"""人工決定不會互相蓋掉、確認不必重跑、匯出不落地、不安全的輸入擋在外面。"""
import io
import json
import zipfile

import pytest
from openpyxl import load_workbook

import dataprocessor.server as server
from dataprocessor import engine
from dataprocessor.engine.recipe import RecipeError, load_recipe
from test_api import EXAMPLES, LOCAL, _run, client  # noqa: F401  client 是 fixture


def _post(client, path, body=None):
    return client.post(path, json=body or {}, headers=LOCAL)


def test_two_runs_of_same_file_keep_each_others_decisions(client):
    first = _run(client)
    second = _post(client, "/api/runs", {"recipe": "invoice-declaration", "workbook": first["workbook"]["id"]}).json
    _post(client, f"/api/runs/{first['run_id']}/edit", {"rid": "invoice:9", "column": "金額", "value": "300"})
    after = _post(client, f"/api/runs/{second['run_id']}/edit", {"rid": "invoice:6", "column": "金額", "value": "2100"}).json
    assert after["decisions"] == 2
    edited = {r["rid"] for r in after["output"]["rows"] if r["edited"]}
    assert {"invoice:9", "invoice:6"} <= edited


def test_reset_twice_keeps_the_backup_and_restore_keeps_new_decisions(client):
    run = _run(client)
    rid = run["run_id"]
    _post(client, f"/api/runs/{rid}/edit", {"rid": "invoice:9", "column": "金額", "value": "300"})
    _post(client, f"/api/runs/{rid}/reset")
    again = _post(client, f"/api/runs/{rid}/reset").json        # 已經沒有決定可清，不能把備份蓋成空的
    assert again["can_restore"]
    key = next(i["key"] for i in again["issues"] if i["code"] == "check0")
    _post(client, f"/api/runs/{rid}/dismiss", {"keys": [key]})   # 重設之後又確認了一筆
    restored = _post(client, f"/api/runs/{rid}/restore").json
    assert restored["decisions"] == 2                            # 原本的修改回來了，新的確認也還在
    assert next(i for i in restored["issues"] if i["key"] == key)["dismissed"]


@pytest.mark.parametrize("body", [{"keys": [["x"]]}, {"keys": [{"a": 1}]}, {"keys": ["k"], "on": "false"}])
def test_dismiss_rejects_malformed_requests(client, body):
    run = _run(client)
    assert _post(client, f"/api/runs/{run['run_id']}/dismiss", body).status_code == 400


def _comparable(result):
    data = json.loads(json.dumps(result))
    data.pop("can_restore", None)
    return data


def test_dismiss_without_rerun_matches_a_full_rerun(client, monkeypatch):
    run = _run(client)
    rid = run["run_id"]
    # 兩列搶同兩筆候選：人工指定一列後，另一列只剩一筆，會變成「配對待確認」
    match = next(m for m in run["matches"] if m["name"] == "inv_decl")
    row = next(r for r in match["rows"] if r["left"] == "invoice:12")
    run = _post(client, f"/api/runs/{rid}/match", {"match": "inv_decl", "left": "invoice:12",
                                                   "rights": [row["candidates"][0]["rid"]]}).json
    calls = []
    real = engine.run
    monkeypatch.setattr(server.engine, "run", lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    keys = [i["key"] for i in run["issues"] if i["level"] in ("review", "notice")]
    assert any(k.startswith("match_review") for k in keys)       # 也涵蓋「配對待確認」變成已確認
    for on in (True, False):
        for key in keys:
            fast = _post(client, f"/api/runs/{rid}/dismiss", {"keys": [key], "on": on}).json
            assert not calls, "只改確認時不應該整個重跑"
            full = _post(client, f"/api/runs/{rid}/rerun").json
            calls.clear()
            assert _comparable(fast) == _comparable(full), key


def test_export_streams_without_saving_a_copy(client, tmp_path):
    run = _run(client)
    before = set(server.paths.WORKSPACE.rglob("*.xlsx")) if server.paths.WORKSPACE.exists() else set()
    response = client.get(f"/api/runs/{run['run_id']}/export", headers=LOCAL)
    assert response.status_code == 200 and response.headers["Content-Disposition"].startswith("attachment")
    book = load_workbook(io.BytesIO(response.data))
    assert "待檢查" in book.sheetnames
    assert not [p for p in tmp_path.rglob("*.xlsx") if "uploads" not in p.parts]
    after = set(server.paths.WORKSPACE.rglob("*.xlsx")) if server.paths.WORKSPACE.exists() else set()
    assert after == before


def test_rejects_zip_bomb_before_reading(client):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/sharedStrings.xml", b"\0" * (30 * 1024 * 1024))   # 壓縮後只有幾十 KB
    response = client.post("/api/workbooks", data={"file": (io.BytesIO(data.getvalue()), "big.xlsx")},
                           content_type="multipart/form-data", headers=LOCAL)
    assert response.status_code == 400 and "壓縮比" in response.json["error"]


@pytest.mark.parametrize("pattern,ok", [("Lot\\s*(\\w+)", True), ("(\\d{4})", True), ("(?:\\d{3})+", True),
                                        ("(a+)+$", False), ("(\\w*)*x", False), ("(x|y+)*z", False)])
def test_recipe_rejects_regex_that_can_hang(pattern, ok):
    text = (EXAMPLES / "recipes" / "invoice-declaration.yaml").read_text(encoding="utf-8")
    text = text.replace("status: {aliases: [狀態]}",
                        "status: {aliases: [狀態]}\n      lot: {source: item, extract: {regex: " + json.dumps(pattern) + "}}")
    if ok:
        load_recipe(text)
    else:
        with pytest.raises(RecipeError, match="重複裡面又重複"):
            load_recipe(text)
