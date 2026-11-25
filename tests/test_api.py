"""API 流程：存 recipe、上傳檔案、執行、修改、指定配對、補對照、匯出。"""
import io
from pathlib import Path

import pytest

import dataprocessor.server as server

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "app" / "examples" / "workspace"
LOCAL = {"Origin": "http://localhost", "Sec-Fetch-Site": "same-origin"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    for name in ("RECIPES", "MAPPINGS", "REVIEWS", "UPLOADS", "SCRATCH", "SAMPLES"):
        monkeypatch.setattr(server.paths, name, tmp_path / name.lower())
    server.paths.RECIPES.mkdir()
    return server.app.test_client()


def _run(client):
    text = (EXAMPLES / "recipes" / "invoice-declaration.yaml").read_text(encoding="utf-8")
    assert client.post("/api/recipes", json={"text": text}, headers=LOCAL).status_code == 200
    data = (EXAMPLES / "samples" / "範例_發票與報關單.xlsx").read_bytes()
    upload = client.post("/api/workbooks", data={"file": (io.BytesIO(data), "../../x.xlsx")},
                         content_type="multipart/form-data", headers=LOCAL)
    assert upload.status_code == 200
    response = client.post("/api/runs", json={"recipe": "invoice-declaration", "workbook": upload.json["id"]},
                           headers=LOCAL)
    assert response.status_code == 200
    return response.json


def test_full_review_flow(client):
    result = _run(client)
    run_id = result["run_id"]
    assert result["status"] == "review"

    edited = client.post(f"/api/runs/{run_id}/edit", json={"rid": "invoice:9", "column": "金額", "value": "300"},
                         headers=LOCAL).json
    row = next(r for r in edited["output"]["rows"] if r["rid"] == "invoice:9")
    assert row["values"]["金額"] == 300 and "金額" in row["edited"]

    bad = client.post(f"/api/runs/{run_id}/edit", json={"rid": "invoice:9", "column": "金額", "value": "abc"},
                      headers=LOCAL)
    assert bad.status_code == 400

    picked = client.post(f"/api/runs/{run_id}/match", json={"match": "inv_decl", "left": "invoice:12",
                                                             "rights": ["declaration:6"]}, headers=LOCAL).json
    assert next(r for r in picked["output"]["rows"] if r["rid"] == "invoice:12")["values"]["報單號碼"] == "AA15A0005"

    wrong = client.post(f"/api/runs/{run_id}/mapping", json={"mapping": "ship_mode", "raw": "陸運", "target": "TRUCK"},
                        headers=LOCAL)
    assert wrong.status_code == 400
    mapped = client.post(f"/api/runs/{run_id}/mapping", json={"mapping": "ship_mode", "raw": "陸運", "target": "TRUCK",
                                                               "new_value": True}, headers=LOCAL).json
    assert not mapped["unmapped"]                               # 清單裡沒有的值，使用者可以自己新增
    ship = next(m for m in mapped["mappings"] if m["name"] == "ship_mode")
    assert "TRUCK" in ship["allowed"] and ship["added"] == [{"raw": "陸運", "target": "TRUCK"}]
    assert next(r for r in mapped["output"]["rows"] if r["rid"] == "invoice:8")["values"]["運送方式"] == "TRUCK"
    removed = client.post(f"/api/runs/{run_id}/mapping", json={"mapping": "ship_mode", "raw": "陸運", "target": None},
                          headers=LOCAL).json
    assert removed["unmapped"] and "TRUCK" not in next(m for m in removed["mappings"] if m["name"] == "ship_mode")["allowed"]
    mapped = client.post(f"/api/runs/{run_id}/mapping", json={"mapping": "ship_mode", "raw": "陸運", "target": "SEA"},
                         headers=LOCAL).json
    assert not mapped["unmapped"]

    issue = next(i for i in mapped["issues"] if i["code"] == "check0")
    dismissed = client.post(f"/api/runs/{run_id}/dismiss", json={"keys": [issue["key"]]}, headers=LOCAL).json
    assert next(i for i in dismissed["issues"] if i["key"] == issue["key"])["dismissed"]

    exported = client.get(f"/api/runs/{run_id}/export", headers=LOCAL)
    assert exported.status_code == 200 and exported.data[:2] == b"PK"


def test_live_connection_is_event_stream(client):
    response = client.get("/api/live?client=t1", headers={"Sec-Fetch-Site": "same-origin"}, buffered=False)
    assert response.mimetype == "text/event-stream"
    assert "t1" in server._clients
    response.close()                                           # 頁面關閉：連線斷掉就移除
    assert "t1" not in server._clients


def test_invalid_recipe_returns_problems(client):
    response = client.post("/api/recipes", json={"text": "recipe: 1\nid: x\ninputs: {}\n"}, headers=LOCAL)
    assert response.status_code == 422
    assert response.json["problems"]


def test_rejects_non_excel(client):
    response = client.post("/api/workbooks", data={"file": (io.BytesIO(b"hello"), "a.xlsx")},
                           content_type="multipart/form-data", headers=LOCAL)
    assert response.status_code == 400


def test_recipe_explanation(client):
    text = (EXAMPLES / "recipes" / "invoice-declaration.yaml").read_text(encoding="utf-8")
    data = client.post("/api/recipes/explain", json={"text": text}, headers=LOCAL).json
    assert data["subject"] == "發票"                              # 以第一個配對的左表為主角
    texts = [n["text"] for n in data["flow"]]
    assert texts[0] == "讀進發票" and any(t.startswith("找對應的報關單") for t in texts)
    match = next(n for n in data["flow"] if n["text"].startswith("找對應的報關單"))
    first = match["children"][0]
    assert first["kind"] == "if" and "發票的「發票號碼」等於報關單的「發票參考」" in first["text"]
    assert [c["text"] for c in first["children"]] == ["找到 1 筆 → 配對", "找到多筆 → 不自動挑，請你選"]
    assert match["children"][3]["kind"] == "else"                # 都找不到時
    assert [n["text"] for n in data["sources"]] == ["報關單", "匯率表"]
    bad = client.post("/api/recipes/explain", json={"text": "recipe: 1\nid: x\n"}, headers=LOCAL)
    assert bad.status_code == 422 and bad.json["problems"]


def test_row_trace(client):
    result = _run(client)
    trace = client.get(f"/api/runs/{result['run_id']}/trace?rid=invoice:5", headers=LOCAL).json
    assert trace["steps"][0] == "來自發票，工作表「發票明細」第 5 列"
    assert any("配到 報關單 AA15A0002（第 3 列）" in s for s in trace["steps"])
    assert trace["columns"]["金額"][:2] == ["儲存格原本是「USD 3,450.00」", "讀成數字 → 3450"]
    assert any("AIr" in s and "AIR" in s for s in trace["columns"]["運送方式"])
    assert trace["columns"]["報單號碼"][0] == "從配到的報關單 AA15A0002（第 3 列）帶過來"
    assert trace["columns"]["台幣金額"][0] == "在計算步驟「換算台幣」算出"
    # 驗證標記到的列：寫出規則與規則用到的每個欄位的值
    flagged = client.get(f"/api/runs/{result['run_id']}/trace?rid=invoice:6", headers=LOCAL).json["steps"]
    at = flagged.index("檢查「發票金額和報關金額不同」：有 → 標記需檢查")
    assert flagged[at + 1] == "　規則：「報關金額」不是空白 且 絕對值(「金額」-「報關金額」) > 0.01"
    assert flagged[at + 2] == "　這一列：金額 2,000、報關金額 2,100"
    passed = trace["steps"]   # invoice:5 沒被標記：不列數值
    assert "檢查「發票金額和報關金額不同」：沒問題" in passed and not any(s.startswith("　這一列") for s in passed)
    # 人工修改後通過：留下紀錄的列也寫出現在的值
    client.post(f"/api/runs/{result['run_id']}/edit", json={"rid": "invoice:6", "column": "金額", "value": "2100"},
                headers=LOCAL)
    fixed = client.get(f"/api/runs/{result['run_id']}/trace?rid=invoice:6", headers=LOCAL).json["steps"]
    assert "　這一列：金額 2,100、報關金額 2,100" in fixed
    missing = client.get(f"/api/runs/{result['run_id']}/trace?rid=nope", headers=LOCAL)
    assert missing.status_code == 404


def test_reset_clears_decisions_and_can_be_restored(client):
    result = _run(client)
    run_id = result["run_id"]
    assert result["decisions"] == 0 and not result["can_restore"]
    client.post(f"/api/runs/{run_id}/edit", json={"rid": "invoice:9", "column": "金額", "value": "300"}, headers=LOCAL)
    client.post(f"/api/runs/{run_id}/match", json={"match": "inv_decl", "left": "invoice:12",
                                                    "rights": ["declaration:6"]}, headers=LOCAL)
    client.post(f"/api/runs/{run_id}/mapping", json={"mapping": "ship_mode", "raw": "陸運", "target": "SEA"},
                headers=LOCAL)
    before = client.get(f"/api/runs/{run_id}", headers=LOCAL).json
    assert before["decisions"] == 2

    # 關掉重開、重新上傳同一份檔案：人工決定會套回來
    again = _run(client)
    assert again["decisions"] == 2

    reset = client.post(f"/api/runs/{again['run_id']}/reset", headers=LOCAL).json
    assert reset["decisions"] == 0 and reset["can_restore"]
    row = next(r for r in reset["output"]["rows"] if r["rid"] == "invoice:9")
    assert not row["edited"] and row["values"]["金額"] is None             # 回到原本需要檢查的樣子
    assert next(r for m in reset["matches"] if m["name"] == "inv_decl"
                for r in m["rows"] if r["left"] == "invoice:12")["status"] == "ambiguous"
    assert not reset["unmapped"]                                              # 補上的對照表不清（其他檔案也在用）

    restored = client.post(f"/api/runs/{again['run_id']}/restore", headers=LOCAL).json
    assert restored["decisions"] == 2 and not restored["can_restore"]
    assert next(r for r in restored["output"]["rows"] if r["rid"] == "invoice:9")["values"]["金額"] == 300
    assert client.post(f"/api/runs/{again['run_id']}/restore", headers=LOCAL).status_code == 404


def test_original_sheet_and_cell_origins(client):
    result = _run(client)
    run_id = result["run_id"]
    inputs = result["inputs"]["invoice"]
    position = inputs["positions"][inputs["sheets"][0]]
    row = next(r for r in result["output"]["rows"] if r["rid"] == "invoice:6")
    source_rid, column = row["origins"]["金額"]                     # 金額來自發票的哪一列、哪一欄
    assert source_rid == "invoice:6" and column in position["columns"]
    page = client.get(f"/api/runs/{run_id}/sheet", query_string={"name": inputs["sheets"][0], "start": 1},
                      headers=LOCAL).json
    header = page["rows"][position["header_row"] - 1]
    assert header[position["columns"][column]] == "金額" and position["header_row"] == 3
    cell = page["rows"][6 - 1][position["columns"][column]]
    assert cell == "2,000"                                            # 原始 Excel 第 6 列的金額格，原本的寫法
    assert page["rows"][5][0] == "INV-1003" and page["width"] == 8
    linked = row["origins"].get("報單號碼")
    assert linked and linked[0].startswith("declaration:")             # 從報關單帶進來的欄位指回報關單
    assert client.get(f"/api/runs/{run_id}/sheet", query_string={"name": "沒有這張"}, headers=LOCAL).status_code == 404
