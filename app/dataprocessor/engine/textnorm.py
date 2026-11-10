"""文字、數字、日期的整理規則。只做明確的轉換，判斷不了就回傳 None，由上層標記，不猜測。"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata

_SPACE = re.compile(r"\s+")
_KEY_DROP = re.compile(r"[\W_]+", re.UNICODE)  # 空白與標點


def halfwidth(text: str) -> str:
    """全形轉半形（NFKC），例如 ＡＩＲ１２３ → AIR123、全形空白 → 空白。"""
    return unicodedata.normalize("NFKC", text)


def key(text: object) -> str:
    """比對用的鍵：全半形視為相同、不分大小寫、忽略空白與標點。
    「空 運」「空運」、「AIr」「AIR」、「Invoice No.」「invoice_no」都會得到相同的鍵。"""
    if text is None:
        return ""
    return _KEY_DROP.sub("", halfwidth(str(text)).casefold())


TEXT_OPS = {
    "trim": lambda s: s.strip(),
    "upper": lambda s: s.upper(),
    "lower": lambda s: s.lower(),
    "halfwidth": halfwidth,
    "collapse_space": lambda s: _SPACE.sub(" ", s),
    "no_space": lambda s: _SPACE.sub("", s),
    "digits_only": lambda s: re.sub(r"\D", "", s),
    "alnum_only": lambda s: re.sub(r"[\W_]", "", s, flags=re.UNICODE),
}
DEFAULT_TEXT_OPS = ["trim", "collapse_space"]


def clean_text(raw: str | None, ops: list[str] | None = None,
               replace: list[tuple[re.Pattern, str]] | None = None) -> str | None:
    if raw is None:
        return None
    text = str(raw)
    for op in (ops if ops is not None else DEFAULT_TEXT_OPS):
        text = TEXT_OPS[op](text)
    for pattern, repl in replace or []:
        text = pattern.sub(repl, text)
    return text if text != "" else None


# ---------- 數字 ----------

CURRENCY_TOKENS = ["NT$", "US$", "HK$", "NTD", "TWD", "USD", "EUR", "JPY", "CNY", "RMB", "HKD", "GBP",
                   "$", "¥", "€", "£", "元", "圓"]
_NUMBER = re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?")


def parse_number(raw: str | None, strip: list[str] | None = None) -> float | None:
    """解析數字。支援千分位、全形、貨幣符號、括號負數、尾端負號、百分比（12% → 0.12）。
    其他文字（例如 12KG）不硬解析，回傳 None；需要去掉的單位寫在 recipe 的 strip。"""
    if raw is None:
        return None
    text = halfwidth(str(raw)).strip()
    if text == "":
        return None
    for token in sorted([*CURRENCY_TOKENS, *(strip or [])], key=len, reverse=True):
        token = halfwidth(token)
        if re.fullmatch(r"[A-Za-z]+", token):  # 英文代碼只去掉開頭或結尾，避免吃掉中間的字
            text = re.sub(rf"(?i)^{re.escape(token)}|{re.escape(token)}$", "", text.strip())
        else:
            text = text.replace(token, "")
    text = text.replace(",", "").replace(" ", "")
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1]
    if text.endswith("-") and len(text) > 1:
        negative, text = True, text[:-1]
    percent = text.endswith("%")
    if percent:
        text = text[:-1]
    if not _NUMBER.fullmatch(text):
        return None
    value = float(text)
    if percent:
        value /= 100
    return -value if negative else value


def parse_integer(raw: str | None, strip: list[str] | None = None) -> int | None:
    value = parse_number(raw, strip)
    if value is None or value != int(value):
        return None
    return int(value)


# ---------- 日期 ----------

_YMD = re.compile(r"(\d{2,4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?")
_COMPACT = re.compile(r"(\d{4})(\d{2})(\d{2})")


def parse_date(raw: str | None, formats: list[str] | None = None, roc: str = "auto") -> dt.date | None:
    """解析日期。支援 2026-01-05、2026/1/5、2026.1.5、20260105、民國 115/01/05、2026年1月5日，
    以及 recipe 指定的 strftime 格式。roc：auto（年份小於 1000 視為民國）、always、never。"""
    if raw is None:
        return None
    text = halfwidth(str(raw)).strip()
    if text == "":
        return None
    text = re.sub(r"[ T]\d{1,2}:\d{2}(:\d{2}(\.\d+)?)?$", "", text)  # Excel 日期常帶 00:00:00
    text = re.sub(r"^民國\s*", "", text)
    for fmt in formats or []:
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    found = _YMD.fullmatch(text) or _COMPACT.fullmatch(text)
    if not found:
        return None
    year, month, day = (int(part) for part in found.groups())
    if roc == "always" or (roc == "auto" and year < 1000):
        year += 1911
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None
