"""實地練習（labs）後端測試：解答通過、起始片段不通過、錯誤片段回傳片段行號、不洩漏預期值、不汙染 workspace。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import dataprocessor.server as server

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "app" / "dataprocessor" / "demo"
LOCAL = {"Origin": "http://localhost", "Sec-Fetch-Site": "same-origin"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    for name in ("RECIPES", "MAPPINGS", "REVIEWS", "UPLOADS", "SCRATCH", "OUTPUT", "SAMPLES"):
        monkeypatch.setattr(server.paths, name, tmp_path / name.lower())
    server.paths.RECIPES.mkdir()
    server.paths.MAPPINGS.mkdir()
    server.paths.REVIEWS.mkdir()
    return server.app.test_client()


def test_labs_list_hides_answers_and_checks(client):
    res = client.get("/api/labs", headers=LOCAL)
    assert res.status_code == 200
    labs = res.json["labs"]
    assert len(labs) == 5
    for lab in labs:
        assert set(lab.keys()) == {"id", "title", "steps"}
        assert "answer" not in lab and "checks" not in lab

    assert client.post("/api/labs/unknown/start", json={}, headers=LOCAL).status_code == 400
    assert client.post("/api/labs/unknown/try", json={"snippet": ""}, headers=LOCAL).status_code == 400


def test_all_five_labs_answer_passes_and_start_fails(client):
    manifest = json.loads((DEMO / "labs.json").read_text(encoding="utf-8"))
    for lab in manifest["labs"]:
        lab_id = lab["id"]
        started = client.post(f"/api/labs/{lab_id}/start", json={}, headers=LOCAL)
        assert started.status_code == 200, lab_id
        assert started.json["result"]["demo"] is True

        # 起始片段（空白）不應通過
        empty_try = client.post(f"/api/labs/{lab_id}/try", json={"snippet": lab.get("start", "")}, headers=LOCAL)
        assert empty_try.status_code == 200, lab_id
        assert empty_try.json["ok"] is False, f"{lab_id} 起始片段竟然通過了"

        # 解答應該通過所有 checks
        ans_try = client.post(f"/api/labs/{lab_id}/try", json={"snippet": lab["answer"]}, headers=LOCAL)
        assert ans_try.status_code == 200, lab_id
        assert ans_try.json["ok"] is True, f"{lab_id} 解答未通過：{ans_try.json['checks']} {ans_try.json['problems']}"
        assert all(c["pass"] for c in ans_try.json["checks"])

    # 不寫入正式 workspace
    assert list(server.paths.RECIPES.glob("*.yaml")) == []
    assert list(server.paths.REVIEWS.rglob("*")) == []
    assert list(server.paths.MAPPINGS.rglob("*")) == []


def test_lab_syntax_error_remaps_line_number(client):
    bad_yaml = "- label: broken\n  on: [unclosed"
    res = client.post("/api/labs/lab-match/try", json={"snippet": bad_yaml}, headers=LOCAL)
    assert res.status_code == 200
    assert res.json["ok"] is False
    assert res.json["problems"]
    assert any("片段第" in p for p in res.json["problems"]), res.json["problems"]
