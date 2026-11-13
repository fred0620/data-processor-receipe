"""範例模式端點：白名單安全、不汙染正式資料、匯出前綴、returning 判斷、demo 與 examples 同步。"""
from __future__ import annotations

from pathlib import Path

import pytest

import dataprocessor.server as server

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "app" / "dataprocessor" / "demo"
EXAMPLES = ROOT / "app" / "examples" / "workspace"
LOCAL = {"Origin": "http://localhost", "Sec-Fetch-Site": "same-origin"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    for name in ("RECIPES", "MAPPINGS", "REVIEWS", "UPLOADS", "SCRATCH", "SAMPLES"):
        monkeypatch.setattr(server.paths, name, tmp_path / name.lower())
    server.paths.RECIPES.mkdir()
    server.paths.MAPPINGS.mkdir()
    server.paths.REVIEWS.mkdir()
    return server.app.test_client()


def test_demo_whitelist_and_security(client):
    assert client.post("/api/demo/start", json={"journey": "../etc"}, headers=LOCAL).status_code == 400
    assert client.post("/api/demo/start", json={"journey": "unknown"}, headers=LOCAL).status_code == 400
    assert client.get("/api/demo/recipe/../../secret", headers=LOCAL).status_code in (400, 404)
    assert client.get("/api/demo/recipe/unknown", headers=LOCAL).status_code == 400
    cross = {"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"}
    assert client.post("/api/demo/start", json={"journey": "review"}, headers=cross).status_code == 403
    assert client.post("/api/demo/clear", json={}, headers=cross).status_code == 403
    bad_recipe = client.post("/api/runs", json={"recipe": "demo:../evil", "workbook": "none"}, headers=LOCAL)
    assert bad_recipe.status_code in (400, 404)


def test_demo_does_not_pollute_workspace_and_clears(client):
    started = client.post("/api/demo/start", json={"journey": "review"}, headers=LOCAL)
    assert started.status_code == 200
    payload = started.json
    assert payload["recipe"]["id"] == "demo:invoice-declaration"
    assert payload["recipe"]["demo"] is True

    # demo recipe 不出現在 /api/recipes
    recipes = client.get("/api/recipes", headers=LOCAL).json["recipes"]
    assert not any(r["id"].startswith("demo:") for r in recipes)

    run = client.post("/api/runs", json={"recipe": payload["recipe"]["id"], "workbook": payload["workbook"]["id"]},
                      headers=LOCAL)
    assert run.status_code == 200
    result = run.json
    assert result["demo"] is True
    run_id = result["run_id"]

    # 修改、補對照、指定配對、確認警示都不寫進正式 workspace
    edited = client.post(f"/api/runs/{run_id}/edit", json={"rid": "invoice:9", "column": "金額", "value": "300"},
                         headers=LOCAL)
    assert edited.status_code == 200 and edited.json["demo"] is True
    mapped = client.post(f"/api/runs/{run_id}/mapping",
                         json={"mapping": "ship_mode", "raw": "陸運", "target": "LAND", "new_value": True},
                         headers=LOCAL)
    assert mapped.status_code == 200 and not mapped.json["unmapped"]
    assert list(server.paths.REVIEWS.rglob("*")) == []
    assert list(server.paths.MAPPINGS.rglob("*")) == []
    assert list((server.paths.SCRATCH / "demo" / "reviews").rglob("*.json"))
    assert list((server.paths.SCRATCH / "demo" / "mappings").rglob("*.json"))

    # 匯出檔名帶「示範_」前綴
    exported = client.get(f"/api/runs/{run_id}/export", headers=LOCAL)
    assert exported.status_code == 200 and exported.data[:2] == b"PK"
    cd = exported.headers.get("Content-Disposition", "")
    assert "示範_" in cd or "%E7%A4%BA%E7%AF%84_" in cd

    # 練習 recipe 存在暫存空間，使用者的同名 recipe 不受影響
    user_practice = server.paths.RECIPES / "practice-invoice.yaml"
    user_content = (EXAMPLES / "recipes" / "invoice-declaration.yaml").read_text(encoding="utf-8").replace(
        "id: invoice-declaration", "id: practice-invoice"
    ).replace("name: 發票對報關單（範例）", "name: 我的正式發票規則")
    user_practice.write_text(user_content, encoding="utf-8")
    orig_mtime = user_practice.stat().st_mtime_ns

    fixed = client.get("/api/demo/recipe/recipe-fixed", headers=LOCAL)
    assert fixed.status_code == 200
    saved = client.post("/api/recipes", json={"text": fixed.json["text"], "practice": True}, headers=LOCAL)
    assert saved.status_code == 200
    assert saved.json["id"] == "practice:invoice"
    assert saved.json["practice"] is True
    assert (server.paths.SCRATCH / "demo" / "recipes" / "invoice.yaml").exists()

    # GET /api/recipes 同時列出使用者的 practice-invoice 與練習的 practice:invoice
    listed = client.get("/api/recipes", headers=LOCAL).json["recipes"]
    user_item = next(r for r in listed if r["id"] == "practice-invoice")
    prac_item = next(r for r in listed if r["id"] == "practice:invoice")
    assert not user_item.get("practice")
    assert prac_item.get("practice") is True

    # 刪除練習 recipe 與 /api/demo/clear 都不會動到使用者的檔案
    assert client.delete("/api/recipes/practice:invoice", headers=LOCAL).status_code == 200
    assert not (server.paths.SCRATCH / "demo" / "recipes" / "invoice.yaml").exists()
    assert user_practice.exists()
    assert user_practice.read_text(encoding="utf-8") == user_content
    assert user_practice.stat().st_mtime_ns == orig_mtime

    # 再存一次並呼叫 /api/demo/clear
    assert client.post("/api/recipes", json={"text": fixed.json["text"], "practice": True}, headers=LOCAL).status_code == 200
    cleared = client.post("/api/demo/clear", json={}, headers=LOCAL)
    assert cleared.status_code == 200
    assert not (server.paths.SCRATCH / "demo").exists()
    assert user_practice.exists()
    assert user_practice.read_text(encoding="utf-8") == user_content
    assert user_practice.stat().st_mtime_ns == orig_mtime
    assert client.get(f"/api/runs/{run_id}", headers=LOCAL).status_code == 404


def test_practice_save_creates_nothing_in_workspace_recipes(client):
    fixed = client.get("/api/demo/recipe/recipe-fixed", headers=LOCAL)
    assert fixed.status_code == 200
    res = client.post("/api/recipes", json={"text": fixed.json["text"], "practice": True}, headers=LOCAL)
    assert res.status_code == 200
    assert list(server.paths.RECIPES.glob("*.yaml")) == []


def test_demo_and_practice_code_never_touches_workspace_recipes():
    import inspect
    for fn in (server.demo_start, server.demo_recipe, server.demo_clear, server.start_lab, server.try_lab):
        src = inspect.getsource(fn)
        assert "paths.RECIPES" not in src, f"{fn.__name__} 不應引用 paths.RECIPES"


def test_demo_draft_has_two_problems_and_fixed_is_valid(client):
    draft = client.get("/api/demo/recipe/recipe-draft", headers=LOCAL)
    assert draft.status_code == 200
    explained = client.post("/api/recipes/explain", json={"text": draft.json["text"]}, headers=LOCAL)
    assert explained.status_code == 422
    assert len(explained.json["problems"]) == 2

    fixed = client.get("/api/demo/recipe/recipe-fixed", headers=LOCAL)
    assert fixed.status_code == 200
    explained_ok = client.post("/api/recipes/explain", json={"text": fixed.json["text"]}, headers=LOCAL)
    assert explained_ok.status_code == 200
    assert explained_ok.json["name"] == "發票對報關單（練習）"


def test_demo_matches_examples():
    assert (DEMO / "invoice-declaration.yaml").read_bytes() == (
        EXAMPLES / "recipes" / "invoice-declaration.yaml"
    ).read_bytes()
    assert (DEMO / "範例_發票與報關單.xlsx").read_bytes() == (
        EXAMPLES / "samples" / "範例_發票與報關單.xlsx"
    ).read_bytes()


def test_status_returning_flag(client):
    assert client.get("/api/status", headers=LOCAL).json["returning"] is False

    # 只有範例 recipe 不算 returning
    text = (EXAMPLES / "recipes" / "invoice-declaration.yaml").read_text(encoding="utf-8")
    (server.paths.RECIPES / "invoice-declaration.yaml").write_text(text, encoding="utf-8")
    assert client.get("/api/status", headers=LOCAL).json["returning"] is False

    # 放入使用者自己的 recipe 算 returning
    (server.paths.RECIPES / "custom.yaml").write_text(text, encoding="utf-8")
    assert client.get("/api/status", headers=LOCAL).json["returning"] is True
    (server.paths.RECIPES / "custom.yaml").unlink()
    assert client.get("/api/status", headers=LOCAL).json["returning"] is False

    # reviews 有內容算 returning
    (server.paths.REVIEWS / "r.json").write_text("{}", encoding="utf-8")
    assert client.get("/api/status", headers=LOCAL).json["returning"] is True


def test_returning_when_own_recipe_reuses_builtin_name(client):
    """自己的 recipe 剛好也叫 invoice-declaration 或 practice-invoice，內容不同就算 returning。"""
    text = (EXAMPLES / "recipes" / "invoice-declaration.yaml").read_text(encoding="utf-8")
    own = server.paths.RECIPES / "invoice-declaration.yaml"
    own.write_text(text.replace("name:", "name: 我自己的", 1), encoding="utf-8")
    assert client.get("/api/status", headers=LOCAL).json["returning"] is True
    own.unlink()

    # 關卡 B 存下的練習 recipe（內容和修正版相同，換行是 CRLF 也一樣）不算
    fixed = (DEMO / "recipe-fixed.yaml").read_text(encoding="utf-8")
    practice = server.paths.RECIPES / "practice-invoice.yaml"
    practice.write_bytes(fixed.replace("\n", "\r\n").encode("utf-8"))
    assert client.get("/api/status", headers=LOCAL).json["returning"] is False
    practice.write_text(fixed + "\n# 我改過\n", encoding="utf-8")
    assert client.get("/api/status", headers=LOCAL).json["returning"] is True
