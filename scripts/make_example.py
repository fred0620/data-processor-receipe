"""產生範例 workbook（app/examples/workspace/samples），示範常見的髒資料。

    uv run --project app python scripts/make_example.py
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "app" / "examples" / "workspace" / "samples" / "範例_發票與報關單.xlsx"

INVOICES = [
    # 發票號碼, 發票日期, 品名, 數量, 金額, 幣別, 運送方式, 狀態
    ("INV-1001", dt.date(2026, 1, 5), "不鏽鋼螺絲 M6", 1000, 1200, "USD", "空運", None),
    ("inv 1002", "115/01/06", "鋁合金支架", 50, "USD 3,450.00", "usd", "AIr", None),
    ("INV-1003", "2026/1/7", "電源供應器 500W\n附電源線 1.8M\n保固一年", 20, "2,000", "ＵＳＤ", "海 運", None),
    ("1004", "2026-01-08", "散熱風扇 120mm", 300, 900, "JPY", "快遞", None),
    ("INV-1005", "2026.01.09", "控制板 V2", 10, "(150)", "USD", "陸運", None),
    ("INV-1006", "2026/01/10", "線材組", 5, "約 300", "USD", "空運", None),
    ("INV-1007", "2026/01/11", "包材", 100, 80, "USD", "海運", "作廢"),
    ("INV-1008", "2026/01/12", "感測器模組", 40, 640, "EUR", "空運", None),
    ("INV-1009", "2026/01/13", "LED 燈條", 200, 500, "USD", "空運", None),
    ("INV-1010", "2026/01/14", "LED 燈條 5M", 200, 500, "USD", "空運", None),
]
DECLARATIONS = [
    # 報單號碼, 發票參考, 申報日期, 貨名, 申報金額, 運輸方式
    ("AA15A0001", "INV-1001", dt.date(2026, 1, 6), "不鏽鋼螺絲", 1200, "AIR"),
    ("AA15A0002", "INV1002", "2026/01/07", "鋁合金支架", 3450, "空運"),
    ("AA15A0003", "INV-1003", "2026/01/08", "電源供應器", 2100, "海運"),
    ("AA15A0004", "INV-1004", "2026/01/09", "散熱風扇", 900, "Courier"),
    ("AA15A0005", None, "2026/01/14", "LED燈條", 500, "AIR"),
    ("AA15A0006", None, "2026/01/15", "LED 燈條", 500, "AIR"),
    ("AA15A0007", "INV-1099", "2026/01/15", "其他貨物", 99, "SEA"),
]
FX = [("USD", 32.1), ("JPY", 0.21), ("EUR", 34.8)]


def main() -> None:
    book = Workbook()
    sheet = book.active
    sheet.title = "發票明細"
    sheet.append(["2026 年 1 月出貨明細"])
    sheet.append([])
    sheet.append(["發票號碼", "發票日期", "品名", "數量", "金額", "幣別", "運送方式", "狀態"])
    for row in INVOICES:
        sheet.append(list(row))
    sheet = book.create_sheet("報關單")
    sheet.append(["報單號碼", "發票參考", "申報日期", "貨名", "申報金額", "運輸方式"])
    for row in DECLARATIONS:
        sheet.append(list(row))
    sheet = book.create_sheet("匯率")
    sheet.append(["幣別", "匯率"])
    for row in FX:
        sheet.append(list(row))
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    book.save(TARGET)
    print("完成", TARGET.relative_to(ROOT))


if __name__ == "__main__":
    main()
