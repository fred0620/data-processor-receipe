"""把處理結果輸出成 Excel：整理結果、待檢查、配對明細、排除、對照待補。"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import BinaryIO

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
BOLD = Font(bold=True)
REVIEW_FILL = PatternFill("solid", fgColor="FDE7CF")
NOTICE_FILL = PatternFill("solid", fgColor="EEF2F7")
STATUS = {"ok": "正常", "review": "需檢查", "notice": "提示", "confirmed": "已確認"}
LEVEL = {"review": "需檢查", "notice": "提示", "error": "無法執行"}
MATCH_STATUS = {"auto": "自動配對", "review": "配對待確認", "confirmed": "配對已確認", "manual": "人工指定", "none": "人工確認沒有配對",
                "ambiguous": "多筆候選", "unmatched": "找不到"}


def _text(cell, value) -> None:
    """文字一律強制為文字格式，避免 = + - @ 開頭的內容被 Excel 當成公式。多行文字自動換行。"""
    cell.value = CONTROL.sub("", str(value))
    cell.data_type = "s"
    cell.number_format = "@"
    if "\n" in cell.value:
        cell.alignment = Alignment(wrap_text=True, vertical="top")


def _put(cell, value, kind: str = "text") -> None:
    if value is None or value == "":
        return
    if kind in ("number", "integer") and isinstance(value, (int, float)) and not isinstance(value, bool):
        cell.value = value
        cell.number_format = "#,##0" if kind == "integer" or float(value).is_integer() else "#,##0.00##"
    elif kind == "date" and isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        cell.value = dt.date.fromisoformat(value)
        cell.number_format = "yyyy-mm-dd"
    else:
        _text(cell, value)


def _header(sheet, names: list[str]) -> None:
    for i, name in enumerate(names, 1):
        cell = sheet.cell(row=1, column=i)
        _text(cell, name)
        cell.font = BOLD
    sheet.freeze_panes = "A2"


def _widths(sheet) -> None:
    for column in sheet.columns:
        longest = max((max(len(part) for part in str(c.value).split("\n")) * (2 if re.search(r"[^\x00-\x7f]", str(c.value or "")) else 1)
                       for c in column if c.value is not None), default=6)
        sheet.column_dimensions[get_column_letter(column[0].column)].width = min(max(longest + 2, 8), 60)


def export(result: dict, path: Path | BinaryIO) -> Path | BinaryIO:
    """path 可以是檔案路徑，或 BytesIO 之類的串流（直接送給瀏覽器下載，不落地）。"""
    book = Workbook()
    issues = result["issues"]
    output = result["output"]
    columns = output["columns"]

    sheet = book.active
    sheet.title = output.get("sheet") or "整理結果"
    _header(sheet, [c["name"] for c in columns] + ["檢查狀態", "問題說明", "來源列"])
    for r, row in enumerate(output["rows"], 2):
        active = [issues[i] for i in row["issues"] if not issues[i]["dismissed"]]
        for c, column in enumerate(columns, 1):
            cell = sheet.cell(row=r, column=c)
            _put(cell, row["values"].get(column["name"]), column["type"])
            flagged = [i for i in active if column["name"] in i["out_columns"]]
            if any(i["level"] == "review" for i in flagged):
                cell.fill = REVIEW_FILL
            elif flagged:
                cell.fill = NOTICE_FILL
            if column["name"] in row["edited"]:
                original = row["edited"][column["name"]]
                cell.comment = Comment(CONTROL.sub("", f"人工修改，原值：{'' if original is None else original}"),
                                       "資料處理器")
        _text(sheet.cell(row=r, column=len(columns) + 1), STATUS.get(row["status"], row["status"]))
        notes = []
        for issue in active:
            notes.append(issue["message"])
        for name, raw in row["raw"].items():
            notes.append(f"{name} 原始內容：{raw}")
        if notes:
            _text(sheet.cell(row=r, column=len(columns) + 2), "；".join(dict.fromkeys(notes)))
        if row.get("row"):
            sheet.cell(row=r, column=len(columns) + 3).value = row["row"]
    _widths(sheet)

    sheet = book.create_sheet("待檢查")
    _header(sheet, ["等級", "階段", "列代號", "欄位", "說明", "處理"])
    r = 2
    for issue in issues:
        if issue["level"] == "skip":
            continue
        values = [LEVEL.get(issue["level"], issue["level"]), issue["stage"], issue["rid"] or "",
                  "、".join(issue["out_columns"]) or (issue["column"] or ""), issue["message"],
                  issue.get("note") or ("已確認" if issue["dismissed"] else "")]
        for c, value in enumerate(values, 1):
            if value != "":
                _text(sheet.cell(row=r, column=c), value)
        r += 1
    _widths(sheet)

    if result["matches"]:
        sheet = book.create_sheet("配對明細")
        _header(sheet, ["配對", "左表列", "結果", "比對方式", "右表列", "候選"])
        r = 2
        for match in result["matches"]:
            for row in match["rows"]:
                values = [match.get("label", match["name"]), row["left"], MATCH_STATUS.get(row["status"], row["status"]), row["how"],
                          "、".join(row["rights"]), "、".join(c["rid"] for c in row["candidates"])
                          if row["status"] == "ambiguous" else ""]
                for c, value in enumerate(values, 1):
                    if value:
                        _text(sheet.cell(row=r, column=c), value)
                r += 1
            for rid in match["unused_right"]:
                for c, value in enumerate([match.get("label", match["name"]), "", "右表沒被用到", "", rid, ""], 1):
                    if value:
                        _text(sheet.cell(row=r, column=c), value)
                r += 1
        _widths(sheet)

    if result["excluded"]:
        sheet = book.create_sheet("排除")
        names = sorted({k for e in result["excluded"] for k in e["values"]})
        _header(sheet, ["輸入表", "Excel 列", "原因", *names])
        for r, row in enumerate(result["excluded"], 2):
            _text(sheet.cell(row=r, column=1), row["input"])
            sheet.cell(row=r, column=2).value = row["row"]
            _text(sheet.cell(row=r, column=3), row["label"])
            for c, name in enumerate(names, 4):
                if row["values"].get(name) is not None:
                    _text(sheet.cell(row=r, column=c), row["values"][name])
        _widths(sheet)

    pending = [u for u in result["unmapped"] if u["missing"] == "ask"]
    if pending:
        sheet = book.create_sheet("對照待補")
        _header(sheet, ["對照表", "原始值", "出現次數", "出現位置"])
        for r, entry in enumerate(pending, 2):
            _text(sheet.cell(row=r, column=1), entry["mapping"])
            _text(sheet.cell(row=r, column=2), entry["raw"])
            sheet.cell(row=r, column=3).value = entry["count"]
            _text(sheet.cell(row=r, column=4), "、".join(entry["places"]))
        _widths(sheet)

    if isinstance(path, Path):
        path.parent.mkdir(parents=True, exist_ok=True)
    book.save(path)
    return path
