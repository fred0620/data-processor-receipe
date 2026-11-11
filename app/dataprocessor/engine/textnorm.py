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


_INLINE_SPACE = re.compile(r"[^\S\n]+")   # 換行以外的空白


def _collapse_space(text: str) -> str:
    """每一行裡的連續空白合成一個、去掉行首行尾空白；保留換行，連續空行只留一行。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [_INLINE_SPACE.sub(" ", line).strip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines))


TEXT_OPS = {
    "trim": lambda s: s.strip(),
    "upper": lambda s: s.upper(),
    "lower": lambda s: s.lower(),
    "halfwidth": halfwidth,
    "collapse_space": _collapse_space,
    "single_line": lambda s: _SPACE.sub(" ", s).strip(),
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
_DIGITS = re.compile(r"\d+")


def parse_number(raw: str | None, strip: list[str] | None = None, decimal: str = ".") -> float | None:
    """解析數字。支援千分位、全形、貨幣符號、括號負數、尾端負號、百分比（12% → 0.12）。

    decimal 是小數點符號：「.」時 1,000.02；「,」時 1.000,02（歐洲寫法）。千分位一定要三位一組，
    否則不解析：例如 decimal 是「.」時，1,5 或 1.000,02 都會失敗並標記，不會被讀成錯的數字。
    空白與單引號（1 000、1'000）一律當作千分位。其他文字（例如 12KG）不硬解析，要去掉的單位寫在 strip。"""
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
    text = re.sub(r"[\s'’\u00a0\u202f]", "", text)
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1]
    if text.endswith("-") and len(text) > 1:
        negative, text = True, text[:-1]
    percent = text.endswith("%")
    if percent:
        text = text[:-1]
    sign = ""
    if text[:1] in "+-":
        sign, text = text[:1], text[1:]
    group = "," if decimal == "." else "."
    if text.count(decimal) > 1:
        return None
    whole, _, fraction = text.partition(decimal)
    if group in whole and not re.fullmatch(rf"\d{{1,3}}({re.escape(group)}\d{{3}})+", whole):
        return None                        # 千分位不是三位一組，可能是另一種小數點寫法，不猜
    whole = whole.replace(group, "")
    if (whole and not _DIGITS.fullmatch(whole)) or (fraction and not _DIGITS.fullmatch(fraction)) or not (whole or fraction):
        if not re.fullmatch(r"\d+(\.\d+)?[eE][+-]?\d+", text):  # 科學記號（1.2E+5）
            return None
        value = float(text)
    else:
        value = float(f"{whole or 0}.{fraction or 0}")
    if sign == "-":
        value = -value
    if percent:
        value /= 100
    return -value if negative else value


# ---------- 從儲存格取一部分 ----------

def _keyword(word: str) -> re.Pattern:
    """關鍵字比對：全半形相同、不分大小寫、空白多寡不拘。"""
    parts = [re.escape(p) for p in halfwidth(word).split()]
    return re.compile(r"\s*".join(parts), re.IGNORECASE)


def extract(text: str | None, rules) -> str | None:
    return extract_with_rule(text, rules)[0]


def extract_with_rule(text: str | None, rules) -> tuple[str | None, int | None]:
    """依 recipe 的 extract 取值。多個寫法依序嘗試，第一個取得到值的就用；都取不到回傳 None。
    每個寫法依序套用：第幾行 → 關鍵字之後 → 關鍵字之前 → 正規表達式。
    第幾行、after、regex 對不到時，這個寫法就算失敗、換下一個；before 對不到時取到最後。"""
    if text is None:
        return None, None
    base = halfwidth(str(text)).replace("\r\n", "\n").replace("\r", "\n")
    for index, rule in enumerate(rules):
        value = base
        if rule.line is not None:
            lines = value.split("\n")
            position = rule.line - 1 if rule.line > 0 else len(lines) + rule.line   # 行的位置，和寫法的序號 index 分開
            if not 0 <= position < len(lines):
                continue
            value = lines[position]
        if rule.after:
            found = [m for m in (_keyword(w).search(value) for w in rule.after) if m]
            if not found:
                continue
            first = min(found, key=lambda m: m.start())
            value = re.sub(r"^\s*[:：=＝]?\s*", "", value[first.end():])   # 關鍵字後面的冒號、等號不帶進值
        if rule.before:   # 找不到結束的關鍵字時取到最後，例如有時候後面沒有「規格」
            found = [m for m in (_keyword(w).search(value) for w in rule.before) if m]
            if found:
                value = value[:min(m.start() for m in found)]
        if rule.regex is not None:
            match = rule.regex.search(value)
            if not match:
                continue
            value = match.group(1) if match.groups() else match.group(0)
        value = value.strip()
        if value:
            return value, index
    return None, None


def parse_integer(raw: str | None, strip: list[str] | None = None, decimal: str = ".") -> int | None:
    value = parse_number(raw, strip, decimal)
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
