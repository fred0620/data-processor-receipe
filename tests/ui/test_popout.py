"""Pop out / Pop in：用真的瀏覽器點按鈕。

Pop out 把目前的分頁搬到另一個視窗：主視窗不再重複顯示那個分頁，只留說明；其他分頁照常使用。
兩邊的修改即時同步；跳到另一個視窗的分頁時，交給擁有那個分頁的視窗顯示。執行方式見 tests/ui/conftest.py。
"""
from __future__ import annotations


def _pop_out(ui, page):
    with ui.context.expect_page() as info:
        page.click(".tab-tools button:has-text('Pop out')")
    win = ui.watch(info.value, "pop")
    win.set_viewport_size({"width": 1600, "height": 950})
    win.wait_for_selector("#result:not([hidden]) .tab-body *")
    win.wait_for_timeout(500)
    return win


def test_pop_out_moves_the_tab_and_keeps_windows_in_sync(ui):
    main = ui.run_sample()
    w = _pop_out(ui, main)

    # 主視窗：結果搬出去了，換到配對；結果分頁標上 ↗，點進去只有說明，不重複顯示表格
    assert ui.state("state.tab") == "match"
    assert main.locator(".tab.away:has-text('結果') .away-mark").count() == 1
    main.click(".tab:has-text('結果')")
    assert main.is_visible(".popped-note:has-text('在 pop out 視窗')") and main.locator("table.grid").count() == 0
    assert not main.is_visible(".tab-tools button:has-text('Pop out')")   # 已經搬出去的分頁不能再搬一次

    # pop out 視窗：只有結果這個分頁，沒有左欄和流程卡片，表格用滿寬度
    assert w.locator(".tab").all_inner_texts()[0].startswith("結果") and w.locator(".tab").count() == 1
    assert w.inner_text("#popInButton") == "Pop in"
    assert not w.is_visible(".setup") and not w.is_visible("#pipeline")
    rows = w.locator("table.grid tbody tr")
    review = rows.count()
    w.click(".chip:has-text('全部')")
    assert rows.count() > review
    w.fill("input.search", "LED")
    w.wait_for_timeout(400)
    assert rows.count() == 2
    w.fill("input.search", "")
    w.wait_for_timeout(400)
    w.click("summary:has-text('檢視')")
    w.click(".menu-body label:has-text('匯率') input")
    assert "匯率" not in w.locator("table.grid thead th").all_inner_texts()
    w.click(".menu-body label:has-text('匯率') input")
    w.click("summary:has-text('檢視')")
    ui.view('換行', page=w)
    assert w.locator("table.grid.wrap").count() == 1
    ui.view('換行', page=w)

    # 在 pop out 視窗修改 → 主視窗同步
    ui.row("INV-1006", page=w).click()
    amount = ui.field("金額", page=w).locator("input")
    amount.fill("300")
    amount.press("Enter")
    ui.settle(w)
    assert ui.state("state.result.output.rows.find(r => r.rid === 'invoice:9').values['金額']") == 300
    name = ui.field("品名", page=w).locator("textarea")
    name.click()
    name.press("End")
    name.press("Shift+Enter")
    name.type("第二行")
    name.press("Enter")
    ui.settle(w)
    assert ui.state("state.result.output.rows.find(r => r.rid === 'invoice:9').values['品名']", page=w) == "線材組\n第二行"
    ui.field("品名", page=w).locator(".hint button:has-text('還原')").click()
    ui.settle(w)
    w.click("#drawer summary:has-text('這一列的處理過程')")
    ui.settle(w)
    assert "來自發票" in w.inner_text("#drawer .row-trace")
    ui.shot("popout-rows", page=w)

    # 從 pop out 視窗跳到配對：交給主視窗顯示
    ui.row("INV-1009", page=w).click()
    w.click("#drawer button:has-text('前往配對')")
    ui.settle()
    assert ui.state("state.tab") == "match" and ui.state("state.matchFocus") == "invoice:12"
    assert ui.state("state.tab", page=w) == "rows"
    # 在主視窗選配對 → pop out 視窗同步
    main.locator(".match-card:has-text('INV-1009') button:has-text('選這筆')").first.click()
    ui.settle(w)
    assert ui.state("state.result.output.rows.find(r => r.rid === 'invoice:12').values['報單號碼']", page=w)
    # 從主視窗的流程卡片跳到結果：交給 pop out 視窗顯示
    main.locator("#pipeline .stage", has_text="Export").click()
    main.click("#stageDetail li:has-text('需檢查') button:has-text('查看')")
    ui.settle(w)
    assert ui.state("state.filter", page=w) == "review" and ui.state("state.tab") == "match"

    # 另一個視窗更新時，正在打的字不會被清掉、也不會被自動存起來
    w.click(".chip:has-text('全部')")
    ui.row("INV-1005", page=w).click()
    qty = ui.field("數量", page=w).locator("input")
    qty.click()
    qty.fill("12")
    ui.page.evaluate("act('edit', {rid: 'invoice:11', column: '金額', value: '650'})")
    ui.settle(w)
    assert qty.input_value() == "12"
    assert ui.state("state.result.output.rows.find(r => r.rid === 'invoice:8').values['數量']", page=w) == 10
    qty.press("Escape")
    ui.settle(w)
    assert ui.state("state.result.output.rows.find(r => r.rid === 'invoice:11').values['金額']", page=w) == 650

    # 第二個分頁也搬出去：配對
    main.click(".tab:has-text('配對')")
    w2 = _pop_out(ui, main)
    assert w2.locator(".tab").count() == 1 and w2.locator(".match-card").count() >= 1
    assert ui.state("state.tab") not in ("rows", "match")
    assert main.is_visible(".tab-tools button:has-text('全部 Pop in')")

    # 主視窗重新整理、重新執行：還知道哪些分頁在外面，pop out 視窗跟著換到新的處理
    old_run = ui.state("state.result.run_id", page=w)
    main = ui.run_sample()
    ui.settle(w)
    assert ui.state("state.result.run_id", page=w) == ui.state("state.result.run_id") != old_run
    assert main.locator(".tab.away").count() == 2

    # Pop in：帶回篩選與選到的列，主視窗切到結果
    w.click(".chip:has-text('全部')")
    ui.row("INV-1003", page=w).click()
    w.click("#popInButton")
    main.wait_for_timeout(800)
    assert w.is_closed()
    assert ui.state("state.tab") == "rows" and ui.state("state.filter") == "all" and ui.state("state.selected") == "invoice:6"
    assert main.locator("table.grid").count() == 1 and main.locator(".tab.away").count() == 1
    # 全部 Pop in
    main.click(".tab-tools button:has-text('全部 Pop in')")
    main.wait_for_timeout(800)
    assert w2.is_closed() and main.locator(".tab.away").count() == 0
    ui.shot("popin-main")
