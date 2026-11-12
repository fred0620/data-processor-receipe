"""主視窗的檢查流程：流程卡片、結果表、單列細節、配對、對照表、警示、重新檢查、下載。"""
from __future__ import annotations

import openpyxl


def test_stage_cards_link_to_rows(ui):
    page = ui.run_sample()
    cards = page.locator("#pipeline .stage")
    assert cards.count() == 8
    statuses = dict(zip(ui.state("state.result.stages.map(s => s.id)"), ui.state("state.result.stages.map(s => s.status)")))
    for stage_id, status in statuses.items():
        assert page.locator(f"#pipeline .stage.{status}").count() >= 1, stage_id
    # 每張有問題的卡片都能用「查看」跳到相關的地方
    page.locator("#pipeline .stage", has_text="Normalize").click()
    assert page.is_visible("#stageDetail")
    page.locator("#stageDetail button:has-text('查看')").first.click()
    ui.settle()
    assert ui.state("state.tab") == "issues" and page.is_visible(".badge:has-text('只看')")
    page.locator("#pipeline .stage", has_text="Gate").click()
    page.locator("#stageDetail button:has-text('查看')").first.click()
    assert ui.state("state.tab") == "excluded"
    page.locator("#pipeline .stage", has_text="Match").click()
    page.locator("#stageDetail button:has-text('查看')").first.click()
    assert ui.state("state.tab") == "match"
    ui.shot("stage-detail")


def test_table_tools_and_colors(ui):
    page = ui.run_sample()
    rows = page.locator("table.grid tbody tr")
    review = rows.count()
    page.click(".chip:has-text('全部')")
    assert rows.count() > review
    assert page.locator("table.grid tbody .dot.ok").count() >= 1           # 綠色：正確
    assert page.locator("table.grid tbody .dot.review").count() >= 1       # 橘色：需檢查
    page.fill("input.search", "1003")
    page.wait_for_timeout(400)
    assert rows.count() == 1
    page.fill("input.search", "")
    page.wait_for_timeout(400)
    page.click("summary:has-text('欄位')")
    page.click(".menu-body label:has-text('匯率') input")
    assert "匯率" not in page.locator("table.grid thead th").all_inner_texts()
    assert page.is_visible(".menu-body")                                    # 勾選時選單不會收起
    page.click(".menu-body label:has-text('匯率') input")
    page.click("summary:has-text('欄位')")
    page.click("button:has-text('顯示換行')")
    multi = ui.row("INV-1003").locator("td .cell-text").nth(2)
    assert "附電源線" in multi.inner_text() and "↵" not in multi.inner_text()
    page.click("button:has-text('壓成一行')")
    assert "↵" in ui.row("INV-1003").locator("td .cell-text").nth(2).inner_text()
    page.click("button:has-text('緊湊')")
    assert page.locator("table.grid.dense").count() == 1
    page.click("button:has-text('寬鬆')")
    # 確認一列後變成藍色的已確認
    ui.row("INV-1008").click()
    ui.field("幣別").locator("..").page.locator("#drawer button:has-text('確認無誤')").first.click()
    ui.settle()
    page.click(".chip:has-text('已確認')")
    assert ui.row("INV-1008").locator(".dot.confirmed").count() == 1         # 藍色：已確認
    ui.shot("table-confirmed")


def test_drawer_edit_revert_multiline_and_trace(ui):
    page = ui.run_sample()
    ui.row("INV-1006").click()
    assert page.is_visible("#drawer")
    amount = ui.field("金額").locator("input")
    amount.fill("300")
    amount.press("Enter")
    ui.settle()
    assert ui.state("state.result.output.rows.find(r => r.rid === 'invoice:9').values['金額']") == 300
    assert ui.row("INV-1006").locator("td.cell-edited").count() == 1
    assert ui.field("金額").locator(".hint").inner_text().startswith("原值")
    # 處理過的警示留在「處理紀錄」，不會直接消失
    assert page.is_visible("#drawer h4:text-is('處理紀錄')")
    assert "已人工修改" in page.locator("#drawer .issue.dismissed").first.inner_text()
    # 多行文字：Shift+Enter 換行、Enter 儲存，文字框跟著長高
    name = ui.field("品名").locator("textarea")
    name.click()
    name.press("End")
    name.press("Shift+Enter")
    name.type("第二行")
    height = name.evaluate("e => e.offsetHeight")
    name.press("Enter")
    ui.settle()
    assert ui.state("state.result.output.rows.find(r => r.rid === 'invoice:9').values['品名']") == "線材組\n第二行"
    assert ui.field("品名").locator("textarea").evaluate("e => e.offsetHeight") >= height
    ui.field("品名").locator(".hint button:has-text('還原')").click()
    ui.settle()
    assert ui.state("state.result.output.rows.find(r => r.rid === 'invoice:9').values['品名']") == "線材組"
    # Esc 取消，不會存
    qty = ui.field("數量").locator("input")
    qty.fill("99")
    qty.press("Escape")
    ui.settle()
    assert ui.state("state.result.output.rows.find(r => r.rid === 'invoice:9').values['數量']") == 5
    # 執行紀錄：好奇時才展開
    ui.field("金額").locator("button.why").click()
    ui.settle()
    assert "儲存格原本是" in ui.field("金額").locator(".trace").inner_text()
    page.click("#drawer summary:has-text('這一列的處理過程')")
    ui.settle()
    assert "來自發票" in page.locator("#drawer .row-trace .trace").inner_text()
    ui.shot("drawer")
    page.click("#drawerClose")
    assert page.is_hidden("#drawer")


