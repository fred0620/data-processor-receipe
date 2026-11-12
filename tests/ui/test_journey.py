"""檢查的流程：一開始就打開第一筆，看完確認後直接到下一筆，進度跟著走。"""
from __future__ import annotations


def _open_count(ui):
    return ui.state("state.result.output.rows.filter(r => r.status === 'review').length")


def test_first_row_opens_and_confirm_moves_to_next(ui):
    page = ui.run_sample()
    assert page.is_visible("#drawer"), "執行完就打開第一筆需檢查的列"
    first = ui.state("state.selected")
    assert first == ui.state("visibleRows()[0].rid")
    assert page.locator("table.grid tr.selected").count() == 1
    assert "需檢查 1 / 6" in page.inner_text(".drawer-foot")
    progress = page.inner_text("#progress")
    assert "已處理 0 / 6 列" in progress
    # 確認無誤，下一筆
    before = _open_count(ui)
    page.click(".drawer-foot button.primary")
    ui.settle()
    assert _open_count(ui) == before - 1
    second = ui.state("state.selected")
    assert second and second != first and "需檢查 1 / 5" in page.inner_text(".drawer-foot")
    assert "已處理 1 / 6 列" in page.inner_text("#progress")
    assert page.locator("#progress .meter i").evaluate("e => parseFloat(e.style.width)") > 0
    ui.shot("journey")


def test_keyboard_and_buttons_move_between_rows(ui):
    page = ui.run_sample()
    first = ui.state("state.selected")
    page.keyboard.press("j")
    second = ui.state("state.selected")
    assert second != first and "需檢查 2 / 6" in page.inner_text(".drawer-foot")
    page.keyboard.press("k")
    assert ui.state("state.selected") == first
    page.click(".drawer-foot button[aria-label='下一筆（J）']")
    assert ui.state("state.selected") == second
    page.click(".drawer-foot button[aria-label='上一筆（K）']")
    assert ui.state("state.selected") == first
    assert page.is_disabled(".drawer-foot button[aria-label='上一筆（K）']")
    # 在欄位裡打字時 J／K 不會換列
    qty = ui.field("數量").locator("input")
    qty.click()
    page.keyboard.press("j")
    assert ui.state("state.selected") == first and qty.input_value().endswith("j")
    qty.press("Escape")


def test_must_handle_issues_cannot_be_bulk_confirmed(ui):
    """缺資料或要做決定的警示（不在對照表、找不到配對）不能被「確認無誤，下一筆」順手確認掉。"""
    page = ui.run_sample()
    ui.row("INV-1005").click()                       # 運送方式「陸運」不在對照表，也找不到報關單
    foot = page.locator(".drawer-foot")
    assert foot.locator("button.primary").count() == 0
    assert "還有 2 個要處理" in foot.inner_text()
    before = _open_count(ui)
    foot.locator("button:has-text('跳過')").click()
    assert _open_count(ui) == before and ui.state("state.selected") != "invoice:8", "跳過不會確認任何東西"
    # 處理掉：補上對照，找不到配對的那個還在，仍然不能一鍵確認
    ui.row("INV-1005").click()
    issue = page.locator("#drawer .issue:has-text('不在對照表')")
    issue.locator(".inline-fix select").select_option("SEA")
    issue.locator("button:has-text('補上對照')").click()
    ui.settle()
    assert "還有 1 個要處理" in page.inner_text(".drawer-foot")
    # 真的沒問題時，還是可以在那個警示上個別確認
    page.locator("#drawer .issue:has-text('找不到') .link:text-is('確認無誤')").click()
    ui.settle()
    assert ui.state("state.result.output.rows.find(r => r.rid === 'invoice:8').status") == "confirmed"
    ui.shot("must-handle")


def test_judgement_rows_confirm_in_one_click(ui):
    page = ui.run_sample()
    ui.row("INV-1003").click()                       # 只有「金額不一致」要人判斷
    page.click(".drawer-foot button.primary:has-text('確認無誤，下一筆')")
    ui.settle()
    assert ui.state("state.result.output.rows.find(r => r.rid === 'invoice:6').status") == "confirmed"
    assert ui.state("state.selected") != "invoice:6"


def test_fill_mapping_inside_the_row(ui):
    """不在對照表：直接在細節裡補，不用離開正在檢查的列。"""
    page = ui.run_sample()
    ui.row("INV-1005").click()
    issue = page.locator("#drawer .issue:has-text('不在對照表')")
    assert issue.locator(".inline-fix select").count() == 1
    assert issue.locator("button.link:text-is('補對照')").count() == 0
    issue.locator(".inline-fix select").select_option("SEA")
    issue.locator("button:has-text('補上對照')").click()
    ui.settle()
    assert ui.state("state.tab") == "rows" and ui.state("state.selected") == "invoice:8"
    assert ui.state("state.result.output.rows.find(r => r.rid === 'invoice:8').values['運送方式']") == "SEA"
    assert "已補對照" in page.inner_text("#drawer")


def test_one_number_for_progress(ui):
    """同一件事只用一種單位（列）：右上角、進度、結果分頁的數字一致。"""
    page = ui.run_sample()
    rows = ui.state("state.result.output.rows.filter(r => r.status === 'review').length")
    assert page.inner_text("#runStatus").strip() == f"{rows} 列需檢查"
    assert page.locator(".tab:has-text('結果') .count").inner_text() == str(rows)
    assert f"/ {rows} 列" in page.inner_text("#progress")
    # 流程維持 Load → Export 的卡片：每一步都是一張卡片，寫著這一步的摘要
    cards = page.locator("#pipeline .stage")
    for i in range(cards.count()):
        card = cards.nth(i)
        if "skip" in (card.get_attribute("class") or ""):
            continue
        assert card.locator(".summary").is_visible() and card.locator(".summary").inner_text().strip(), card.inner_text()
        assert card.bounding_box()["height"] >= 56, "卡片要放得下名稱與摘要兩行"
