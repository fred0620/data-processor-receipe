"""依 recipe 執行整個流程，回傳給介面與匯出使用的結果。

Load → Gate → Normalize → Match → Transform → Validate → Mapping → Export

原則跟 pdf-mapper 一樣：判斷不了就標記，不猜測；解析失敗留空，原始內容保留在 raw；
人工修改保留原值；警示只標在實際受影響的欄位。
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from .recipe import MODES, Column, Mapping, Recipe, RecipeError, quote
from .review import MappingStore, ReviewStore
from .sandbox import SQL_TYPES, Sandbox
from .textnorm import clean_text, key, parse_date, parse_integer, parse_number
from .workbook import Sheet, cell_text, data_rows, locate

MAX_CANDIDATES = 5     # 左表一列只對一列時，最多列出幾筆候選
MAX_MULTI = 200        # 左表一列可以對多列時，最多取幾列
STAGES = [
    ("load", "Load 讀取"), ("gate", "Gate 篩選"), ("normalize", "Normalize 整理"), ("match", "Match 配對"),
    ("transform", "Transform 計算"), ("validate", "Validate 驗證"), ("mapping", "Mapping 對照"),
    ("export", "Export 輸出"),
]


@dataclass
class Issue:
    level: str                       # error（無法執行）、review（需檢查）、notice（提示）
    stage: str
    code: str
    message: str
    rid: str | None = None           # 哪一列（輸入表的列代號）
    table: str | None = None
    column: str | None = None        # 來源欄位
    out_columns: list[str] = field(default_factory=list)  # 標在哪些輸出欄位
    dismissed: bool = False

    @property
    def key(self) -> str:
        return f"{self.code}|{self.table or ''}|{self.rid or ''}|{self.column or ''}"

    def to_json(self, index: int) -> dict:
        return {"id": index, "key": self.key, "level": self.level, "stage": self.stage, "code": self.code,
                "message": self.message, "rid": self.rid, "table": self.table, "column": self.column,
                "out_columns": self.out_columns, "dismissed": self.dismissed}


class Mapper:
    """對照表查詢：recipe 寫好的對照，加上使用者在介面補的對照。比對用寬鬆鍵（全半形、大小寫、空白、標點）。"""

    def __init__(self, recipe: Recipe, store: MappingStore):
        self.specs = recipe.mappings
        self.tables: dict[str, dict[str, str]] = {}
        self.added: dict[str, dict[str, str]] = {}
        self.allowed: dict[str, list[str] | None] = {}
        self.store = store
        for name, spec in self.specs.items():
            table: dict[str, str] = {}
            for target, variants in spec.entries.items():
                table[key(target)] = target
                for variant in variants:
                    table[key(variant)] = target
            allowed = None if spec.values is None else [*spec.values, *(v for v in store.values(name) if v not in spec.values)]
            self.allowed[name] = allowed
            for value in allowed or []:
                table.setdefault(key(value), value)
            added = {k: e["target"] for k, e in store.entries(name).items() if isinstance(e, dict) and "target" in e}
            table.update(added)
            self.tables[name] = table
            self.added[name] = added
        self.unmapped: dict[tuple[str, str], dict] = {}

    def lookup(self, name: str, value: str, place: str) -> str | None:
        spec: Mapping = self.specs[name]
        target = self.tables[name].get(key(value))
        allowed = self.allowed[name]
        if target is not None and (allowed is None or target in allowed):
            return target
        entry = self.unmapped.setdefault((name, key(value)), {
            "mapping": name, "raw": value, "count": 0, "places": [], "missing": spec.missing,
            "allowed": allowed})
        entry["count"] += 1
        if place not in entry["places"]:
            entry["places"].append(place)
        return None


class _Run:
    def __init__(self, recipe: Recipe, review: ReviewStore, mappings: MappingStore):
        self.recipe = recipe
        self.review = review
        self.mapper = Mapper(recipe, mappings)
        self.issues: list[Issue] = []
        self.stages: dict[str, dict] = {sid: {"id": sid, "label": label, "status": "skip", "lines": [], "summary": ""}
                                        for sid, label in STAGES}
        self.inputs: dict[str, dict] = {}
        self.raw: dict[str, dict[str, dict]] = {}      # 輸入表 → rid → 原始文字
        self.excluded: list[dict] = []
        self.matches: list[dict] = []
        self.links: dict[str, dict[str, str]] = {}     # 配對名稱 → 帶過來的欄位（新名稱 → 右表欄位）
        self.output: dict = {"columns": [], "rows": []}
        self.blocked = False
        self.current = "load"
        self.labels: dict[str, dict[str, str]] = {}  # 輸入表 → 欄位 → 實際表頭文字（訊息用）
        self.upstream = self._plan_edits()             # rid → 輸入欄位 → (輸出欄位, 修改紀錄)
        self.applied: dict[tuple[str, str], object] = {}  # 已在輸入階段套用的修改 (rid, 輸出欄位) → 原值

    # ---------- 共用 ----------

    def _plan_edits(self) -> dict[str, dict[str, tuple[str, dict]]]:
        """直接來自輸入表的欄位，修改在讀進來時就套用，後面的配對、計算、驗證都會用修改後的值重算。"""
        direct = {c.name: c.expr.strip('"') for c in self.recipe.output.columns if c.expr.startswith('"')}
        plan: dict[str, dict[str, tuple[str, dict]]] = {}
        for rid, changes in self.review.data["edits"].items():
            table = rid.rpartition(":")[0]
            spec = self.recipe.inputs.get(table)
            for out_name, change in changes.items():
                source = direct.get(out_name)
                if spec and source in spec.columns:
                    plan.setdefault(rid, {})[source] = (out_name, change)
        return plan

    def stage(self, sid: str, line: str | None = None, status: str | None = None) -> None:
        stage = self.stages[sid]
        if stage["status"] == "skip":
            stage["status"] = "ok"
        if line:
            stage["lines"].append(line)
        rank = {"skip": 0, "ok": 1, "review": 2, "error": 3}
        if status and rank[status] > rank[stage["status"]]:
            stage["status"] = status

    def summary(self, sid: str, text: str) -> None:
        """卡片上的一句話摘要，細節放在 lines。"""
        self.stages[sid]["summary"] = text

    def fatal(self, problems: list[str], sid: str | None = None) -> None:
        sid = sid or self.current
        for problem in problems:
            self.issues.append(Issue("error", sid, "recipe", problem))
        self.stage(sid, status="error")
        self.blocked = True

    # ---------- Load + Normalize ----------

    def load(self, sheets: list[Sheet], box: Sandbox) -> list[Issue]:
        pending: list[Issue] = []
        by_name = {s.name: s for s in sheets}
        for spec in self.recipe.inputs.values():
            found = locate(sheets, spec.sheet, spec.header_row, {c: col.aliases for c, col in spec.columns.items()})
            if found is None:
                where = f"工作表 {'、'.join(spec.sheet)}" if spec.sheet else "所有工作表"
                self.fatal([f"輸入表 {spec.name}：在{where}裡找不到任何一個欄位的表頭"])
                continue
            required = [c for c in found.missing if spec.columns[c].required]
            if required:
                names = "、".join(f"{c}（{'/'.join(spec.columns[c].aliases)}）" for c in required)
                self.fatal([f"輸入表 {spec.name}：工作表「{found.sheet}」第 {found.header_row} 列找不到必要欄位 {names}"])
                continue
            for column in found.missing:
                self.issues.append(Issue("notice", "load", "missing_column",
                                         f"{spec.name} 找不到欄位 {column}（{'/'.join(spec.columns[column].aliases)}），整欄留空",
                                         table=spec.name, column=column))
            self.labels[spec.name] = {c: found.headers.get(c, spec.columns[c].aliases[0]) for c in spec.columns}
            rows = []
            self.raw[spec.name] = {}
            for number, raw in data_rows(by_name[found.sheet], found):
                rid = f"{spec.name}:{number}"
                self.raw[spec.name][rid] = raw
                row = {"_rid": rid, "_row": number}
                for name, column in spec.columns.items():
                    before = len(pending)
                    row[name] = self.normalize(spec.name, column, raw.get(name), rid, pending)
                    if name in self.upstream.get(rid, {}):
                        out_name, change = self.upstream[rid][name]
                        now = _display(row[name]) if row[name] is not None else _display(raw.get(name))
                        del pending[before:]          # 人工修正過的格子，不再提醒解析或對照問題
                        if now != _display(change.get("original")):
                            pending.append(Issue("review", "normalize", "edit_stale",
                                                 f"{out_name} 人工修改後，原始值已變更（原本「{_display(change.get('original'))}」，"
                                                 f"現在「{now}」）", rid=rid, table=spec.name, column=name))
                        value = change.get("value")
                        row[name] = None if value == "" else value
                        self.applied[(rid, out_name)] = change.get("original")
                rows.append(row)
            types = {"_rid": "VARCHAR", "_row": "BIGINT",
                     **{name: SQL_TYPES[c.type] for name, c in spec.columns.items()}}
            box.load(spec.name, types, rows)
            self.inputs[spec.name] = {"sheet": found.sheet, "header_row": found.header_row, "rows": len(rows),
                                      "headers": found.headers, "missing": found.missing, "excluded": 0}
            self.stage("load", f"{spec.name}：工作表「{found.sheet}」第 {found.header_row} 列為表頭，{len(rows)} 列")
        self.summary("load", f"{len(self.inputs)} 張表・{sum(i['rows'] for i in self.inputs.values())} 列")
        return pending

    def normalize(self, table: str, column: Column, raw: str | None, rid: str, pending: list[Issue]):
        label = self.labels.get(table, {}).get(column.name, column.name)

        def flag(level: str, code: str, message: str) -> None:
            pending.append(Issue(level, "normalize", code, message, rid=rid, table=table, column=column.name))

        if raw is None or str(raw).strip() == "":
            if column.required:
                flag("review", "required", f"{label} 是必填欄位，但這列是空白")
            return None
        text = str(raw)
        for pattern, repl in column.replace if column.type != "text" else []:
            text = pattern.sub(repl, text)
        if column.type == "number":
            value = parse_number(text, column.strip)
        elif column.type == "integer":
            value = parse_integer(text, column.strip)
        elif column.type == "date":
            value = parse_date(text, column.formats, column.roc)
        else:
            value = clean_text(text, column.text, column.replace)
            if value is not None and column.map:
                mapped = self.mapper.lookup(column.map, value, f"{table}.{column.name}")
                if mapped is None:
                    return self._missing_map(column.map, value, flag)
                value = mapped
            return value
        if value is None:
            kind = {"number": "數字", "integer": "整數", "date": "日期"}[column.type]
            flag("review", "parse", f"{label} 無法解析成{kind}，已留空（原始內容：{raw}）")
        return value

    def _missing_map(self, name: str, value: str, flag) -> str | None:
        missing = self.recipe.mappings[name].missing
        if missing == "ask":
            flag("review", "unmapped", f"「{value}」不在對照表 {name}，請補上對照")
            return None
        if missing == "keep":
            flag("notice", "unmapped", f"「{value}」不在對照表 {name}，保留原值")
            return value
        flag("notice", "unmapped", f"「{value}」不在對照表 {name}，已留空")
        return None

    # ---------- Gate ----------

    def gate(self, box: Sandbox, pending: list[Issue]) -> None:
        excluded_rids: set[str] = set()
        for spec in self.recipe.gate:
            where = f"gate「{spec.label}」"
            condition = f"NOT COALESCE(({spec.keep}), FALSE)"
            rows = box.query(f"SELECT _rid, _row FROM {quote(spec.input)} WHERE {condition}", where)
            box.execute(f"DELETE FROM {quote(spec.input)} WHERE {condition}", where)
            for rid, number in rows:
                excluded_rids.add(rid)
                self.excluded.append({"input": spec.input, "rid": rid, "row": number, "label": spec.label,
                                      "values": self.raw.get(spec.input, {}).get(rid, {})})
            self.inputs[spec.input]["excluded"] += len(rows)
            self.stage("gate", f"{spec.input}：{spec.label}，排除 {len(rows)} 列")
            if rows and len(rows) == self.inputs[spec.input]["rows"]:
                self.issues.append(Issue("review", "gate", "gate_all", f"{spec.input} 的每一列都被「{spec.label}」排除，"
                                         "條件可能寫錯", table=spec.input))
                self.stage("gate", status="review")
        if not self.recipe.gate:
            self.stage("gate", "沒有設定篩選條件")
        self.summary("gate", f"排除 {len(self.excluded)} 列" if self.recipe.gate else "未設定")
        kept = [issue for issue in pending if issue.rid not in excluded_rids]  # 被排除的列不提醒
        self.issues.extend(kept)
        counts: dict[str, int] = {}
        for issue in kept:
            counts[issue.code] = counts.get(issue.code, 0) + 1
        labels = {"parse": "無法解析", "required": "必填空白", "unmapped": "不在對照表"}
        for code, n in counts.items():
            self.stage("normalize", f"{labels.get(code, code)} {n} 格", "review")
        self.stage("normalize", None if counts else "所有欄位都已整理完成")
        self.summary("normalize", f"{sum(counts.values())} 格待處理" if counts else "完成")

    # ---------- Match ----------

    def match(self, box: Sandbox) -> None:
        for spec in self.recipe.match:
            self._match_one(box, spec)
        if not self.recipe.match:
            self.stage("match", "沒有設定配對")
        todo = sum(m["counts"]["ambiguous"] + m["counts"]["review"] + m["counts"]["unmatched"] for m in self.matches)
        self.summary("match", "未設定" if not self.recipe.match else f"{todo} 列待處理" if todo else "全部完成")

    def _match_one(self, box: Sandbox, spec) -> None:
        where = f"match「{spec.name}」"
        left, right = quote(spec.left), quote(spec.right)
        for table in (spec.left, spec.right):
            if "_rid" not in box.columns(table):
                raise RecipeError([f"{where}：表 {table} 沒有 _rid 欄位，transform 的 SELECT 要保留 _rid"])
        left_rids = list(dict.fromkeys(r[0] for r in box.query(f"SELECT _rid FROM {left}", where)))
        right_rids = {r[0] for r in box.query(f"SELECT _rid FROM {right}", where)}
        exclusive = spec.mode in ("one_to_one", "one_to_many")   # 右表每列只能給一個左表列
        decided: dict[str, dict] = {}
        used: set[str] = set()
        box.execute("CREATE OR REPLACE TEMP TABLE __decided (rid VARCHAR)", where)
        box.execute("CREATE OR REPLACE TEMP TABLE __used (rid VARCHAR)", where)

        known = set(left_rids)
        for left_rid, chosen in self.review.data["matches"].get(spec.name, {}).items():
            if left_rid not in known:
                continue
            chosen = [chosen] if isinstance(chosen, str) and chosen else chosen if isinstance(chosen, list) else []
            lost = [rid for rid in chosen if rid not in right_rids]
            chosen = [rid for rid in chosen if rid in right_rids]
            if lost:
                self.issues.append(Issue("review", "match", "manual_lost",
                                         f"{spec.name}：之前人工指定的 {'、'.join(lost)} 已不存在"
                                         + ("，改回自動比對" if not chosen else ""), rid=left_rid, table=spec.left))
                if not chosen:
                    continue
            if not chosen:
                decided[left_rid] = {"status": "none", "rights": [], "how": "人工：沒有配對", "candidates": []}
            else:
                decided[left_rid] = {"status": "manual", "rights": chosen, "how": "人工指定", "candidates": []}
                used.update(chosen)
        box.insert_values("__decided", [(rid,) for rid in decided])
        box.insert_values("__used", [(rid,) for rid in used])

        stats: list[str] = []
        limit = MAX_MULTI if spec.multi else MAX_CANDIDATES
        for strategy in spec.strategies:
            swhere = f"{where} 的「{strategy.label}」"
            filters = ["l._rid NOT IN (SELECT rid FROM __decided)"]
            if strategy.when:
                filters.append(f"COALESCE(({strategy.when}), FALSE)")
            if exclusive:
                filters.append("r._rid NOT IN (SELECT rid FROM __used)")
            score = f"({strategy.best})" if strategy.best else "NULL"
            rows = box.query(
                f"SELECT lr, rr, score, n FROM (SELECT l._rid AS lr, r._rid AS rr, {score} AS score, "
                f"count(*) OVER (PARTITION BY l._rid) AS n, row_number() OVER (PARTITION BY l._rid "
                f"ORDER BY {score} DESC NULLS LAST, r._rid) AS k FROM {left} l JOIN {right} r ON ({strategy.on}) "
                f"WHERE {' AND '.join(filters)}) WHERE k <= {limit}", swhere)
            grouped: dict[str, list[tuple]] = {}
            for lr, rr, value, n in rows:
                grouped.setdefault(lr, []).append((rr, value, n))
            new = (self._decide_multi if spec.multi else self._decide_single)(grouped, strategy)
            if exclusive:
                self._resolve_claims(new, spec)
            decided.update(new)
            box.insert_values("__decided", [(lr,) for lr in new])
            newly_used = {rr for d in new.values() for rr in d["rights"]}
            used |= newly_used
            box.insert_values("__used", [(rr,) for rr in newly_used])
            matched = sum(1 for d in new.values() if d["rights"])
            pairs = sum(len(d["rights"]) for d in new.values())
            ambiguous = sum(1 for d in new.values() if d["status"] == "ambiguous")
            stats.append(f"{strategy.label}：{matched} 列" + (f"（{pairs} 組）" if spec.multi and pairs != matched else "")
                         + (f"，待選 {ambiguous} 列" if ambiguous else ""))

        rows_json = []
        for lr in left_rids:
            decision = decided.get(lr) or {"status": "unmatched", "rights": [], "how": "", "candidates": []}
            decided[lr] = decision
            if decision["status"] == "ambiguous":
                total = decision.get("total", len(decision["candidates"]))
                text = (f"{spec.name}：「{decision['how']}」找到 {total} 筆候選，請選擇"
                        if not decision.get("conflict") else
                        f"{spec.name}：候選的 {spec.right} 同時對到其他列，請選擇")
                self.issues.append(Issue("review", "match", "match_ambiguous", text, rid=lr, table=spec.left))
            elif decision["status"] == "unmatched" and spec.unmatched == "flag":
                self.issues.append(Issue("review", "match", "match_none",
                                         f"{spec.name}：所有比對方式都找不到對應的 {spec.right}", rid=lr, table=spec.left))
            elif decision["status"] == "review":
                self.issues.append(Issue("review", "match", "match_review",
                                         f"{spec.name}：以「{decision['how']}」配對，請確認", rid=lr, table=spec.left))
            if decision.get("overflow"):
                self.issues.append(Issue("review", "match", "match_overflow",
                                         f"{spec.name}：對到超過 {MAX_MULTI} 列，只取前 {MAX_MULTI} 列，比對條件可能太寬",
                                         rid=lr, table=spec.left))
            if decision.get("dropped"):
                self.issues.append(Issue("review", "match", "match_shared",
                                         f"{spec.name}：{len(decision['dropped'])} 筆 {spec.right} 同時對到其他列，已先拿掉，"
                                         "請確認要歸給哪一列", rid=lr, table=spec.left))
            rows_json.append({"left": lr, **decision})

        self._build_match_table(box, spec, left_rids, decided, where)
        counts = {s: sum(1 for d in decided.values() if d["status"] == s)
                  for s in ("auto", "review", "manual", "none", "ambiguous", "unmatched")}
        unused = [rid for rid in right_rids if rid not in used] if exclusive else \
            [rid for rid in right_rids if rid not in {r for d in decided.values() for r in d["rights"]}]
        pair_total = sum(len(d["rights"]) for d in decided.values())
        self.matches.append({
            "name": spec.name, "left": spec.left, "right": spec.right, "mode": spec.mode, "multi": spec.multi,
            "mode_label": MODES[spec.mode].split("：")[0], "rows_mode": spec.rows,
            "strategies": [s.label for s in spec.strategies], "counts": counts, "pairs": pair_total,
            "rows": rows_json, "show": self._show_columns(spec),
            "left_rows": _preview(box, spec.left, self.labels.get(spec.left)),
            "right_rows": _preview(box, spec.right, self.labels.get(spec.right)),
            "unused_right": sorted(unused, key=_rid_order)})
        status = "review" if counts["ambiguous"] or counts["review"] or (
            counts["unmatched"] and spec.unmatched == "flag") else None
        self.stage("match", f"{spec.name}（{MODES[spec.mode].split('：')[0]}）{len(left_rids)} 列", status)
        for line in stats:
            self.stage("match", "　" + line)
        if counts["manual"] or counts["none"]:
            self.stage("match", f"　人工指定 {counts['manual'] + counts['none']} 列")
        if counts["unmatched"]:
            self.stage("match", f"　找不到 {counts['unmatched']} 列")
        if unused:
            self.stage("match", f"　{spec.right} 沒用到 {len(unused)} 列")

    @staticmethod
    def _decide_single(grouped: dict[str, list[tuple]], strategy) -> dict[str, dict]:
        """左表一列只對一列：只有一筆候選，或 best 分數最高的只有一筆，才算配對成功；其他列給人選。"""
        new = {}
        for lr, candidates in grouped.items():
            top = candidates[0]
            unique = top[2] == 1 or (strategy.best and top[1] is not None
                                     and (len(candidates) < 2 or candidates[1][1] is None or top[1] > candidates[1][1]))
            cand = [{"rid": rr, "score": _json(value)} for rr, value, _ in candidates]
            if unique:
                new[lr] = {"status": "review" if strategy.review else "auto", "rights": [top[0]],
                           "how": strategy.label, "candidates": cand}
            else:
                new[lr] = {"status": "ambiguous", "rights": [], "how": strategy.label, "candidates": cand,
                           "total": top[2]}
        return new

    @staticmethod
    def _decide_multi(grouped: dict[str, list[tuple]], strategy) -> dict[str, dict]:
        """左表一列可以對多列：符合條件的全部都算。"""
        return {lr: {"status": "review" if strategy.review else "auto", "rights": [rr for rr, _, _ in candidates],
                     "how": strategy.label, "candidates": [], "overflow": candidates[0][2] > MAX_MULTI}
                for lr, candidates in grouped.items()}

    @staticmethod
    def _resolve_claims(new: dict[str, dict], spec) -> None:
        """右表每列只能給一個左表列時，同一個右表列被多個左表列選中，不替人決定歸屬。"""
        claimed: dict[str, list[str]] = {}
        for lr, decision in new.items():
            for rr in decision["rights"]:
                claimed.setdefault(rr, []).append(lr)
        shared = {rr for rr, lrs in claimed.items() if len(lrs) > 1}
        if not shared:
            return
        for lr, decision in new.items():
            dropped = [rr for rr in decision["rights"] if rr in shared]
            if not dropped:
                continue
            kept = [rr for rr in decision["rights"] if rr not in shared]
            options = decision["candidates"] or [{"rid": rr, "score": None} for rr in decision["rights"]]
            if kept:
                decision.update(rights=kept, dropped=dropped)
            else:
                decision.update(status="ambiguous", rights=[], candidates=options, conflict=True,
                                total=len(options))

    def _build_match_table(self, box: Sandbox, spec, left_rids: list[str], decided: dict[str, dict], where: str) -> None:
        right_columns = [c for c in box.columns(spec.right) if not c.startswith("_")]
        left_columns = box.columns(spec.left)
        combine = spec.rows == "combine"
        bring = spec.bring or {f"{spec.right}_{c}": c for c in right_columns}
        for alias, source in bring.items():
            if not combine and source not in right_columns:
                raise RecipeError([f"{where}.bring：右表 {spec.right} 沒有欄位 {source}"])
            if alias in left_columns:
                raise RecipeError([f"{where}.bring：新欄位名稱 {alias} 和左表欄位重複，請換一個名稱"])
        self.links[spec.name] = {} if combine else bring

        box.execute("CREATE OR REPLACE TEMP TABLE __pairs (seq BIGINT, lr VARCHAR, rr VARCHAR, how VARCHAR, "
                    "status VARCHAR)", where)
        pairs = []
        for i, lr in enumerate(left_rids):
            d = decided[lr]
            for rr in d["rights"] or [None]:
                pairs.append((i, lr, rr, d["how"], d["status"]))
        box.insert_values("__pairs", pairs)
        drop = "WHERE p.status NOT IN ('unmatched', 'ambiguous', 'none')" if spec.unmatched == "drop" else ""
        rid, how, status = (quote(f"_{k}_{spec.name}") for k in ("rid", "how", "status"))
        if combine:   # 對到的多列彙總成一列，bring 是彙總運算式
            brought = "".join(f", ({expr}) AS {quote(alias)}" for alias, expr in bring.items())
            box.execute(
                f"CREATE TABLE {quote(spec.name)} AS SELECT l.*{brought}, string_agg(r._rid, ',' ORDER BY r._rid) AS {rid}, "
                f"count(r._rid) AS {quote('_count_' + spec.name)}, any_value(p.how) AS {how}, any_value(p.status) AS {status} "
                f"FROM {quote(spec.left)} l JOIN __pairs p ON p.lr = l._rid LEFT JOIN {quote(spec.right)} r ON r._rid = p.rr "
                f"{drop} GROUP BY ALL ORDER BY min(p.seq)", where)
        else:         # 每組配對一列；左表一列對到多列時會變成多列
            brought = "".join(f", r.{quote(src)} AS {quote(alias)}" for alias, src in bring.items())
            box.execute(
                f"CREATE TABLE {quote(spec.name)} AS SELECT l.*{brought}, p.rr AS {rid}, p.how AS {how}, "
                f"p.status AS {status} FROM {quote(spec.left)} l JOIN __pairs p ON p.lr = l._rid "
                f"LEFT JOIN {quote(spec.right)} r ON r._rid = p.rr {drop} ORDER BY p.seq, p.rr", where)

    def _show_columns(self, spec) -> dict[str, list[str]]:
        """配對畫面先顯示的欄位：recipe 的 show，沒寫就用比對條件裡出現的欄位。顯示名稱用實際表頭。"""
        result = {}
        for side, table, alias in (("left", spec.left, "l"), ("right", spec.right, "r")):
            labels = self.labels.get(table, {})
            names = spec.show.get(side) or []
            if not names:
                for strategy in spec.strategies:
                    for found in re.findall(rf'\b{alias}\."?([A-Za-z][A-Za-z0-9_]*)', strategy.on):
                        if found not in names:
                            names.append(found)
            result[side] = [labels.get(n, n) for n in names]
        return result

    # ---------- Transform、Validate ----------

    def transform(self, box: Sandbox) -> None:
        for step in self.recipe.transform:
            where = f"transform「{step.name}」"
            box.execute(f"CREATE TABLE {quote(step.name)} AS {step.sql}", where)
            self.stage("transform", f"{step.name}：{box.count(step.name)} 列" + (f"（{step.note}）" if step.note else ""))
        if not self.recipe.transform:
            self.stage("transform", "沒有設定計算步驟")
        self.summary("transform", f"{len(self.recipe.transform)} 個步驟" if self.recipe.transform else "未設定")

    def validate(self, box: Sandbox) -> None:
        for i, check in enumerate(self.recipe.validate):
            table = check.table or self.recipe.output.source
            where = f"validate[{i}]「{check.message}」"
            if "_rid" not in box.columns(table):
                raise RecipeError([f"{where}：表 {table} 沒有 _rid 欄位，無法標到是哪一列"])
            rows = box.query(f"SELECT _rid FROM {quote(table)} WHERE COALESCE(({check.where}), FALSE)", where)
            for (rid,) in rows:
                self.issues.append(Issue(check.level, "validate", f"check{i}", check.message, rid=rid, table=table,
                                         out_columns=list(check.highlight)))
            self.stage("validate", f"{check.message}：{len(rows)} 列", "review" if rows and check.level == "review" else None)
        if not self.recipe.validate:
            self.stage("validate", "沒有設定驗證規則")
        flagged = len({i.rid for i in self.issues if i.stage == "validate" and i.level == "review"})
        self.summary("validate", "未設定" if not self.recipe.validate else f"{flagged} 列有問題" if flagged else "全部通過")

    # ---------- Mapping + Export ----------

    def build_output(self, box: Sandbox) -> None:
        spec = self.recipe.output
        source_columns = box.columns(spec.source)
        rid_columns = [c for c in source_columns if c == "_rid" or c.startswith("_rid_")]
        extra = rid_columns + (["_row"] if "_row" in source_columns else [])
        select = ", ".join([*(quote(c) for c in extra),
                            *(f"({c.expr}) AS {quote(f'__c{i}')}" for i, c in enumerate(spec.columns))])
        order = f" ORDER BY {spec.order_by}" if spec.order_by else ""
        rows = box.query(f"SELECT {select} FROM {quote(spec.source)}{order}", "output")
        direct = {c.expr.strip('"'): c.name for c in spec.columns if c.expr.startswith('"')}
        translations = {"_rid": direct}
        for match_name, bring in self.links.items():
            translations[f"_rid_{match_name}"] = {src: direct[alias] for alias, src in bring.items() if alias in direct}

        edits = self.review.data["edits"]
        out_rows = []
        index: dict[str, list[tuple[int, dict]]] = {}
        seen: dict[str, int] = {}
        for row in rows:
            seen[row[0]] = seen.get(row[0], 0) + 1
        for n, row in enumerate(rows):
            own = dict(zip(extra, row[:len(extra)]))
            rid = own.get("_rid") or f"out:{n + 1}"
            if own.get("_rid") and seen.get(rid, 0) > 1:   # 一對多展開後同一個左表列有多列，加上右表列代號區分
                rid = "|".join([rid, *(str(own[c]) for c in rid_columns if c != "_rid" and own.get(c))])
            record = {"rid": rid, "row": own.get("_row"), "values": {}, "raw": {}, "edited": {}, "issues": []}
            cell_issues: list[Issue] = []
            for column, value in zip(spec.columns, row[len(extra):]):
                record["values"][column.name] = self._output_value(column, value, record, rid, cell_issues)
            for name, change in edits.get(rid, {}).items():
                if name not in record["values"]:
                    continue
                if (rid, name) in self.applied:
                    record["edited"][name] = self.applied[(rid, name)]
                    record["raw"].pop(name, None)
                    continue
                now = _display(record["values"][name] if name not in record["raw"] else record["raw"][name])
                if now != _display(change.get("original")):
                    self.issues.append(Issue("review", "mapping", "edit_stale",
                                             f"{name} 人工修改後，原始值已變更（原本「{_display(change.get('original'))}」，"
                                             f"現在「{now}」）", rid=rid, out_columns=[name]))
                record["values"][name] = change.get("value")
                record["edited"][name] = change.get("original")
                record["raw"].pop(name, None)
            # 人工改過的格子，不再提醒這格的解析或對照問題
            self.issues.extend(i for i in cell_issues if not set(i.out_columns) & set(record["edited"]))
            out_rows.append(record)
            for column in rid_columns:
                for linked in str(own.get(column) or "").split(","):   # 彙總時是逗號分隔的多個列代號
                    if linked:
                        index.setdefault(linked, []).append((n, translations.get(column, {})))
            if rid != own.get("_rid"):
                index.setdefault(rid, []).append((n, {}))

        dismissed = set(self.review.data["dismissed"])
        for issue in self.issues:
            issue.dismissed = issue.key in dismissed
        for number, issue in enumerate(self.issues):
            for row_index, translate in index.get(issue.rid or "", []):
                record = out_rows[row_index]
                if issue.column and issue.stage == "normalize" and issue.column in translate:
                    target = translate[issue.column]
                    if target in record["edited"] and issue.code != "edit_stale":
                        continue  # 這格已經人工修正
                    issue.out_columns = [target]
                    raw = self.raw.get(issue.table or "", {}).get(issue.rid, {}).get(issue.column)
                    if issue.code in ("parse", "unmapped") and raw is not None and record["values"].get(target) is None:
                        record["raw"][target] = raw
                record["issues"].append(number)
        for record in out_rows:  # 同一格已經有解析或對照問題時，不再重複提醒「必填空白」
            explained = {c for i in record["issues"] for c in self.issues[i].out_columns
                         if self.issues[i].code in ("parse", "unmapped")}
            for i in record["issues"]:
                issue = self.issues[i]
                if issue.code == "required" and issue.stage == "mapping" and set(issue.out_columns) <= explained:
                    issue.level = "skip"
            record["issues"] = [i for i in record["issues"] if self.issues[i].level != "skip"]
        for record in out_rows:
            active = [self.issues[i] for i in record["issues"] if not self.issues[i].dismissed]
            record["status"] = ("review" if any(i.level == "review" for i in active)
                                else "notice" if active else "ok")
        self.output = {"sheet": spec.sheet, "columns": [
            {"name": c.name, "type": c.type, "map": c.map, "required": c.required, "editable": c.editable}
            for c in spec.columns], "rows": out_rows}

        review_rows = sum(1 for r in out_rows if r["status"] == "review")
        unmapped = sum(e["count"] for e in self.mapper.unmapped.values() if e["missing"] == "ask")
        if self.recipe.mappings:
            added = sum(len(v) for v in self.mapper.added.values())
            self.stage("mapping", f"對照表 {len(self.recipe.mappings)} 張" + (f"，介面補上的對照 {added} 筆" if added else ""))
        self.stage("mapping", f"待補對照 {unmapped} 格" if unmapped else "所有值都有對照", "review" if unmapped else None)
        edited = sum(len(r["edited"]) for r in out_rows)
        if edited:
            self.stage("mapping", f"人工修改 {edited} 格")
        self.stage("export", f"輸出 {len(out_rows)} 列，需檢查 {review_rows} 列", "review" if review_rows else None)
        self.summary("mapping", f"待補 {unmapped} 格" if unmapped else "完成" if self.recipe.mappings else "未設定")
        self.summary("export", f"{len(out_rows)} 列・{review_rows} 列需檢查" if review_rows else f"{len(out_rows)} 列")

    def _output_value(self, column, value, record: dict, rid: str, issues: list[Issue]):
        def flag(level: str, code: str, message: str) -> None:
            issues.append(Issue(level, "mapping", code, message, rid=rid, out_columns=[column.name]))

        if isinstance(value, Decimal):
            value = float(value)
        if value is None or (isinstance(value, str) and value.strip() == ""):
            if column.required:
                flag("review", "required", f"{column.name} 是必填欄位，但這列是空白")
            return None
        if column.type in ("number", "integer"):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                parsed = parse_number(str(value)) if column.type == "number" else parse_integer(str(value))
                if parsed is None:
                    record["raw"][column.name] = str(value)
                    flag("review", "parse", f"{column.name} 不是數字，已留空（原始內容：{value}）")
                return parsed
            return int(value) if column.type == "integer" and float(value).is_integer() else value
        if column.type == "date":
            if isinstance(value, dt.datetime):
                return value.date().isoformat()
            if isinstance(value, dt.date):
                return value.isoformat()
            parsed = parse_date(str(value))
            if parsed is None:
                record["raw"][column.name] = str(value)
                flag("review", "parse", f"{column.name} 不是日期，已留空（原始內容：{value}）")
                return None
            return parsed.isoformat()
        text = value if isinstance(value, str) else cell_text(value)
        if column.map:
            mapped = self.mapper.lookup(column.map, text, column.name)
            if mapped is None:
                record["raw"][column.name] = text
                kept = self._missing_map(column.map, text, flag)
                if kept is None:
                    return None
                record["raw"].pop(column.name, None)
                return kept
            return mapped
        return text

    # ---------- 結果 ----------

    def result(self) -> dict:
        active = [i for i in self.issues if not i.dismissed and i.level != "skip"]
        status = ("error" if self.blocked else "review" if any(i.level == "review" for i in active) else "ok")
        return {
            "recipe": {"id": self.recipe.id, "name": self.recipe.name},
            "status": status,
            "stages": [self.stages[sid] for sid, _ in STAGES],
            "inputs": self.inputs,
            "excluded": self.excluded,
            "matches": self.matches,
            "output": self.output,
            "issues": [i.to_json(n) for n, i in enumerate(self.issues)],  # skip 的保留位置，id 才會對上
            "unmapped": sorted(self.mapper.unmapped.values(), key=lambda e: (e["mapping"], -e["count"])),
            "mappings": [{"name": name, "allowed": self.mapper.allowed[name], "missing": spec.missing,
                          "custom_values": self.mapper.store.values(name),
                          "added": sorted(({"raw": e["raw"], "target": e["target"]}
                                           for e in self.mapper.store.entries(name).values()
                                           if isinstance(e, dict) and "target" in e), key=lambda e: e["raw"])}
                         for name, spec in self.recipe.mappings.items()],
            "counts": {"review": sum(1 for i in active if i.level == "review"),
                       "notice": sum(1 for i in active if i.level == "notice"),
                       "error": sum(1 for i in active if i.level == "error")},
        }


def _json(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value


def _display(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _rid_order(rid: str):
    table, _, number = rid.rpartition(":")
    return (table, int(number) if number.isdigit() else 0, rid)


def _preview(box: Sandbox, table: str, labels: dict[str, str] | None = None) -> dict[str, dict]:
    """列出表的內容給配對畫面用；輸入表的欄位顯示成實際表頭文字。"""
    columns = box.columns(table)
    shown = [c for c in columns if not c.startswith("_")]
    has_row = "_row" in columns
    picked = ["_rid", *(["_row"] if has_row else []), *shown]
    rows = box.query(f"SELECT {', '.join(quote(c) for c in picked)} FROM {quote(table)}", "preview")
    result = {}
    labels = labels or {}
    for row in rows:
        values = dict(zip(picked, row))
        rid = values.pop("_rid")
        number = values.pop("_row", None)
        result[rid] = {"row": number, "values": {labels.get(k, k): _json(v) for k, v in values.items()}}
    return result


def run(recipe: Recipe, sheets: list[Sheet], review: ReviewStore, mappings: MappingStore, scratch: Path) -> dict:
    job = _Run(recipe, review, mappings)
    box = Sandbox(scratch)
    try:
        try:
            pending = job.load(sheets, box)
        finally:
            box.lock()
        if job.blocked:
            return job.result()
        for job.current, step in (("gate", lambda: job.gate(box, pending)), ("match", lambda: job.match(box)),
                                  ("transform", lambda: job.transform(box)), ("validate", lambda: job.validate(box)),
                                  ("export", lambda: job.build_output(box))):
            step()
    except RecipeError as exc:
        job.fatal(exc.problems)
    finally:
        box.close()
    return job.result()