def test_match_pick_confirm_and_none(ui):
    page = ui.run_sample()
    page.click(".tab:has-text('配對')")
    card = page.locator(".match-card:has-text('INV-1009')").first
    assert "待選擇" in card.inner_text() or "選這筆" in card.inner_text()
    card.locator("button:has-text('選這筆')").first.click()
    ui.settle()
    rows = "state.result.matches[0].rows"
    assert ui.state(f"{rows}.find(r => r.left === 'invoice:12').status") == "manual"
    other = page.locator(".match-card:has-text('INV-1010')").first
    assert "人工配給別列" in other.inner_text()                               # 刪去法剩下的要確認，寫明原因
    other.locator("button:has-text('確認正確')").click()
    ui.settle()
    assert ui.state(f"{rows}.find(r => r.left === 'invoice:13').status") == "confirmed"
    page.click(".chip:has-text('全部')")
    card = page.locator(".match-card:has-text('INV-1008')").first
    card.locator("button:has-text('沒有配對')").click()
    ui.settle()
    chosen = ui.state(f"{rows}.find(r => r.left === 'invoice:11')")
    assert chosen["status"] == "none" and chosen["how"] == "人工：沒有配對" and not chosen["open"]
    ui.shot("match")


def test_mapping_fill_add_value_and_remove(ui):
    page = ui.run_sample()
    page.click(".tab:has-text('對照表')")
    page.select_option(".map-row select", "__new")
    page.fill(".map-row input", "TRUCK")
    page.click(".map-row button:has-text('儲存')")
    ui.settle()
    assert not ui.state("state.result.unmapped.length")
    assert page.is_visible(".badge:has-text('自訂值')")
    page.click("button.danger:has-text('移除')")
    ui.settle()
    assert ui.state("state.result.unmapped.length") == 1
    page.select_option(".map-row select", "SEA")
    page.click(".map-row button:has-text('儲存')")
    ui.settle()
    assert not ui.state("state.result.unmapped.length")


def test_issues_bulk_confirm_and_handled_records(ui):
    page = ui.run_sample()
    ui.row("INV-1006").click()
    amount = ui.field("金額").locator("input")
    amount.fill("300")
    amount.press("Enter")
    ui.settle()
    page.click(".tab:has-text('所有警示')")
    open_before = ui.state("state.result.issues.filter(i => !i.dismissed && i.level === 'review').length")
    page.click("button:has-text('全選')")
    page.click("button:has-text('確認無誤（')")
    ui.settle()
    assert ui.state("state.result.issues.filter(i => !i.dismissed && i.level === 'review').length") < open_before
    page.click(".chip:has-text('已處理')")
    handled = page.locator(".issue-list").inner_text()
    assert "已人工修改" in handled and "已確認" in handled
    # 人工修改的紀錄不能在這裡取消，要到原本的地方還原
    edited = page.locator(".issue-row:has-text('約 300')").first
    assert edited.locator("input[type=checkbox]").is_disabled()
    page.locator("#pipeline .stage", has_text="Normalize").click()
    assert "已處理" in page.inner_text("#stageDetail") and "已確認" not in page.inner_text("#stageDetail")
    ui.shot("issues-handled")


def test_reset_restore_and_reload_keeps_decisions(ui):
    page = ui.run_sample()
    assert page.is_disabled("#resetButton")
    ui.row("INV-1006").click()
    amount = ui.field("金額").locator("input")
    amount.fill("300")
    amount.press("Enter")
    ui.settle()
    # 關掉重開，同一份檔案會接著上次的檢查
    page = ui.run_sample()
    assert ui.state("state.result.decisions") == 1
    page.click("#resetButton")
    assert "清掉 1 項" in page.inner_text("#resetButton")
    page.wait_for_timeout(4300)                                               # 沒按第二次就恢復
    assert page.inner_text("#resetButton") == "重新檢查"
    page.click("#resetButton")
    page.click("#resetButton")
    ui.settle()
    assert ui.state("state.result.decisions") == 0
    assert page.is_visible(".toast-action")
    page.click(".toast-action")
    ui.settle()
    assert ui.state("state.result.decisions") == 1


def test_export_has_all_sheets(ui, tmp_path):
    page = ui.run_sample()
    with page.expect_download() as download:
        page.click("#exportButton")
    target = tmp_path / "out.xlsx"
    download.value.save_as(target)
    book = openpyxl.load_workbook(target)
    assert {"整理結果", "待檢查", "配對明細", "排除", "對照待補"} <= set(book.sheetnames)
