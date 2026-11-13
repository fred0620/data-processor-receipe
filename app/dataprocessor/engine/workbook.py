"""讀取 Excel workbook，依 recipe 的欄位別名找出工作表與表頭。"""
from __future__ import annotations

import datetime as dt
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import load_workbook

from .textnorm import key

HEADER_SCAN_ROWS = 30
MAX_ROWS = 200_000
MAX_UNZIPPED = 1024 * 1024 * 1024   # xlsx 是 zip：解壓後超過 1 GB 就不讀，避免一個小檔吃光記憶體
MAX_RATIO = 200                      # 單一檔案的壓縮比；正常的工作表遠低於這個值


@dataclass
class Sheet:
    name: str
    rows: list[list[str | None]]  # rows[0] 是 Excel 第 1 列


@dataclass
class Located:
    sheet: str
    header_row: int                 # Excel 列號
    columns: dict[str, int]         # recipe 欄位 → 欄位位置（0 起算）
    headers: dict[str, str]         # recipe 欄位 → 實際表頭文字
    missing: list[str] = field(default_factory=list)


def cell_text(value: object) -> str | None:
    """把儲存格的值轉成原始文字。數字不加千分位，日期轉成 ISO 格式。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() and abs(value) < 1e15 else format(value, ".15g")
    if isinstance(value, dt.datetime):
        return value.date().isoformat() if value.time() == dt.time() else value.isoformat(sep=" ")
    if isinstance(value, (dt.date, dt.time)):
        return value.isoformat()
    text = str(value)
    return text if text.strip() != "" else None


def check_archive(path: Path) -> None:
    """讀之前先看 zip 的目錄：解壓後的大小與壓縮比異常就拒絕，不用真的解開。"""
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
    except zipfile.BadZipFile:
        raise ValueError("這不是有效的 Excel 檔案") from None
    total = sum(m.file_size for m in members)
    if total > MAX_UNZIPPED:
        raise ValueError("這個 Excel 解壓後超過 1 GB，請先拆檔")
    for member in members:
        if member.file_size > 10 * 1024 * 1024 and member.file_size > MAX_RATIO * max(member.compress_size, 1):
            raise ValueError("這個 Excel 的內容異常（壓縮比過高），可能已損毀，請重新另存後再試")


def read_workbook(path: Path) -> list[Sheet]:
    check_archive(path)
    book = load_workbook(path, read_only=True, data_only=True)
    try:
        sheets = []
        for ws in book.worksheets:
            rows = []
            for row in ws.iter_rows(values_only=True):
                rows.append([cell_text(v) for v in row])
                if len(rows) > MAX_ROWS:
                    raise ValueError(f"工作表「{ws.title}」超過 {MAX_ROWS} 列，請先拆檔")
            while rows and not any(rows[-1]):
                rows.pop()
            sheets.append(Sheet(ws.title, rows))
        return sheets
    finally:
        book.close()


def locate(sheets: list[Sheet], wanted_sheets: list[str], header_row: int | None,
           aliases: dict[str, list[str]]) -> Located | None:
    """找出表頭位置：在候選工作表的前幾列，挑對到最多欄位別名的那一列。
    別名比對不分全半形、大小寫、空白與標點，但必須整格相同，不做模糊猜測。"""
    alias_keys = {column: {key(a) for a in names} for column, names in aliases.items()}
    wanted = {key(name) for name in wanted_sheets}
    candidates = [s for s in sheets if not wanted or key(s.name) in wanted]
    best: Located | None = None
    for sheet in candidates:
        rows = [header_row] if header_row else range(1, min(len(sheet.rows), HEADER_SCAN_ROWS) + 1)
        for number in rows:
            if number > len(sheet.rows):
                continue
            found: dict[str, int] = {}
            headers: dict[str, str] = {}
            for index, cell in enumerate(sheet.rows[number - 1]):
                cell_key = key(cell)
                if not cell_key:
                    continue
                for column, keys in alias_keys.items():
                    if column not in found and cell_key in keys:
                        found[column], headers[column] = index, str(cell)
                        break
            if found and (best is None or len(found) > len(best.columns)):
                best = Located(sheet.name, number, found, headers)
    if best:
        best.missing = [c for c in aliases if c not in best.columns]
    return best


def data_rows(sheet: Sheet, located: Located) -> list[tuple[int, dict[str, str | None]]]:
    """表頭下方的資料列，回傳 (Excel 列號, {recipe 欄位: 原始文字})；整列空白的略過。"""
    result = []
    for number in range(located.header_row + 1, len(sheet.rows) + 1):
        row = sheet.rows[number - 1]
        values = {c: (row[i] if i < len(row) else None) for c, i in located.columns.items()}
        if any(v is not None and str(v).strip() for v in values.values()):
            result.append((number, values))
    return result
