"""執行紀錄：說明某一列（或某一格）是怎麼來的。

平常不會看，使用者好奇或要覆核時才產生。內容全部來自執行當下的紀錄：
原始內容、怎麼整理、查了哪個對照、配對試了哪些方式、哪一步算出來、驗證有沒有過、有沒有人工修改。
"""
from __future__ import annotations

from .explain import _Names, humanize


def _display(value) -> str:
    if value is None or value == "":
        return "空白"
    if isinstance(value, float):
        return f"{value:,.6f}".rstrip("0").rstrip(".") if not value.is_integer() else f"{int(value):,}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _who(match: dict, rid: str) -> str:
    """右表一列的稱呼：單號加列號，例如「報關單 AA15A0002（第 3 列）」。"""
    record = match["right_rows"].get(rid)
    if record is None:
        return f"{match['right_label']} {rid}"
    title = "・".join(str(record["values"].get(k)) for k in match["right_title"] if record["values"].get(k) not in (None, ""))
    return f"{match['right_label']} {title}（第 {record['row']} 列）" if title else f"{match['right_label']}第 {record['row']} 列"


def _match_story(match: dict, decision: dict) -> list[str]:
    status, how = decision["status"], decision["how"]
    tried = match["strategies"]
    if status in ("manual", "none"):
        return [f"{match['label']}：你指定配到 " + "、".join(_who(match, r) for r in decision["rights"])] if status == "manual" \
            else [f"{match['label']}：你確認沒有對應的{match['right_label']}"]
    if status == "unmatched":
        return [f"{match['label']}：依序試了「{'」「'.join(tried)}」，都找不到"]
    index = tried.index(how) if how in tried else 0
    lines = [f"{match['label']}：" + (f"「{'」「'.join(tried[:index])}」找不到，改用「{how}」" if index else f"用「{how}」")]
    if status == "ambiguous":
        lines.append(f"　找到 {decision.get('total', len(decision['candidates']))} 筆，分不出是哪一筆，等你選")
    else:
        lines.append("　配到 " + "、".join(_who(match, r) for r in decision["rights"]))
        if decision.get("why"):
            lines.append(f"　{decision['why']}，要你確認")
        elif status == "review":
            lines.append("　這個方式配到的要你確認")
    if decision.get("dropped"):
        lines.append(f"　另有 {len(decision['dropped'])} 筆同時對到其他列，先拿掉等你決定")
    return lines


class _Shown:
    """驗證規則裡的欄位：結果表上有這一欄就用結果表的名稱，和細節、警示上看到的一致。"""

    def __init__(self, recipe, names: _Names):
        self.names = names
        self.output = {c.expr.strip('"'): c.name for c in recipe.output.columns if c.expr.startswith('"')}
        self.everything = {**names.everything, **self.output}

    def column(self, table, name: str) -> str:
        return self.output.get(name) or self.names.column(table, name)

    def table(self, name: str) -> str:
        return self.names.table(name)

    def __getattr__(self, attr):   # humanize 用到的其他屬性照舊
        return getattr(self.names, attr)


def trace(job, result: dict, row: dict) -> dict:
    recipe = job.recipe
    names = _Names(recipe)
    root = row.get("source") or ""
    table = root.split(":", 1)[0]
    spec = recipe.inputs.get(table)
    matches = {m["name"]: m for m in result["matches"]}

    shown = _Shown(recipe, names)
    steps: list[str] = []
    if spec:
        where = f"工作表「{row['sheet']}」第 {row['row']} 列" if row.get("sheet") else f"第 {row['row']} 列"
        steps.append(f"來自{spec.label}，{where}")
    for label in job.gate_labels.get(table, []):
        steps.append(f"通過篩選：{label}")
    for match in result["matches"]:
        decision = next((d for d in match["rows"] if d["left"] == root), None)
        if decision:
            steps.extend(_match_story(match, decision))
    for i, check in enumerate(recipe.validate):
        if i < len(job.check_hits):
            hit = root in job.check_hits[i]
            level = {"review": "需檢查", "notice": "提示"}[check.level]
            values = job.check_values[i].get(root) if i < len(job.check_values) else None
            steps.append(f"檢查「{check.message}」：" + (f"有 → 標記{level}" if hit else "沒問題"))
            if values:   # 標記過的列：寫出規則和用到的值，讓人自己算算看
                table = check.table or recipe.output.source
                steps.append(f"　規則：{humanize(check.where, shown, table)}")
                steps.append("　這一列：" + "、".join(f"{shown.column(table, c)} {_display(v)}" for c, v in values))

    columns: dict[str, list[str]] = {}
    for column in recipe.output.columns:
        lines: list[str] = []
        source = column.expr.strip('"') if column.expr.startswith('"') else None
        if source is None:
            lines.append(f"由運算式算出：{humanize(column.expr, names, recipe.output.source)}")
        elif source in job.created:
            step, note = job.created[source]
            lines.append(f"在計算步驟「{note or step}」算出")
        elif spec and source in spec.columns:
            lines.extend(job.cells.get((root, source), []))
        else:
            lines.extend(_brought(job, recipe, matches, row, source))
        trail = job.out_trail.get((row["rid"], column.name))
        if trail:
            lines.append(trail)
        if column.name in row["edited"]:
            lines.append(f"你改成「{_display(row['values'].get(column.name))}」（原值「{_display(row['edited'][column.name])}」）")
        else:
            value = row["values"].get(column.name)
            lines.append(f"結果：{_display(value)}" if value not in (None, "") or column.name not in row["raw"]
                         else f"結果：留空（原始內容「{row['raw'][column.name]}」）")
        columns[column.name] = lines
    return {"rid": row["rid"], "steps": steps, "columns": columns}


def _brought(job, recipe, matches: dict, row: dict, source: str) -> list[str]:
    """欄位是配對時從右表帶過來的：找出是哪一筆，再接上那一格的經過。"""
    for spec in recipe.match:
        if not spec.bring or source not in spec.bring:
            continue
        match = matches.get(spec.name)
        linked = row["links"].get(f"_rid_{spec.name}")
        if not linked:
            return [f"{spec.label or match['label']}沒有配到，所以是空白"] if match else ["沒有配到，所以是空白"]
        if spec.rows == "combine":
            count = len(linked.split(","))
            return [f"從配到的 {count} 筆{match['right_label']}彙總：{humanize(spec.bring[source], _Names(recipe), None, spec.right)}"]
        right_spec = recipe.inputs.get(spec.right)
        lines = [f"從配到的{_who(match, linked)}帶過來"]
        if right_spec:
            lines.extend("　" + line for line in job.cells.get((linked, spec.bring[source]), []))
        return lines
    return ["來自前面步驟的結果"]
