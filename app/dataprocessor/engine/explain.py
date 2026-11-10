"""把 recipe 翻成人看得懂的說明，讓使用者不用讀 YAML 就能檢查 AI 寫的規則對不對。

說明完全由程式依 recipe 的結構產生，不經過 AI，所以說明和實際執行的邏輯一定一致。
SQL 會盡量換成白話（欄位換成表頭名稱、AND 換成「且」），原始 SQL 另外附上供核對。
"""
from __future__ import annotations

import re

from .recipe import MODES, Recipe, quote
from .textnorm import TEXT_OPS  # noqa: F401  確保 TEXT_LABELS 與實際支援的操作一致

TEXT_LABELS = {
    "trim": "去掉前後空白", "upper": "轉大寫", "lower": "轉小寫", "halfwidth": "全形轉半形",
    "collapse_space": "連續空白合成一個", "no_space": "去掉所有空白", "digits_only": "只留數字",
    "alnum_only": "只留文字與數字",
}
TYPE_LABELS = {"text": "文字", "number": "數字", "integer": "整數", "date": "日期"}
MISSING_LABELS = {"ask": "留空並列出來請人補上", "keep": "保留原本的寫法並提示", "blank": "留空並提示"}
UNMATCHED_LABELS = {"flag": "標記需檢查", "keep": "保留這列，不標記", "drop": "從結果移除這列"}
LEVEL_LABELS = {"review": "需檢查", "notice": "提示"}

_FUNCTIONS = [
    (r"\bjaro_winkler_similarity\s*\(", "相似度("), (r"\blevenshtein\s*\(", "相差字數("),
    (r"\bdp_key\s*\(", "寬鬆比對("), (r"\bdp_digits\s*\(", "只取數字("), (r"\bregexp_replace\s*\(", "取代("),
    (r"\bregexp_matches\s*\(", "符合格式("), (r"\bcoalesce\s*\(", "第一個不是空白的("), (r"\babs\s*\(", "絕對值("),
    (r"\bround\s*\(", "四捨五入("), (r"\bstring_agg\s*\(", "串接("), (r"\bsum\s*\(", "加總("),
    (r"\bcount\s*\(", "筆數("), (r"\bmax\s*\(", "最大("), (r"\bmin\s*\(", "最小("), (r"\bany_value\s*\(", "任一("),
]
_WORDS = [
    (r"\bIS\s+NOT\s+NULL\b", "不是空白"), (r"\bIS\s+NULL\b", "是空白"), (r"\bNOT\s+LIKE\b", "不包含"),
    (r"\bLIKE\b", "符合"), (r"\bNOT\s+IN\b", "不在"), (r"\bIN\b", "在"), (r"\bAND\b", "且"), (r"\bOR\b", "或"),
    (r"\bNOT\b", "不是"), (r"\bCASE\s+WHEN\b", "如果"), (r"\bWHEN\b", "如果"), (r"\bTHEN\b", "就是"),
    (r"\bELSE\b", "否則"), (r"\bEND\b", ""), (r"<>|!=", "≠"), (r">=", "≥"), (r"<=", "≤"),
]


class _Names:
    """欄位名稱 → 表頭名稱。"""

    def __init__(self, recipe: Recipe):
        self.recipe = recipe
        self.by_table: dict[str, dict[str, str]] = {}
        for name, spec in recipe.inputs.items():
            columns = {c: col.aliases[0] if col.source is None else c for c, col in spec.columns.items()}
            if spec.sheet_column:
                columns[spec.sheet_column.name] = "工作表名稱"
            self.by_table[name] = columns
        for match in recipe.match:
            columns = dict(self.by_table.get(match.left, {}))
            right = self.by_table.get(match.right, {})
            for alias, source in (match.bring or {}).items():
                columns[alias] = right.get(source, source) if match.rows != "combine" else alias
            self.by_table[match.name] = columns
        self.everything: dict[str, str] = {}
        for columns in self.by_table.values():
            for name, label in columns.items():
                self.everything.setdefault(name, label)

    def column(self, table: str | None, name: str) -> str:
        return self.by_table.get(table or "", {}).get(name) or self.everything.get(name, name)

    def table(self, name: str) -> str:
        return self.recipe.table_label(name)


