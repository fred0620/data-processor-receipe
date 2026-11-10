"""讀取與檢查 recipe。

recipe 是 YAML，只描述資料怎麼處理，不含 Python。檢查時把所有問題一次列出，
訊息寫成「位置：說明」，使用者可以整段複製回去給 AI 修改。完整規格見 docs/recipe-spec.md。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import duckdb
import yaml

from .textnorm import TEXT_OPS

SPEC_VERSION = 1
NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,47}")
RECIPE_ID = re.compile(r"[\w\-]{1,64}")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
SQL_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")  # SQL 可以換行


class _Loader(yaml.SafeLoader):
    """YAML 1.1 會把 on、off、yes、no 當成布林值（on: 會變成 True:），這裡只認 true、false。"""


_Loader.yaml_implicit_resolvers = {
    first: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:bool"]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()}
_Loader.add_implicit_resolver("tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
                              list("tTfF"))


def _refuse_extras(loader: _Loader) -> None:
    """recipe 用不到錨點（&）、別名（*）與 !! 標籤，一律拒絕：
    別名可以用很小的檔案展開成巨大的資料；標籤是 YAML 被拿來執行程式的入口。"""
    event = loader.peek_event()
    line = event.start_mark.line + 1
    if isinstance(event, yaml.AliasEvent):
        raise RecipeError([f"第 {line} 行：recipe 不能使用別名（*{event.anchor}），請把內容直接寫出來"])
    if getattr(event, "anchor", None):
        raise RecipeError([f"第 {line} 行：recipe 不能使用錨點（&{event.anchor}），請把內容直接寫出來"])
    tag = getattr(event, "tag", None)
    if tag and tag != "!":
        raise RecipeError([f"第 {line} 行：recipe 不能使用標籤（{tag}），請拿掉 ! 開頭的寫法"])


_compose_node = _Loader.compose_node


def _safe_compose(self, parent, index):
    _refuse_extras(self)
    return _compose_node(self, parent, index)


_Loader.compose_node = _safe_compose
WINDOWS_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
TYPES = {"text", "number", "integer", "date"}
LEVELS = {"review", "notice"}


class RecipeError(Exception):
    """recipe 有問題。problems 是「位置：說明」的清單。"""

    def __init__(self, problems: list[str]):
        super().__init__("\n".join(problems))
        self.problems = problems


# ---------- 結構 ----------

@dataclass
class Column:
    name: str
    aliases: list[str]
    type: str = "text"
    required: bool = False
    text: list[str] | None = None
    replace: list[tuple[re.Pattern, str]] = field(default_factory=list)
    strip: list[str] = field(default_factory=list)
    formats: list[str] = field(default_factory=list)
    roc: str = "auto"
    map: str | None = None
    decimal: str = "."                                  # 小數點符號；"," 時 1.000,02 = 1000.02
    extract: list["Extract"] = field(default_factory=list)  # 從儲存格裡取一部分，多個寫法依序嘗試
    source: str | None = None                            # 取用另一個欄位的儲存格（同一格拆成多欄）


@dataclass
class Extract:
    line: int | None = None          # 第幾行（1 起算，負數從最後一行算）
    after: list[str] = field(default_factory=list)    # 取這些關鍵字之後的文字（任一個符合即可）
    before: list[str] = field(default_factory=list)   # 取到這些關鍵字之前
    regex: re.Pattern | None = None  # 正規表達式；有括號時取第一組


@dataclass
class SheetColumn:
    name: str
    regex: re.Pattern | None = None


@dataclass
class Input:
    name: str
    sheet: list[str]
    header_row: int | None
    columns: dict[str, Column]
    sheets: list[str] = field(default_factory=list)      # 工作表名稱的萬用字元（item_*），符合的全部疊在一起
    sheet_column: SheetColumn | None = None              # 把工作表名稱（或其中一段）放進一個欄位


@dataclass
class Gate:
    input: str
    keep: str
    label: str


@dataclass
class Mapping:
    name: str
    values: list[str] | None
    entries: dict[str, list[str]]
    missing: str = "ask"


@dataclass
class Strategy:
    label: str
    on: str
    when: str | None = None
    best: str | None = None
    review: bool = False


MODES = {
    "one_to_one": "一對一：左右兩邊各只能用一次",
    "many_to_one": "多對一：左表每列最多對一列，右表可以重複使用",
    "one_to_many": "一對多：左表每列可以對多列，右表每列只屬於一個左表列",
    "many_to_many": "多對多：兩邊都可以對多列",
}


@dataclass
class Match:
    name: str
    left: str
    right: str
    mode: str
    strategies: list[Strategy]
    bring: dict[str, str] | None
    unmatched: str
    rows: str = "expand"              # 對到多列時：expand（每組配對一列）或 combine（彙總成一列）
    show: dict[str, list[str]] = field(default_factory=dict)  # 配對畫面優先顯示的欄位

    @property
    def multi(self) -> bool:
        """左表一列可以對到多列右表。"""
        return self.mode in ("one_to_many", "many_to_many")


@dataclass
class Transform:
    name: str
    sql: str
    note: str = ""


@dataclass
class Check:
    table: str | None
    where: str
    message: str
    level: str = "review"
    highlight: list[str] = field(default_factory=list)


@dataclass
class OutputColumn:
    name: str
    expr: str
    type: str = "text"
    map: str | None = None
    required: bool = False
    editable: bool = True


@dataclass
class Output:
    source: str
    sheet: str
    columns: list[OutputColumn]
    order_by: str | None = None


@dataclass
class Recipe:
    id: str
    name: str
    description: str
    inputs: dict[str, Input]
    gate: list[Gate]
    mappings: dict[str, Mapping]
    match: list[Match]
    transform: list[Transform]
    validate: list[Check]
    output: Output
    text: str = ""

    def tables(self) -> list[str]:
        return [*self.inputs, *(m.name for m in self.match), *(t.name for t in self.transform)]


# ---------- 檢查工具 ----------

class _Checker:
    def __init__(self) -> None:
        self.problems: list[str] = []

    def fail(self, where: str, message: str) -> None:
        self.problems.append(f"{where}：{message}")

    def mapping(self, value: Any, where: str, allowed: set[str], required: set[str] = frozenset()) -> dict:
        if not isinstance(value, dict):
            self.fail(where, "要是 key: value 的物件")
            return {}
        for key in value:
            if key not in allowed:
                hint = "、".join(sorted(allowed))
                self.fail(f"{where}.{key}", f"不認得這個設定，可以用的有：{hint}")
        for key in required:
            if key not in value:
                self.fail(where, f"缺少 {key}")
        return value

    def text(self, value: Any, where: str, required: bool = True, limit: int = 200,
             control: re.Pattern = CONTROL) -> str | None:
        if value is None:
            if required:
                self.fail(where, "不能空白")
            return None
        if not isinstance(value, (str, int, float)) or isinstance(value, bool):
            self.fail(where, "要是文字")
            return None
        value = str(value)
        if len(value) > limit or control.search(value):
            self.fail(where, f"最多 {limit} 字，不能有控制字元")
            return None
        return value

    def name(self, value: Any, where: str) -> str | None:
        if not isinstance(value, str) or not NAME.fullmatch(value):
            self.fail(where, f"名稱「{value}」要英文字母開頭，只用英數與底線，最多 48 字（給 SQL 使用）")
            return None
        if value.lower().startswith(("dp_", "_")):
            self.fail(where, f"名稱「{value}」不能以 dp_ 或底線開頭（保留給系統）")
            return None
        return value

    def str_list(self, value: Any, where: str) -> list[str]:
        if value is None:
            return []
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            value = [value]
        if not isinstance(value, list):
            self.fail(where, "要是文字或文字清單")
            return []
        return [text for i, item in enumerate(value) if (text := self.text(item, f"{where}[{i}]")) is not None]

    def sql(self, value: Any, where: str, kind: str = "expr") -> str | None:
        """SQL 只允許單一 SELECT；運算式包成 SELECT 檢查語法，避免夾帶其他指令。"""
        text = self.text(value, where, limit=8000, control=SQL_CONTROL)
        if text is None:
            return None
        statement = text if kind == "select" else f"SELECT ({text})"
        try:
            parsed = duckdb.extract_statements(statement)
        except duckdb.Error as exc:
            self.fail(where, f"SQL 語法錯誤：{_short(exc)}")
            return None
        if len(parsed) != 1 or parsed[0].type != duckdb.StatementType.SELECT:
            self.fail(where, "只能寫一段 SELECT（或一個運算式），不能有分號或其他指令")
            return None
        return text


def _short(exc: Exception) -> str:
    return str(exc).splitlines()[0][:300]


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


# ---------- 讀取 ----------

def load_recipe(text: str) -> Recipe:
    try:
        data = yaml.load(text, Loader=_Loader)  # noqa: S506  _Loader 繼承 SafeLoader
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f"第 {mark.line + 1} 行" if mark else "YAML"
        raise RecipeError([f"{where}：YAML 格式錯誤（{getattr(exc, 'problem', '') or exc}）"]) from None
    check = _Checker()
    data = check.mapping(data, "recipe", {"recipe", "id", "name", "description", "inputs", "gate", "mappings",
                                          "match", "transform", "validate", "output"},
                         {"recipe", "id", "inputs", "output"})
    if check.problems and not data:
        raise RecipeError(check.problems)
    if data.get("recipe") != SPEC_VERSION:
        check.fail("recipe", f"規格版本要寫 {SPEC_VERSION}")
    recipe_id = str(data.get("id", ""))
    if not RECIPE_ID.fullmatch(recipe_id) or recipe_id.lower() in WINDOWS_RESERVED:
        check.fail("id", "只能用文字、數字、底線與連字號，最多 64 字，不能是 Windows 保留名稱")
    name = check.text(data.get("name", recipe_id), "name", limit=80) or recipe_id
    description = check.text(data.get("description", ""), "description", required=False, limit=2000) or ""

    mappings = _mappings(check, data.get("mappings") or {})
    inputs = _inputs(check, data.get("inputs"), mappings)
    gate = _gate(check, data.get("gate") or [], inputs)
    tables = set(inputs)
    match = _match(check, data.get("match") or [], tables)
    transform = _transform(check, data.get("transform") or [], tables)
    output = _output(check, data.get("output"), tables, mappings)
    validate = _validate(check, data.get("validate") or [], tables, output)
    if check.problems:
        raise RecipeError(check.problems)
    return Recipe(recipe_id, name, description, inputs, gate, mappings, match, transform, validate, output, text)


def _mappings(check: _Checker, raw: Any) -> dict[str, Mapping]:
    result: dict[str, Mapping] = {}
    if not isinstance(raw, dict):
        check.fail("mappings", "要是「對照表名稱: 設定」的物件")
        return result
    for table, spec in raw.items():
        where = f"mappings.{table}"
        if check.name(table, where) is None:
            continue
        spec = check.mapping(spec, where, {"values", "entries", "missing"})
        values = check.str_list(spec.get("values"), f"{where}.values") if "values" in spec else None
        entries: dict[str, list[str]] = {}
        raw_entries = spec.get("entries") or {}
        if not isinstance(raw_entries, dict):
            check.fail(f"{where}.entries", "要是「對應值: [原始寫法, ...]」的物件")
            raw_entries = {}
        for target, variants in raw_entries.items():
            target = check.text(target, f"{where}.entries")
            if target is None:
                continue
            if values is not None and target not in values:
                check.fail(f"{where}.entries.{target}", "不在 values 列出的值裡")
            entries[target] = check.str_list(variants, f"{where}.entries.{target}")
        missing = spec.get("missing", "ask")
        if missing not in ("ask", "keep", "blank"):
            check.fail(f"{where}.missing", "只能是 ask（標記待補）、keep（保留原值）、blank（留空）")
        result[table] = Mapping(table, values, entries, missing)
    return result


def _inputs(check: _Checker, raw: Any, mappings: dict[str, Mapping]) -> dict[str, Input]:
    result: dict[str, Input] = {}
    if not isinstance(raw, dict) or not raw:
        check.fail("inputs", "至少要定義一張輸入表")
        return result
    for table, spec in raw.items():
        where = f"inputs.{table}"
        if check.name(table, where) is None:
            continue
        spec = check.mapping(spec, where, {"sheet", "sheets", "sheet_column", "header_row", "columns"}, {"columns"})
        if spec.get("sheet") and spec.get("sheets"):
            check.fail(where, "sheet（挑一張）和 sheets（全部疊起來）只能擇一")
        sheets = check.str_list(spec.get("sheets"), f"{where}.sheets")
        sheet_column = None
        if spec.get("sheet_column") is not None:
            sc = spec["sheet_column"]
            if isinstance(sc, str):
                sc = {"name": sc}
            sc = check.mapping(sc, f"{where}.sheet_column", {"name", "regex"}, {"name"})
            sc_name = check.name(sc.get("name"), f"{where}.sheet_column.name")
            pattern = _regex(check, sc.get("regex"), f"{where}.sheet_column.regex") if sc.get("regex") else None
            if sc_name:
                sheet_column = SheetColumn(sc_name, pattern)
        header_row = spec.get("header_row")
        if header_row not in (None, "auto") and (not isinstance(header_row, int) or not 1 <= header_row <= 1000):
            check.fail(f"{where}.header_row", "要是 1 到 1000 的列號，或 auto")
        columns: dict[str, Column] = {}
        raw_columns = spec.get("columns")
        if not isinstance(raw_columns, dict) or not raw_columns:
            check.fail(f"{where}.columns", "至少要有一個欄位")
            raw_columns = {}
        for column, cspec in raw_columns.items():
            cwhere = f"{where}.columns.{column}"
            if check.name(column, cwhere) is None:
                continue
            if cspec is None:
                cspec = {}
            if isinstance(cspec, (str, list)):
                cspec = {"aliases": cspec}
            cspec = check.mapping(cspec, cwhere, {"aliases", "type", "required", "text", "replace", "strip",
                                                  "formats", "roc", "map", "decimal", "extract", "source"})
            columns[column] = _column(check, column, cspec, cwhere, mappings)
        for column in columns.values():
            if column.source is not None:
                target = columns.get(column.source)
                if target is None or target.source is not None:
                    check.fail(f"{where}.columns.{column.name}.source", f"「{column.source}」要是同一張表、有自己表頭的欄位")
        if sheet_column and sheet_column.name in columns:
            check.fail(f"{where}.sheet_column.name", f"「{sheet_column.name}」和欄位名稱重複")
        result[table] = Input(table, check.str_list(spec.get("sheet"), f"{where}.sheet"),
                              header_row if isinstance(header_row, int) else None, columns, sheets, sheet_column)
    return result


def _regex(check: _Checker, value: Any, where: str) -> re.Pattern | None:
    text = check.text(value, where, limit=500)
    if text is None:
        return None
    try:
        return re.compile(text)
    except re.error as exc:
        check.fail(where, f"正規表達式錯誤：{exc}")
        return None


def _extracts(check: _Checker, raw: Any, where: str) -> list[Extract]:
    """extract 可以是一個寫法，或多個寫法的清單（依序嘗試，第一個取得到值的就用）。"""
    items = raw if isinstance(raw, list) else [raw]
    result = []
    for i, item in enumerate(items):
        iwhere = f"{where}[{i}]" if isinstance(raw, list) else where
        item = check.mapping(item, iwhere, {"line", "after", "before", "regex"})
        if not item:
            check.fail(iwhere, "至少要有 line、after、before、regex 其中一個")
            continue
        line = item.get("line")
        if line is not None and (not isinstance(line, int) or isinstance(line, bool) or line == 0):
            check.fail(f"{iwhere}.line", "要是不為 0 的整數（1 是第一行，-1 是最後一行）")
            line = None
        pattern = _regex(check, item["regex"], f"{iwhere}.regex") if item.get("regex") is not None else None
        result.append(Extract(line, check.str_list(item.get("after"), f"{iwhere}.after"),
                              check.str_list(item.get("before"), f"{iwhere}.before"), pattern))
    return result


def _column(check: _Checker, name: str, spec: dict, where: str, mappings: dict[str, Mapping]) -> Column:
    column_type = spec.get("type", "text")
    if column_type not in TYPES:
        check.fail(f"{where}.type", "只能是 text、number、integer、date")
    ops = None
    if "text" in spec:
        ops = check.str_list(spec.get("text"), f"{where}.text")
        for op in ops:
            if op not in TEXT_OPS:
                check.fail(f"{where}.text", f"不認得「{op}」，可以用：{'、'.join(TEXT_OPS)}")
    replace = []
    for i, pair in enumerate(spec.get("replace") or []):
        if not (isinstance(pair, list) and len(pair) == 2 and all(isinstance(p, str) for p in pair)):
            check.fail(f"{where}.replace[{i}]", "要是 [正規表達式, 取代文字]")
            continue
        try:
            replace.append((re.compile(pair[0]), pair[1]))
        except re.error as exc:
            check.fail(f"{where}.replace[{i}]", f"正規表達式錯誤：{exc}")
    roc = spec.get("roc", "auto")
    if roc not in ("auto", "always", "never"):
        check.fail(f"{where}.roc", "只能是 auto、always、never")
    map_name = spec.get("map")
    if map_name is not None and map_name not in mappings:
        check.fail(f"{where}.map", f"找不到對照表「{map_name}」，要先定義在 mappings")
    if map_name is not None and column_type != "text":
        check.fail(f"{where}.map", "對照表只能用在 text 欄位")
    decimal = spec.get("decimal", ".")
    if decimal not in (".", ","):
        check.fail(f"{where}.decimal", "只能是 \".\"（1,000.02）或 \",\"（1.000,02）")
    if "decimal" in spec and column_type not in ("number", "integer"):
        check.fail(f"{where}.decimal", "只能用在 number 或 integer 欄位")
    source = spec.get("source")
    if source is not None:
        source = check.name(source, f"{where}.source")
        if "aliases" in spec:
            check.fail(where, "有 source 時不用寫 aliases（直接用來源欄位的儲存格）")
    extract = _extracts(check, spec["extract"], f"{where}.extract") if spec.get("extract") is not None else []
    aliases = check.str_list(spec.get("aliases"), f"{where}.aliases") or [name]
    return Column(name, aliases, column_type, bool(spec.get("required", False)), ops, replace,
                  check.str_list(spec.get("strip"), f"{where}.strip"),
                  check.str_list(spec.get("formats"), f"{where}.formats"), roc, map_name, decimal, extract, source)


def _gate(check: _Checker, raw: Any, inputs: dict[str, Input]) -> list[Gate]:
    result = []
    if not isinstance(raw, list):
        check.fail("gate", "要是清單")
        return result
    for i, spec in enumerate(raw):
        where = f"gate[{i}]"
        spec = check.mapping(spec, where, {"input", "keep", "label"}, {"input", "keep"})
        if spec.get("input") not in inputs:
            check.fail(f"{where}.input", f"找不到輸入表「{spec.get('input')}」")
        keep = check.sql(spec.get("keep"), f"{where}.keep")
        label = check.text(spec.get("label", "不符合篩選條件"), f"{where}.label", limit=80)
        if keep and label and spec.get("input") in inputs:
            result.append(Gate(spec["input"], keep, label))
    return result


def _match(check: _Checker, raw: Any, tables: set[str]) -> list[Match]:
    result = []
    if not isinstance(raw, list):
        check.fail("match", "要是清單")
        return result
    for i, spec in enumerate(raw):
        where = f"match[{i}]"
        spec = check.mapping(spec, where, {"name", "left", "right", "mode", "strategies", "bring", "unmatched",
                                           "rows", "show"},
                             {"name", "left", "right", "strategies"})
        name = check.name(spec.get("name"), f"{where}.name")
        for side in ("left", "right"):
            if spec.get(side) not in tables:
                check.fail(f"{where}.{side}", f"找不到表「{spec.get(side)}」（要是 inputs 或前面步驟的名稱）")
        mode = spec.get("mode", "many_to_one")
        if mode not in MODES:
            check.fail(f"{where}.mode", "只能是 " + "、".join(f"{k}（{v}）" for k, v in MODES.items()))
        rows = spec.get("rows", "expand")
        if rows not in ("expand", "combine"):
            check.fail(f"{where}.rows", "只能是 expand（每組配對一列）或 combine（彙總成一列）")
        if rows == "combine" and mode not in ("one_to_many", "many_to_many"):
            check.fail(f"{where}.rows", "combine 只用在 one_to_many 或 many_to_many")
        show = spec.get("show") or {}
        if not isinstance(show, dict) or set(show) - {"left", "right"}:
            check.fail(f"{where}.show", "要是 {left: [欄位], right: [欄位]}")
            show = {}
        show = {side: [c for c in check.str_list(show.get(side), f"{where}.show.{side}")] for side in show}
        unmatched = spec.get("unmatched", "flag")
        if unmatched not in ("flag", "keep", "drop"):
            check.fail(f"{where}.unmatched", "只能是 flag、keep、drop")
        bring = spec.get("bring")
        if bring is not None:
            if isinstance(bring, list):
                bring = {str(c): str(c) for c in bring}
            if not isinstance(bring, dict):
                check.fail(f"{where}.bring", "要是「新欄位名稱: 右表欄位」的物件，或右表欄位清單")
                bring = None
            else:
                for new, source in bring.items():
                    check.name(new, f"{where}.bring.{new}")
                    if rows == "combine":   # 彙總時 bring 的值是彙總運算式，例如 sum(r.amount)
                        bring[new] = check.sql(source, f"{where}.bring.{new}") or ""
                    else:
                        check.name(source, f"{where}.bring.{new}")
        elif rows == "combine":
            check.fail(f"{where}.bring", "combine 要寫 bring，例如 {decl_total: sum(r.amount), decl_nos: string_agg(r.decl_no, '、')}")
        strategies = []
        raw_strategies = spec.get("strategies")
        if not isinstance(raw_strategies, list) or not raw_strategies:
            check.fail(f"{where}.strategies", "至少要有一個比對方式")
            raw_strategies = []
        for j, sspec in enumerate(raw_strategies):
            swhere = f"{where}.strategies[{j}]"
            sspec = check.mapping(sspec, swhere, {"label", "on", "when", "best", "review"}, {"on"})
            on = _condition(check, sspec.get("on"), f"{swhere}.on")
            when = check.sql(sspec["when"], f"{swhere}.when") if sspec.get("when") is not None else None
            best = check.sql(sspec["best"], f"{swhere}.best") if sspec.get("best") is not None else None
            label = check.text(sspec.get("label", f"方式 {j + 1}"), f"{swhere}.label", limit=80)
            if on and label:
                strategies.append(Strategy(label, on, when, best, bool(sspec.get("review", False))))
        if name:
            if name in tables:
                check.fail(f"{where}.name", f"名稱「{name}」重複")
            tables.add(name)
            if strategies and spec.get("left") in tables and spec.get("right") in tables:
                result.append(Match(name, spec["left"], spec["right"], mode, strategies, bring, unmatched, rows, show))
    return result


def _condition(check: _Checker, raw: Any, where: str) -> str | None:
    """on 可以是欄位配對清單 [[左欄, 右欄], ...]（等值比對），或 SQL 條件（l. 代表左表、r. 代表右表）。"""
    if isinstance(raw, list):
        parts = []
        for i, pair in enumerate(raw):
            if isinstance(pair, str):
                pair = [pair, pair]
            if not (isinstance(pair, list) and len(pair) == 2):
                check.fail(f"{where}[{i}]", "要是 [左表欄位, 右表欄位]")
                return None
            left, right = (check.name(p, f"{where}[{i}]") for p in pair)
            if not left or not right:
                return None
            parts.append(f"l.{quote(left)} = r.{quote(right)}")
        if not parts:
            check.fail(where, "不能是空的")
            return None
        return " AND ".join(parts)
    return check.sql(raw, where)


def _transform(check: _Checker, raw: Any, tables: set[str]) -> list[Transform]:
    result = []
    if not isinstance(raw, list):
        check.fail("transform", "要是清單")
        return result
    for i, spec in enumerate(raw):
        where = f"transform[{i}]"
        spec = check.mapping(spec, where, {"name", "sql", "note"}, {"name", "sql"})
        name = check.name(spec.get("name"), f"{where}.name")
        sql = check.sql(spec.get("sql"), f"{where}.sql", kind="select")
        note = check.text(spec.get("note", ""), f"{where}.note", required=False, limit=200) or ""
        if name:
            if name in tables:
                check.fail(f"{where}.name", f"名稱「{name}」重複")
            tables.add(name)
            if sql:
                result.append(Transform(name, sql, note))
    return result


def _output(check: _Checker, raw: Any, tables: set[str], mappings: dict[str, Mapping]) -> Output | None:
    spec = check.mapping(raw, "output", {"from", "sheet", "columns", "order_by"}, {"from", "columns"})
    if spec.get("from") not in tables:
        check.fail("output.from", f"找不到表「{spec.get('from')}」")
    sheet = check.text(spec.get("sheet", "整理結果"), "output.sheet", limit=31) or "整理結果"
    if re.search(r"[\[\]:*?/\\]", sheet):
        check.fail("output.sheet", "工作表名稱不能有 [ ] : * ? / \\")
    order_by = check.sql(spec["order_by"], "output.order_by") if spec.get("order_by") else None
    columns = []
    names: set[str] = set()
    raw_columns = spec.get("columns")
    if not isinstance(raw_columns, list) or not raw_columns:
        check.fail("output.columns", "至少要有一個輸出欄位")
        raw_columns = []
    for i, cspec in enumerate(raw_columns):
        where = f"output.columns[{i}]"
        if isinstance(cspec, str):
            cspec = {"name": cspec, "from": cspec}
        cspec = check.mapping(cspec, where, {"name", "from", "sql", "type", "map", "required", "editable"}, {"name"})
        name = check.text(cspec.get("name"), f"{where}.name", limit=64)
        if name and (name in names or name.startswith("_")):
            check.fail(f"{where}.name", f"欄位名稱「{name}」重複或以底線開頭")
        names.add(name or "")
        if ("from" in cspec) == ("sql" in cspec):
            check.fail(where, "from（來源欄位）和 sql（運算式）要擇一")
            continue
        expr = None
        if "from" in cspec:
            source = check.name(cspec["from"], f"{where}.from")
            expr = quote(source) if source else None
        else:
            expr = check.sql(cspec["sql"], f"{where}.sql")
        column_type = cspec.get("type", "text")
        if column_type not in TYPES:
            check.fail(f"{where}.type", "只能是 text、number、integer、date")
        map_name = cspec.get("map")
        if map_name is not None and map_name not in mappings:
            check.fail(f"{where}.map", f"找不到對照表「{map_name}」")
        if name and expr:
            columns.append(OutputColumn(name, expr, column_type, map_name, bool(cspec.get("required", False)),
                                        bool(cspec.get("editable", True))))
    return Output(spec.get("from", ""), sheet, columns, order_by)


def _validate(check: _Checker, raw: Any, tables: set[str], output: Output | None) -> list[Check]:
    result = []
    if not isinstance(raw, list):
        check.fail("validate", "要是清單")
        return result
    output_names = {c.name for c in output.columns} if output else set()
    for i, spec in enumerate(raw):
        where = f"validate[{i}]"
        spec = check.mapping(spec, where, {"table", "where", "message", "level", "highlight"}, {"where", "message"})
        table = spec.get("table")
        if table is not None and table not in tables:
            check.fail(f"{where}.table", f"找不到表「{table}」")
        condition = check.sql(spec.get("where"), f"{where}.where")
        message = check.text(spec.get("message"), f"{where}.message", limit=120)
        level = spec.get("level", "review")
        if level not in LEVELS:
            check.fail(f"{where}.level", "只能是 review（需檢查）或 notice（提示）")
        highlight = check.str_list(spec.get("highlight"), f"{where}.highlight")
        for column in highlight:
            if column not in output_names:
                check.fail(f"{where}.highlight", f"「{column}」不是輸出欄位名稱")
        if condition and message:
            result.append(Check(table, condition, message, level, highlight))
    return result
