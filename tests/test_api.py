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
    for name in ("RECIPES", "MAPPINGS", "REVIEWS", "UPLOADS", "SCRATCH", "OUTPUT", "SAMPLES"):
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