def humanize(sql: str, names: _Names, left: str | None = None, right: str | None = None) -> str:
    """把 SQL 條件換成比較好讀的句子。只做字面替換，原始 SQL 會另外附上。"""
    text = " ".join(sql.split())
    strings: list[str] = []

    def keep(match):  # 引號裡的文字不動
        strings.append(match.group(0))
        return f"\x00{len(strings) - 1}\x00"

    text = re.sub(r"'(?:[^']|'')*'", keep, text)

    def side(match):
        table = left if match.group(1) == "l" else right
        column = match.group(2)
        label = names.column(table, column) if table else column
        owner = names.table(table) if table else ""
        return f"{owner}「{label}」" if owner else f"「{label}」"

    text = re.sub(r'\b([lr])\."?([A-Za-z_][A-Za-z0-9_]*)"?', side, text)
    for pattern, word in _FUNCTIONS:
        text = re.sub(pattern, word, text, flags=re.IGNORECASE)
    for pattern, word in _WORDS:
        text = re.sub(pattern, word, text, flags=re.IGNORECASE)

    def bare(match):
        name = match.group(1)
        label = names.everything.get(name)
        return f"「{label}」" if label else match.group(0)

    text = re.sub(r'(?<![「\w])"?([A-Za-z_][A-Za-z0-9_]*)"?(?![\w」(])', bare, text)
    def restore(match):
        value = strings[int(match.group(1))][1:-1].replace("''", "'")
        return f"「{value}」" if value else "空白"

    text = re.sub(r"\x00(\d+)\x00", restore, text)
    return " ".join(text.split())


def _pairs(on: str, names: _Names, left: str, right: str) -> str | None:
    """欄位配對清單（[[左欄, 右欄]]）產生的條件，寫成「A 等於 B」。"""
    pairs = re.findall(r'l\."((?:[^"]|"")+)" = r\."((?:[^"]|"")+)"', on)
    rebuilt = " AND ".join(f"l.{quote(a)} = r.{quote(b)}" for a, b in pairs)
    if not pairs or rebuilt != on:
        return None
    return "、".join(f"{names.table(left)}的「{names.column(left, a)}」等於{names.table(right)}的「{names.column(right, b)}」"
                    for a, b in pairs)


def _item(text: str, code: str | None = None, sub: list[str] | None = None) -> dict:
    return {"text": text, "code": code, "sub": sub or []}


def explain(recipe: Recipe) -> dict:
    names = _Names(recipe)
    sections = []

    # ---------- 讀取 ----------
    items = []
    for name, spec in recipe.inputs.items():
        if spec.sheets:
            where = f"讀取所有名稱符合 {'、'.join(spec.sheets)} 的工作表，疊成一張表"
        elif spec.sheet:
            where = f"從工作表「{'」或「'.join(spec.sheet)}」讀取"
        else:
            where = "在所有工作表裡找符合的表頭"
        if spec.header_row:
            where += f"，表頭在第 {spec.header_row} 列"
        if spec.sheet_column:
            part = "工作表名稱" if spec.sheet_column.regex is None else f"工作表名稱中符合 {spec.sheet_column.regex.pattern} 的部分"
            where += f"；{part}放進「{spec.sheet_column.name}」"
        sub = []
        for column in spec.columns.values():
            sub.append(_column_text(column, spec, recipe))
        items.append(_item(f"{spec.label}：{where}", sub=sub))
    sections.append({"title": "讀取資料", "items": items})

    # ---------- 篩選 ----------
    if recipe.gate:
        sections.append({"title": "篩選", "items": [
            _item(f"{names.table(g.input)}：{g.label}。只留下符合這個條件的列：{humanize(g.keep, names, g.input)}",
                  g.keep) for g in recipe.gate]})

    # ---------- 對照表 ----------
    if recipe.mappings:
        items = []
        for name, spec in recipe.mappings.items():
            sub = [f"{target} ← {'、'.join(variants) if variants else '（只對應自己）'}" for target, variants in spec.entries.items()]
            for value in spec.values or []:
                if value not in spec.entries:
                    sub.append(f"{value} ← （只對應自己）")
            head = f"{name}：" + (f"只能對應到 {'、'.join(spec.values)}；" if spec.values else "")
            head += f"找不到時{MISSING_LABELS[spec.missing]}。比對時不分全半形、大小寫、空白與標點"
            used = [f"{names.table(t)}「{names.column(t, c.name)}」" for t, s in recipe.inputs.items()
                    for c in s.columns.values() if c.map == name]
            used += [f"輸出「{c.name}」" for c in recipe.output.columns if c.map == name]
            if used:
                head += f"。用在：{'、'.join(used)}"
            items.append(_item(head, sub=sub))
        sections.append({"title": "對照表", "items": items})

    # ---------- 配對 ----------
    for match in recipe.match:
        left, right = names.table(match.left), names.table(match.right)
        mode = MODES[match.mode]
        items = [_item(f"拿每一列{left}去找對應的{right}。{mode}。")]
        for i, strategy in enumerate(match.strategies, 1):
            condition = _pairs(strategy.on, names, match.left, match.right) or humanize(strategy.on, names, match.left, match.right)
            sub = [f"條件：{condition}"]
            if strategy.when:
                sub.append(f"只用在：{humanize(strategy.when, names, match.left, match.right)}")
            if strategy.best:
                sub.append(f"找到多筆時，挑「{humanize(strategy.best, names, match.left, match.right)}」最高的那一筆；分不出高下時請人選")
            elif not match.multi:
                sub.append("找到多筆時不自動挑，請人選")
            if strategy.review:
                sub.append("用這個方式配到的，要人確認")
            code = strategy.on + (f"\n-- when: {strategy.when}" if strategy.when else "") + (
                f"\n-- best: {strategy.best}" if strategy.best else "")
            items.append(_item(f"第 {i} 種方式：{strategy.label}" + ("（前面的方式都找不到時才用）" if i > 1 else ""), code, sub))
        if match.bring:
            if match.rows == "combine":
                brought = [f"「{alias}」= {humanize(expr, names, None, match.right)}" for alias, expr in match.bring.items()]
                items.append(_item(f"對到的多筆{right}彙總成一列，帶入：", sub=brought))
            else:
                brought = "、".join(names.column(match.right, src) for src in match.bring.values())
                items.append(_item(f"配到後從{right}帶入：{brought}"))
        elif match.multi and match.rows == "expand":
            items.append(_item(f"配到多筆時，每一筆{right}各成一列，帶入{right}的所有欄位"))
        else:
            items.append(_item(f"配到後帶入{right}的所有欄位"))
        if match.multi and match.rows == "expand" and match.bring:
            items.append(_item(f"一列{left}配到多筆{right}時，每一筆各成一列"))
        items.append(_item(f"所有方式都找不到時：{UNMATCHED_LABELS[match.unmatched]}"))
        sections.append({"title": f"配對：{names.table(match.name)}", "items": items})

    # ---------- 計算 ----------
    if recipe.transform:
        sections.append({"title": "計算", "items": [
            _item(f"{step.name}" + (f"：{step.note}" if step.note else "") + "（以 SQL 計算，原文如下）", step.sql)
            for step in recipe.transform]})

    # ---------- 驗證 ----------
    if recipe.validate:
        items = []
        for check in recipe.validate:
            table = check.table or recipe.output.source
            sub = [f"條件：{humanize(check.where, names, table)}"]
            if check.highlight:
                sub.append(f"標在：{'、'.join(check.highlight)}")
            items.append(_item(f"{check.message}（{LEVEL_LABELS[check.level]}）", check.where, sub))
        sections.append({"title": "驗證", "items": items})

    # ---------- 輸出 ----------
    sub = []
    for column in recipe.output.columns:
        source = column.expr.strip('"') if column.expr.startswith('"') else None
        origin = (f"來自「{names.column(recipe.output.source, source)}」" if source
                  else f"計算：{humanize(column.expr, names, recipe.output.source)}")
        notes = [TYPE_LABELS[column.type]] if column.type != "text" else []
        if column.map:
            notes.append(f"套用對照表 {column.map}")
        if column.required:
            notes.append("必填")
        if not column.editable:
            notes.append("不能修改")
        sub.append(f"{column.name}：{origin}" + (f"（{'、'.join(notes)}）" if notes else ""))
    head = f"輸出到工作表「{recipe.output.sheet}」，共 {len(recipe.output.columns)} 欄"
    if recipe.output.order_by:
        head += f"，依 {humanize(recipe.output.order_by, names, recipe.output.source)} 排序"
    sections.append({"title": "輸出", "items": [_item(head, sub=sub)]})

    return {"name": recipe.name, "description": recipe.description, "sections": sections}


