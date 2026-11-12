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


def test_finishing_all_rows(ui):
    page = ui.run_sample()
    for _ in range(12):
        if not page.locator(".drawer-foot button.primary").count():
            break
        page.click(".drawer-foot button.primary")
        ui.settle()
    assert _open_count(ui) == 0
    assert "都已處理，可以下載" in page.inner_text("#progress")
    assert page.is_visible(".note:has-text('沒有需要檢查的列')")
