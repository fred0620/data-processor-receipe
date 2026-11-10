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
    "collapse_space": "連續空白合成一個（保留換行）", "single_line": "合成一行", "no_space": "去掉所有空白", "digits_only": "只留數字",
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
    (r"\bLIKE\b", "符合"), (r"\bNOT\s+IN\b", "不在"), (r"\bIN\b", "在"), (r"\bAND\b", "\x01且\x01"), (r"\bOR\b", "\x01或\x01"),
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
    text = " ".join(text.split())
    text = re.sub(r"(?<=[\u4e00-\u9fff」）])\s+|\s+(?=[\u4e00-\u9fff「（])", "", text)  # 中文之間不留空白
    return text.replace("\x01", " ").replace("  ", " ").strip()


def _pairs(on: str, names: _Names, left: str, right: str) -> str | None:
    """欄位配對清單（[[左欄, 右欄]]）產生的條件，寫成「A 等於 B」。"""
    pairs = re.findall(r'l\."((?:[^"]|"")+)" = r\."((?:[^"]|"")+)"', on)
    rebuilt = " AND ".join(f"l.{quote(a)} = r.{quote(b)}" for a, b in pairs)
    if not pairs or rebuilt != on:
        return None
    return "、".join(f"{names.table(left)}的「{names.column(left, a)}」等於{names.table(right)}的「{names.column(right, b)}」"
                    for a, b in pairs)


def _node(text: str, kind: str = "step", children: list | None = None, code: str | None = None) -> dict:
    """說明裡的一個節點。kind：step（步驟）、if（如果）、then（結果）、else（否則）、note（補充）、detail（預設收起來的細節）。"""
    return {"text": text, "kind": kind, "children": children or [], "code": code}


def _main_input(recipe: Recipe) -> str:
    """說明的主角：第一個配對最左邊的輸入表；沒有配對時是第一張輸入表。"""
    if recipe.match:
        table = recipe.match[0].left
        names = {m.name: m for m in recipe.match}
        while table in names:
            table = names[table].left
        if table in recipe.inputs:
            return table
    return next(iter(recipe.inputs))


def _reading(recipe: Recipe, table: str, names: _Names, main: bool = False) -> list[dict]:
    """一張輸入表怎麼讀：只把值得注意的規則列出來，其他欄位收在細節裡。"""
    spec = recipe.inputs[table]
    if spec.sheets:
        where = f"讀取所有名稱符合 {'、'.join(spec.sheets)} 的工作表，疊成一張表"
    elif spec.sheet:
        where = f"從工作表「{'」或「'.join(spec.sheet)}」讀取"
    else:
        where = "在所有工作表裡找符合的表頭"
    if spec.sheet_column:
        part = "工作表名稱" if spec.sheet_column.regex is None else f"工作表名稱中符合 {spec.sheet_column.regex.pattern} 的部分"
        where += f"，{part}放進「{spec.sheet_column.name}」"
    nodes = [_node(where, "note")]
    plain = []
    for column in spec.columns.values():
        label = column.aliases[0] if column.source is None else column.name
        if column.extract:
            branches = []
            for i, rule in enumerate(column.extract):
                text = _rule_text(rule)
                branches.append(_node(("先" if i == 0 else "找不到時改") + f"取{text}", "then" if i == 0 else "else"))
            branches.append(_node("都取不到 → 留空" + ("並標記需檢查" if column.required else ""), "else"))
            origin = f"從「{spec.columns[column.source].aliases[0]}」這一格" if column.source else ""
            nodes.append(_node(f"「{label}」{origin}只取一部分", "step", branches))
        elif column.map:
            mapping = recipe.mappings[column.map]
            nodes.append(_node(f"「{label}」查對照表 {column.map}", "step", [
                _node("查得到 → 換成對應值", "then"),
                _node(f"查不到 → {MISSING_LABELS[mapping.missing]}", "else")]))
        elif column.type in ("number", "integer") and (column.decimal == "," or column.strip):
            extra = "小數點是逗號（1.000,02）" if column.decimal == "," else f"去掉 {'、'.join(column.strip)} 再讀"
            nodes.append(_node(f"「{label}」當數字讀，{extra}；讀不懂 → 留空並標記需檢查", "note"))
        else:
            plain.append(column)
    required = [c.aliases[0] for c in spec.columns.values() if c.required and c.source is None]
    if required:
        nodes.append(_node(f"必填欄位：{'、'.join(required)}；空白 → 標記需檢查", "note"))
    if main:
        nodes.append(_node("數字、日期讀不懂時（例如「約 300」）一律留空並標記，原始內容保留給你看，不猜測", "note"))
    nodes.append(_node(f"所有欄位的讀法（{len(spec.columns)} 欄）", "detail",
                       [_node(_column_text(c, spec, recipe), "note") for c in spec.columns.values()]))
    return nodes


def _rule_text(rule) -> str:
    steps = []
    if rule.line is not None:
        steps.append(f"第 {rule.line} 行" if rule.line > 0 else f"倒數第 {-rule.line} 行")
    if rule.after:
        steps.append(f"「{'」或「'.join(rule.after)}」之後")
    if rule.before:
        steps.append(f"「{'」或「'.join(rule.before)}」之前")
    if rule.regex is not None:
        steps.append(f"符合 {rule.regex.pattern} 的部分")
    return "、".join(steps)


