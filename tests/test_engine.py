"""引擎的行為：範例 recipe 的完整流程、多策略配對、對照表、人工決定與沙箱。"""
from pathlib import Path

import pytest

from dataprocessor.engine import RecipeError, load_recipe, run
from dataprocessor.engine.export import export
from dataprocessor.engine.review import MappingStore, ReviewStore
from dataprocessor.engine.textnorm import key, parse_date, parse_number
from dataprocessor.engine.workbook import read_workbook

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "app" / "examples" / "workspace"
RECIPE = EXAMPLES / "recipes" / "invoice-declaration.yaml"
SAMPLE = EXAMPLES / "samples" / "範例_發票與報關單.xlsx"


@pytest.fixture
def env(tmp_path):
    recipe = load_recipe(RECIPE.read_text(encoding="utf-8"))
    sheets = read_workbook(SAMPLE)

    def execute():
        review = ReviewStore(tmp_path / "reviews", recipe.id, "test")
        mappings = MappingStore(tmp_path / "mappings", recipe.id)
        return run(recipe, sheets, review, mappings, tmp_path / "scratch"), review, mappings

    return execute


def _row(result, number):
    return next(r for r in result["output"]["rows"] if r["row"] == number)


def _messages(result, row):
    return [result["issues"][i]["message"] for i in row["issues"]]


def test_parsers():
    assert parse_number("USD 1,234.50") == 1234.5
    assert parse_number("(150)") == -150
    assert parse_number("１２０") == 120
    assert parse_number("12%") == 0.12
    assert parse_number("約 300") is None          # 不猜測
    assert parse_number("12KG") is None
    assert parse_number("12KG", strip=["KG"]) == 12
    assert parse_date("115/01/06").isoformat() == "2026-01-06"
    assert parse_date("2026年1月7日").isoformat() == "2026-01-07"
    assert parse_date("2026-02-30") is None
    assert key("空 運") == key("空運") and key("AIr") == key("ＡＩＲ")


def test_example_pipeline(env):
    result, _, _ = env()
    assert result["status"] == "review"
    rows = result["output"]["rows"]
    assert len(rows) == 9                                      # 作廢那張被 Gate 排除
    assert result["excluded"][0]["label"] == "排除作廢發票"
    first = _row(result, 4)
    assert first["values"]["運送方式"] == "AIR" and first["values"]["台幣金額"] == 38520
    assert first["status"] == "ok"
    roc = _row(result, 5)                                      # 民國日期、USD 3,450.00、AIr
    assert roc["values"]["發票日期"] == "2026-01-06" and roc["values"]["金額"] == 3450
    assert roc["values"]["報單號碼"] == "AA15A0002"
    digits = _row(result, 7)                                   # 發票號碼只有 1004，靠第二個比對方式
    assert digits["values"]["報單號碼"] == "AA15A0004"
    unparsable = _row(result, 9)                               # 「約 300」留空，原始內容保留
    assert unparsable["values"]["金額"] is None
    assert any("約 300" in m for m in _messages(result, unparsable))


def test_issues_only_on_affected_cells(env):
    result, _, _ = env()
    mismatch = _row(result, 6)
    flagged = {c for i in mismatch["issues"] for c in result["issues"][i]["out_columns"]}
    assert flagged == {"金額", "報關金額"}
    unmapped = _row(result, 8)                                 # 陸運不在對照表：只提醒一次，不再重複「必填空白」
    messages = _messages(result, unmapped)
    assert sum("陸運" in m for m in messages) == 1
    assert not any("必填" in m for m in messages)


def test_ambiguous_match_then_manual_pick(env):
    result, review, _ = env()
    match = result["matches"][0]
    ambiguous = [r for r in match["rows"] if r["status"] == "ambiguous"]
    assert {r["left"] for r in ambiguous} == {"invoice:12", "invoice:13"}
    review.set_match("inv_decl", "invoice:12", ["declaration:6"])
    review.set_match("inv_decl", "invoice:13", ["declaration:7"])
    review.save()
    result, _, _ = env()
    assert _row(result, 12)["values"]["報單號碼"] == "AA15A0005"
    assert _row(result, 13)["values"]["報單號碼"] == "AA15A0006"
    assert _row(result, 12)["status"] == "ok"


def test_mapping_added_in_ui_is_reused(env):
    _, _, mappings = env()
    mappings.add("ship_mode", "陸 運", "SEA")                  # 寬鬆比對：「陸 運」也對得到「陸運」
    result, _, _ = env()
    assert _row(result, 8)["values"]["運送方式"] == "SEA"
    assert not result["unmapped"]


def test_edits_keep_original_and_suppress_cell_issue(env):
    result, review, _ = env()
    review.set_edit("invoice:9", "金額", "約 300", 300.0)    # 介面會把當時看到的原始內容存成原值
    review.save()
    result, _, _ = env()
    row = _row(result, 9)
    assert row["values"]["金額"] == 300.0 and "金額" in row["edited"]
    assert row["values"]["台幣金額"] == 9630                   # 修改在讀進來時套用，後面的計算會重算
    assert not any("約 300" in m for m in _messages(result, row))
    review.set_edit("invoice:9", "金額", None, 300.0)          # 原值和目前資料不同時要提醒
    review.data["edits"]["invoice:9"]["金額"]["original"] = "約 400"
    review.save()
    result, _, _ = env()
    assert any("原始值已變更" in m for m in _messages(result, _row(result, 9)))


