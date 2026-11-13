"""介面測試的共用設定：起一個只給這次測試用的本機服務，用真的瀏覽器操作。

執行（不在 CI 跑；修改介面後一定要跑一次，並看 tests/ui/screens/ 的截圖）：
    uv run --project app --with playwright pytest tests/ui --ui
第一次在新電腦上要先下載 Chromium：
    uv run --project app --with playwright python -m playwright install chromium
已經有 Chrome 時可以設定 DP_CHROME=Chrome 執行檔路徑，不用另外下載。
"""
from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path

import pytest
from werkzeug.serving import make_server

from dataprocessor import server

sync_api = pytest.importorskip("playwright.sync_api", reason="沒有安裝 playwright：用 uv run --with playwright 執行")

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "app" / "examples" / "workspace"
SCREENS = Path(__file__).resolve().parent / "screens"


@pytest.fixture()
def base_url(tmp_path, monkeypatch):
    for name in ("RECIPES", "MAPPINGS", "REVIEWS", "UPLOADS", "SCRATCH"):
        monkeypatch.setattr(server.paths, name, tmp_path / name.lower())
    server.paths.RECIPES.mkdir()
    shutil.copy(EXAMPLES / "recipes" / "invoice-declaration.yaml", server.paths.RECIPES)
    monkeypatch.setattr(server.paths, "SAMPLES", EXAMPLES / "samples")
    httpd = make_server("127.0.0.1", 0, server.app, threaded=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


@pytest.fixture(scope="session")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            launched = p.chromium.launch(executable_path=os.environ.get("DP_CHROME") or None)
        except Exception as error:  # 沒有下載 Chromium
            pytest.skip(f"沒有可用的 Chromium：{str(error).splitlines()[0]}")
        yield launched
        launched.close()


class Ui:
    """一個瀏覽器分頁加上常用操作。頁面上的 JavaScript 錯誤會讓測試失敗。"""

    def __init__(self, context, base_url):
        self.context = context
        self.base_url = base_url
        self.errors: list[str] = []
        self.page = self.watch(context.new_page(), "main")

    def watch(self, page, name):
        page.on("pageerror", lambda e: self.errors.append(f"{name}: {e}"))
        page.on("dialog", lambda d: d.accept())   # 刪除 recipe 等確認對話框
        return page

    def open(self, path="/"):
        self.page.goto(self.base_url + path)
        self.page.wait_for_selector("#recipeList .recipe-item", timeout=5000)
        self.page.wait_for_timeout(300)
        return self.page

    def run_sample(self):
        page = self.open()
        page.click("text=使用範例")
        page.wait_for_timeout(300)
        page.click("#runButton")
        page.wait_for_selector("#result:not([hidden]) table.grid, #result:not([hidden]) .tab-body")
        page.wait_for_timeout(400)
        return page

    def state(self, expression, page=None):
        return (page or self.page).evaluate(expression)

    def row(self, invoice, page=None):
        return (page or self.page).locator(f"table.grid tbody tr:has-text('{invoice}')").first

    def field(self, name, page=None):
        return (page or self.page).locator(f"#drawer .field:has(label:text-is('{name}'))")

    def view(self, name, page=None):
        """結果表的「檢視」選單裡切換開關（換行、緊湊），切完收起選單。"""
        page = page or self.page
        menu = page.locator("details.menu").first
        if not menu.evaluate("e => e.open"):
            page.click("summary:has-text('檢視')")
        page.click(f".menu-body [role=switch]:has-text('{name}')")
        if page.locator("details.menu").first.evaluate("e => e.open"):
            page.click("summary:has-text('檢視')")

    def settle(self, page=None):
        (page or self.page).wait_for_timeout(900)

    def shot(self, name, page=None, **kwargs):
        SCREENS.mkdir(exist_ok=True)
        (page or self.page).screenshot(path=str(SCREENS / f"{name}.png"), **kwargs)


@pytest.fixture()
def ui(base_url, browser):
    context = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
    helper = Ui(context, base_url)
    yield helper
    context.close()
    assert not helper.errors, "頁面有 JavaScript 錯誤：\n" + "\n".join(helper.errors)
