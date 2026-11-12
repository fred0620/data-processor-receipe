"""Pop out 視窗的操作測試：用真的瀏覽器點按鈕，確認 pop out 出來的視窗能照常處理表格，並和主視窗同步。

需要 playwright 與 Chromium。沒有的環境（例如不能連外網的 GitLab runner）會顯示略過，不會假裝通過。
本機執行：
    uv run --project app --with playwright python -m playwright install chromium
    uv run --project app --with playwright pytest tests/test_ui_popout.py
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

sync_api = pytest.importorskip("playwright.sync_api", reason="沒有安裝 playwright，略過瀏覽器測試")


@pytest.fixture()
def base_url(tmp_path, monkeypatch):
    for name in ("RECIPES", "MAPPINGS", "REVIEWS", "UPLOADS", "SCRATCH", "OUTPUT"):
        monkeypatch.setattr(server.paths, name, tmp_path / name.lower())
    server.paths.RECIPES.mkdir()
    examples = Path(__file__).resolve().parent.parent / "app" / "examples" / "workspace"
    shutil.copy(examples / "recipes" / "invoice-declaration.yaml", server.paths.RECIPES)
    monkeypatch.setattr(server.paths, "SAMPLES", examples / "samples")
    httpd = make_server("127.0.0.1", 0, server.app, threaded=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


@pytest.fixture()
def browser():
    with sync_api.sync_playwright() as p:
        try:
            launched = p.chromium.launch(executable_path=os.environ.get("DP_CHROME") or None)
        except Exception as error:  # 沒有下載 Chromium
            pytest.skip(f"沒有可用的 Chromium：{str(error).splitlines()[0]}")
        yield launched
        launched.close()


def test_pop_out_window_can_review_the_table(base_url, browser):
    failures = []

    def check(ok, what):
        if not ok:
            failures.append(what)

    ctx = browser.new_context(viewport={"width": 1280, "height": 800}, accept_downloads=True)
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append("main:" + str(e)))
    pg.goto(base_url + "/")
    pg.wait_for_timeout(700)
    pg.click("text=使用範例")
    pg.wait_for_timeout(300)
    pg.click("#runButton")
    pg.wait_for_timeout(1500)
    check(pg.is_visible("text=Pop out ↗"), "主視窗有 Pop out ↗")
    with ctx.expect_page() as info:
        pg.click("text=Pop out ↗")
    w = info.value
    w.on("pageerror", lambda e: errs.append("pop:"+str(e)))
    w.set_viewport_size({"width":1600,"height":950}); w.wait_for_timeout(1500)
    check(w.is_visible("#popInButton") and w.inner_text("#popInButton") == "Pop in", "pop out 視窗有 Pop in")
    check(not w.is_visible(".setup") and not w.is_visible("#pipeline"), "pop out 視窗沒有左欄與流程卡片")
    rows = lambda: w.locator("table.grid tbody tr")

    # 1 表格
    n_review = rows().count()
    w.click(".chip:has-text('全部')"); w.wait_for_timeout(200)
    n_all = rows().count()
    check(n_all > n_review, f"篩選：需檢查 {n_review} 列，全部 {n_all} 列")
    w.fill("input.search", "LED"); w.wait_for_timeout(500)
    check(rows().count() == 2, "搜尋 LED 剩 2 列")
    w.fill("input.search", ""); w.wait_for_timeout(500)
    w.click("summary:has-text('欄位')"); w.click(".menu-body label:has-text('匯率') input"); w.wait_for_timeout(200)
    heads = w.locator("table.grid thead th").all_inner_texts()
    check("匯率" not in heads and w.is_visible(".menu-body"), "欄位選單：隱藏匯率，選單保持開著")
    w.click(".menu-body label:has-text('匯率') input"); w.click("summary:has-text('欄位')"); w.wait_for_timeout(200)
    w.click("button:has-text('顯示換行')"); w.wait_for_timeout(200)
    check(w.locator("table.grid.wrap").count() == 1, "顯示換行")
    w.click("button:has-text('壓成一行')"); w.click("button:has-text('緊湊')"); w.wait_for_timeout(200)
    check(w.locator("table.grid.dense").count() == 1, "緊湊")
    w.click("button:has-text('寬鬆')")

    # 2 單列細節
    w.click("table.grid tbody tr:has-text('INV-1006')"); w.wait_for_timeout(400)
    check(w.is_visible("#drawer"), "點一列打開細節")
    amount = w.locator(".field:has(label:text-is('金額')) input")
    amount.fill("300"); amount.press("Enter"); w.wait_for_timeout(1500)
    cell = w.locator("table.grid tbody tr:has-text('INV-1006') td.cell-edited").count()
    check(cell == 1, "在細節改金額後，表格格子變成已修改")
    check(pg.evaluate("state.result.output.rows.find(r=>r.rid==='invoice:9').values['金額']") == 300, "主視窗同步看到修改")
    name = w.locator(".field:has(label:text-is('品名')) textarea")
    name.click(); name.press("End"); name.press("Shift+Enter"); name.type("第二行"); name.press("Enter"); w.wait_for_timeout(1500)
    v = w.evaluate("state.result.output.rows.find(r=>r.rid==='invoice:9').values['品名']")
    check(v == "線材組\n第二行", f"多行文字 Shift+Enter 換行、Enter 儲存：{v!r}")
    w.click(".field:has(label:text-is('品名')) .hint button:has-text('還原')"); w.wait_for_timeout(1500)
    check(w.evaluate("state.result.output.rows.find(r=>r.rid==='invoice:9').values['品名']") == "線材組", "還原")
    w.hover(".field:has(label:text-is('金額')) .field-label"); w.click(".field:has(label:text-is('金額')) button.why"); w.wait_for_timeout(800)
    check(w.locator(".field:has(label:text-is('金額')) .trace").count() == 1, "怎麼來的")
    w.click("summary:has-text('這一列的處理過程')"); w.wait_for_timeout(800)
    check(w.locator(".row-trace .trace").count() == 1, "這一列的處理過程")
    w.screenshot(path="pop_drawer.png")
    w.click("#drawerClose")

    # 3 配對
    w.click(".tab:has-text('配對')"); w.wait_for_timeout(400)
    card = w.locator(".match-card:has-text('INV-1009')").first
    card.locator("button:has-text('選這筆')").first.click(); w.wait_for_timeout(1500)
    st = w.evaluate("state.result.matches[0].rows.find(r=>r.left==='invoice:12').status")
    check(st == "manual", "配對：選這筆")
    other = w.locator(".match-card:has-text('INV-1010')").first
    other.locator("button:has-text('確認正確')").click(); w.wait_for_timeout(1500)
    st = w.evaluate("state.result.matches[0].rows.find(r=>r.left==='invoice:13').status")
    check(st == "confirmed", "配對：確認正確（刪去法剩下的那筆）")
    w.screenshot(path="pop_match.png")

    # 4 對照表
    w.click(".tab:has-text('對照表')"); w.wait_for_timeout(400)
    w.select_option(".tab-body select", "SEA"); w.click(".tab-body button:has-text('儲存')"); w.wait_for_timeout(1500)
    check(not w.evaluate("state.result.unmapped.length"), "對照表：補上對照")

    # 5 所有警示
    w.click(".tab:has-text('所有警示')"); w.wait_for_timeout(400)
    before = w.evaluate("state.result.issues.filter(i=>!i.dismissed && i.level==='review').length")
    w.click("button:has-text('全選')"); w.click("button:has-text('確認無誤（')"); w.wait_for_timeout(1500)
    after = w.evaluate("state.result.issues.filter(i=>!i.dismissed && i.level==='review').length")
    check(after < before, f"所有警示：全選確認（{before} → {after}）")

    # 6 重新檢查與復原
    d = w.evaluate("state.result.decisions")
    w.click("#resetButton"); w.click("#resetButton"); w.wait_for_timeout(1500)
    check(w.evaluate("state.result.decisions") == 0, f"重新檢查：清掉 {d} 項")
    w.click(".toast-action"); w.wait_for_timeout(1500)
    check(w.evaluate("state.result.decisions") == d, "復原")
    check(pg.evaluate("state.result.decisions") == d, "主視窗同步")

    # 7 下載
    with w.expect_download() as dl:
        w.click("#exportButton")
    f = dl.value
    check(f.suggested_filename.endswith(".xlsx"), f"下載 Excel：{f.suggested_filename}")

    # 8 打字中不被另一邊打斷
    w.click(".tab:has-text('結果')"); w.wait_for_timeout(300)
    w.click("table.grid tbody tr:has-text('INV-1005')"); w.wait_for_timeout(300)
    qty = w.locator(".field:has(label:text-is('數量')) input")
    qty.click(); qty.fill("12")
    pg.evaluate("act('edit',{rid:'invoice:11',column:'金額',value:'650'})"); pg.wait_for_timeout(1500)
    check(qty.input_value() == "12", "另一個視窗更新時，正在打的字沒有被清掉")
    check(w.evaluate("document.activeElement.closest('.field')?.querySelector('label')?.textContent") == "數量",
          "另一個視窗更新時，游標還留在輸入框")
    check(w.evaluate("state.result.output.rows.find(r=>r.rid==='invoice:8').values['數量']") == 10,
          "打到一半的字沒有被自動存起來")
    qty.press("Escape"); w.wait_for_timeout(500)
    check(w.evaluate("state.result.output.rows.find(r=>r.rid==='invoice:11').values['金額']") == 650, "離開輸入框後套用另一個視窗的更新")
    check(w.evaluate("state.result.output.rows.find(r=>r.rid==='invoice:8').values['數量']") == 10, "按 Esc 取消，數量沒有被改")

    w.click("#popInButton"); pg.wait_for_timeout(800)
    check(w.is_closed() and pg.evaluate("state.tab") == "rows", "Pop in：關閉並回到主視窗")
    check(not errs, f"沒有 JS 錯誤 {errs}")

    assert not failures, "\n".join(failures)