def _column_text(column, spec, recipe: Recipe) -> str:
    if column.source is not None:
        source = spec.columns[column.source]
        head = f"{column.name}：取用「{source.aliases[0]}」這一格"
    else:
        head = f"{column.aliases[0]}" + (f"（也接受：{'、'.join(column.aliases[1:])}）" if len(column.aliases) > 1 else "")
    parts = [TYPE_LABELS[column.type]]
    if column.required:
        parts.append("必填")
    if column.extract:
        ways = []
        for rule in column.extract:
            steps = []
            if rule.line is not None:
                steps.append(f"第 {rule.line} 行" if rule.line > 0 else f"倒數第 {-rule.line} 行")
            if rule.after:
                steps.append(f"「{'」或「'.join(rule.after)}」之後")
            if rule.before:
                steps.append(f"「{'」或「'.join(rule.before)}」之前")
            if rule.regex is not None:
                steps.append(f"符合 {rule.regex.pattern}")
            ways.append("的".join(steps) if len(steps) <= 1 else "、".join(steps))
        parts.append("取" + ("；找不到時改取".join(ways)) + ("（都找不到時留空）" if len(ways) > 1 else ""))
    if column.type == "text" and column.text is not None:
        parts.append("、".join(TEXT_LABELS[op] for op in column.text) or "不整理")
    if column.type in ("number", "integer"):
        if column.decimal == ",":
            parts.append("小數點是逗號（1.000,02）")
        if column.strip:
            parts.append(f"去掉 {'、'.join(column.strip)}")
    if column.type == "date":
        if column.roc == "always":
            parts.append("一律當成民國年")
        elif column.roc == "auto":
            parts.append("年份小於 1000 當成民國年")
        if column.formats:
            parts.append(f"也接受格式 {'、'.join(column.formats)}")
    if column.replace:
        parts.append(f"先做 {len(column.replace)} 個文字取代")
    if column.map:
        parts.append(f"套用對照表 {column.map}")
    return f"{head}：{'，'.join(parts)}"