def test_export_blocks_formula_injection(env, tmp_path):
    from openpyxl import load_workbook

    result, _, _ = env()
    result["output"]["rows"][0]["values"]["品名"] = "=HYPERLINK(\"http://x\")"
    path = export(result, tmp_path / "out.xlsx")
    sheet = load_workbook(path)["整理結果"]
    cell = sheet.cell(row=2, column=3)
    assert cell.data_type == "s" and cell.value.startswith("=")
    assert {"整理結果", "待檢查", "配對明細", "排除", "對照待補"} <= set(load_workbook(path).sheetnames)


def test_recipe_problems_are_listed_together():
    text = RECIPE.read_text(encoding="utf-8")
    broken = text.replace("type: number, required: true}", "type: money, required: true}", 1)
    broken = broken.replace("left: invoice\n", "left: invoices\n", 1)
    with pytest.raises(RecipeError) as error:
        load_recipe(broken)
    joined = "\n".join(error.value.problems)
    assert "money" in joined or "只能是 text" in joined
    assert "invoices" in joined


def test_sql_is_sandboxed(env, tmp_path):
    text = RECIPE.read_text(encoding="utf-8")
    with pytest.raises(RecipeError):                           # 只能一段 SELECT
        load_recipe(text.replace("FROM with_fx", "FROM with_fx; DROP TABLE fx", 1))
    recipe = load_recipe(text.replace("FROM with_fx", "FROM with_fx, read_csv('/etc/passwd')", 1))
    result = run(recipe, read_workbook(SAMPLE), ReviewStore(tmp_path, recipe.id, "x"),
                 MappingStore(tmp_path, recipe.id), tmp_path / "scratch")
    assert result["status"] == "error"
    assert any("Permission" in i["message"] or "disabled" in i["message"] for i in result["issues"])


def test_yaml_on_is_not_boolean():
    recipe = load_recipe(RECIPE.read_text(encoding="utf-8"))
    assert recipe.match[0].strategies[0].on.startswith("l.")


def _variant(old: str, new: str):
    text = RECIPE.read_text(encoding="utf-8")
    assert old in text
    return load_recipe(text.replace(old, new, 1))


def _run_recipe(recipe, tmp_path):
    return run(recipe, read_workbook(SAMPLE), ReviewStore(tmp_path / "r", recipe.id, "x"),
               MappingStore(tmp_path / "m", recipe.id), tmp_path / "scratch")


MATCH_BLOCK = """    mode: one_to_one
    strategies:
      - label: 發票號碼相同"""


def test_many_to_many_expands_rows(tmp_path):
    recipe = _variant(MATCH_BLOCK, """    mode: many_to_many
    strategies:
      - label: 金額相同
        when: "l.amount = 500"
        on: "l.amount = r.amount"
      - label: 發票號碼相同""")
    result = _run_recipe(recipe, tmp_path)
    led = [r for r in result["output"]["rows"] if r["row"] in (12, 13)]
    assert len(led) == 4                                       # 兩張發票各對到兩張報關單
    assert len({r["rid"] for r in led}) == 4                   # 展開後每列仍有自己的代號，可以各自修改
    match = result["matches"][0]
    assert next(r for r in match["rows"] if r["left"] == "invoice:12")["rights"] == ["declaration:6", "declaration:7"]


def test_one_to_many_does_not_guess_shared_rows(tmp_path):
    recipe = _variant(MATCH_BLOCK, """    mode: one_to_many
    strategies:
      - label: 金額相同
        when: "l.amount = 500"
        on: "l.amount = r.amount"
      - label: 發票號碼相同""")
    result = _run_recipe(recipe, tmp_path)
    row = next(r for r in result["matches"][0]["rows"] if r["left"] == "invoice:12")
    assert row["status"] == "ambiguous" and row["rights"] == []   # 右表同時對到兩張發票，交給人決定


def test_many_to_many_combine_into_one_row(tmp_path):
    text = RECIPE.read_text(encoding="utf-8")
    text = text.replace(MATCH_BLOCK, """    mode: many_to_many
    rows: combine
    strategies:
      - label: 金額相同
        when: "l.amount = 500"
        on: "l.amount = r.amount"
      - label: 發票號碼相同""", 1)
    text = text.replace("bring: {decl_no: decl_no, decl_date: decl_date, decl_amount: amount, decl_ship: ship_mode}",
                        "bring: {decl_no: \"string_agg(r.decl_no, '、' ORDER BY r.decl_no)\", decl_date: max(r.decl_date), "
                        "decl_amount: sum(r.amount), decl_ship: any_value(r.ship_mode)}", 1)
    result = _run_recipe(load_recipe(text), tmp_path)
    assert result["status"] != "error", [i["message"] for i in result["issues"] if i["level"] == "error"]
    row = next(r for r in result["output"]["rows"] if r["row"] == 12)
    assert row["values"]["報單號碼"] == "AA15A0005、AA15A0006" and row["values"]["報關金額"] == 1000
    assert len([r for r in result["output"]["rows"] if r["row"] == 12]) == 1


def test_combine_requires_aggregate_bring():
    text = RECIPE.read_text(encoding="utf-8").replace("    mode: one_to_one\n", "    mode: one_to_one\n    rows: combine\n", 1)
    with pytest.raises(RecipeError):                           # combine 只能用在一對多或多對多
        load_recipe(text)
