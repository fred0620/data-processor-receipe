"""用 Playwright 產生使用手冊的乾淨截圖（1440×900，關閉所有導覽元件）。

    DP_CHROME=/usr/bin/google-chrome uv run --project app --with playwright python scripts/make_manual_screens.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

from dataprocessor import server

EXAMPLES = ROOT / "app" / "examples" / "workspace"
OUT = ROOT / "docs" / "images"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        for name in ("RECIPES", "MAPPINGS", "REVIEWS", "UPLOADS", "SCRATCH", "OUTPUT"):
            setattr(server.paths, name, base / name.lower())
        server.paths.RECIPES.mkdir(parents=True, exist_ok=True)
        shutil.copy(EXAMPLES / "recipes" / "invoice-declaration.yaml", server.paths.RECIPES)
        server.paths.SAMPLES = EXAMPLES / "samples"

        httpd = make_server("127.0.0.1", 0, server.app, threaded=True)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{httpd.server_port}"
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=os.environ.get("DP_CHROME") or None)
                context = browser.new_context(viewport={"width": 1440, "height": 900})
                page = context.new_page()
                page.goto(url)
                page.wait_for_selector("#recipeList .recipe-item")
                # 關掉導覽與新功能小點，拍乾淨畫面
                page.evaluate("""() => {
                  localStorage.setItem('dp:onboarding.v1', JSON.stringify({
                    dismissed: true,
                    journeys: { review: { step: null, done: true, skipped: [] }, recipe: { step: null, done: true, skipped: [] } },
                    cardsSeen: [], labsDone: [], tipsSeen: { jk: 3 }, whatsnewSeen: '9.9.9'
                  }));
                }""")
                page.reload()
                page.wait_for_selector("#recipeList .recipe-item")
                page.click("text=使用範例")
                page.wait_for_timeout(250)
                page.click("#runButton")
                page.wait_for_selector("#result:not([hidden]) table.grid")
                page.wait_for_timeout(450)

                # 1. 總覽：結果表、流程卡片、右側細節
                page.screenshot(path=str(OUT / "manual-01-overview.png"))

                # 2. 怎麼判斷的：展開 INV-1003 的驗證處理過程
                page.click('[data-guide="issue-trace"]')
                page.wait_for_timeout(400)
                page.locator("#drawer").screenshot(path=str(OUT / "manual-02-trace.png"))

                # 3. 原始資料並排：切到原始資料並打開左右並排
                page.click('.tab[data-tab="source"]')
                page.wait_for_selector(".source-pane")
                page.wait_for_timeout(300)
                page.click('.source-top [role="switch"]')
                page.wait_for_timeout(450)
                page.locator(".work").screenshot(path=str(OUT / "manual-03-source-split.png"))

                browser.close()
        finally:
            httpd.shutdown()
    print("完成截圖：", sorted(p.name for p in OUT.glob("manual-*.png")))


if __name__ == "__main__":
    main()