def _gates(recipe: Recipe, table: str, names: _Names) -> list[dict]:
    return [_node(f"只留下：{humanize(g.keep, names, g.input)}", "if",
                  [_node(f"其他列 → 排除，不處理（{g.label}）", "else")], g.keep)
            for g in recipe.gate if g.input == table]


def _matching(recipe: Recipe, match, names: _Names) -> dict:
    left, right = names.table(match.left), names.table(match.right)
    children = []
    for i, strategy in enumerate(match.strategies):
        condition = _pairs(strategy.on, names, match.left, match.right) or humanize(strategy.on, names, match.left, match.right)
        head = ("先找" if i == 0 else "再找") + f"：{condition}"
        if strategy.when:
            head += f"（只在{humanize(strategy.when, names, match.left, match.right)}時）"
        outcomes = []
        if match.multi:
            outcomes.append(_node("找到幾筆就全部算進來", "then"))
        else:
            outcomes.append(_node("找到 1 筆 → 配對", "then"))
            if strategy.best:
                outcomes.append(_node(f"找到多筆 → 挑「{humanize(strategy.best, names, match.left, match.right)}」最高的；"
                                      "分不出高下時請你選", "then"))
            else:
                outcomes.append(_node("找到多筆 → 不自動挑，請你選", "then"))
        if strategy.review:
            outcomes.append(_node("用這個方式配到的，要你確認", "note"))
        code = strategy.on + (f"\n-- when: {strategy.when}" if strategy.when else "") + (
            f"\n-- best: {strategy.best}" if strategy.best else "")
        pairs_only = _pairs(strategy.on, names, match.left, match.right) is not None and not strategy.when and not strategy.best
        children.append(_node(head, "if", outcomes, None if pairs_only else code))  # 欄位配對已經完整翻出來，不用附原文
    children.append(_node(f"都找不到 → {UNMATCHED_LABELS[match.unmatched]}", "else"))
    if match.mode in ("one_to_one", "one_to_many"):
        children.append(_node(f"同一筆{right}只能給一筆{left}；同時對到好幾筆時不替你決定，請你選", "note"))
    if match.multi:
        children.append(_node(f"對到多筆{right}時，" + ("彙總成一列" if match.rows == "combine" else "每一筆各成一列"), "note"))
    if match.bring:
        if match.rows == "combine":
            brought = "、".join(f"「{alias}」= {humanize(expr, names, None, match.right)}" for alias, expr in match.bring.items())
        else:
            brought = "、".join(names.column(match.right, src) for src in match.bring.values())
        children.append(_node(f"配到後帶入{right}的：{brought}", "note"))
    else:
        children.append(_node(f"配到後帶入{right}的所有欄位", "note"))
    label = names.table(match.name)
    return _node(f"找對應的{right}（{label}，{MODES[match.mode].split('：')[0]}）", "step", children)


def explain(recipe: Recipe) -> dict:
    """把 recipe 寫成「一列資料會經過哪些判斷」的流程，另外列出其他資料表的讀法。"""
    names = _Names(recipe)
    main = _main_input(recipe)
    main_label = names.table(main)
    flow = [_node(f"讀進{main_label}", "step", _reading(recipe, main, names, main=True))]
    gates = _gates(recipe, main, names)
    if gates:
        flow.append(_node("篩選", "step", gates))
    for match in recipe.match:
        flow.append(_matching(recipe, match, names))
    for step in recipe.transform:
        flow.append(_node(f"計算：{step.note or step.name}", "step",
                          [_node("以 SQL 計算，原文可展開查看", "note")], step.sql))
    if recipe.validate:
        flow.append(_node("檢查", "step", [
            _node(f"如果{humanize(c.where, names, c.table or recipe.output.source)}", "if",
                  [_node(f"標記「{c.message}」（{LEVEL_LABELS[c.level]}" + (f"，標在 {'、'.join(c.highlight)}" if c.highlight else "")
                         + "）", "then")], c.where)
            for c in recipe.validate]))
    outputs = []
    for column in recipe.output.columns:
        if column.map:
            mapping = recipe.mappings[column.map]
            outputs.append(_node(f"「{column.name}」查對照表 {column.map}", "step", [
                _node("查得到 → 換成對應值", "then"), _node(f"查不到 → {MISSING_LABELS[mapping.missing]}", "else")]))
    required = [c.name for c in recipe.output.columns if c.required]
    if required:
        outputs.append(_node(f"必填：{'、'.join(required)}；空白 → 標記需檢查", "note"))
    detail = []
    for column in recipe.output.columns:
        source = column.expr.strip('"') if column.expr.startswith('"') else None
        origin = (f"來自「{names.column(recipe.output.source, source)}」" if source
                  else f"計算：{humanize(column.expr, names, recipe.output.source)}")
        detail.append(_node(f"{column.name}：{origin}", "note"))
    head = f"輸出 {len(recipe.output.columns)} 欄到工作表「{recipe.output.sheet}」"
    if recipe.output.order_by:
        head += f"，依{humanize(recipe.output.order_by, names, recipe.output.source)}排序"
    outputs.append(_node("每一欄的來源", "detail", detail))
    flow.append(_node(head, "step", outputs))

    sources = []
    for table in recipe.inputs:
        if table == main:
            continue
        nodes = _reading(recipe, table, names) + _gates(recipe, table, names)
        sources.append(_node(names.table(table), "step", nodes))
    return {"name": recipe.name, "description": recipe.description, "subject": main_label,
            "flow": flow, "sources": sources}


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
