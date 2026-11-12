"""原始資料：回到上傳的 Excel 核對。從細節、欄位、配對卡片、排除的列都能跳到原本的那一列或那一格。"""
from __future__ import annotations


def _target_row(page):
    return int(page.locator(".source-grid tr.src-target th.rowno").inner_text())


def test_open_original_row_and_cell_from_drawer(ui):
    page = ui.run_sample()
    ui.row("INV-1003").click()
    section = page.locator("#drawer section:has(h4:text-is('原始 Excel'))")
    assert "發票明細・第 6 列" in section.inner_text()
    assert "報關" in section.inner_text()                                  # 配對帶進來的報關單也列出來
    section.locator(".source-item").first.locator("button:has-text('看原始資料')").click()
    page.wait_for_selector(".source-grid")
    assert ui.state("state.tab") == "source"
    assert page.is_visible("#drawer"), "看原始資料時細節留著，可以左右對照"
    assert _target_row(page) == 6
    header = page.locator(".source-grid tr.src-header")
    assert header.locator("th.rowno").inner_text() == "3" and "金額" in header.inner_text()
    assert "第 3 列是「發票」的表頭" in page.inner_text(".source-legend")
    # 欄位旁邊的儲存格位置：直接看那一格原本寫的是什麼
    ui.field("金額").hover()
    ui.field("金額").locator("button.cell-link").click()
    ui.settle()
    cell = page.locator(".source-grid td.src-cell")
    assert cell.count() == 1 and cell.inner_text() == "2,000"
    assert page.locator(".source-grid thead th.target-col").inner_text() == "E"
    assert "E6" in page.inner_text(".source-legend")
    ui.shot("source-cell")


def test_sheet_switch_jump_and_paging(ui):
    page = ui.run_sample()
    page.click(".tab:has-text('原始資料')")
    page.wait_for_selector(".source-grid")
    chips = page.locator(".tab-body .chips .chip")
    assert chips.count() == 3 and "發票" in chips.first.inner_text()
    page.locator(".tab-body .chips .chip").nth(1).click()
    page.wait_for_selector(".source-grid")
    assert page.locator(".tab-body .chips .chip.active").inner_text() == chips.nth(1).inner_text()
    assert page.is_disabled("button[aria-label='上一段']") and page.is_disabled("button[aria-label='下一段']")
    page.locator(".tab-body .chips .chip").first.click()
    page.wait_for_selector(".source-grid")
    page.fill("input.jump", "10")
    page.press("input.jump", "Enter")
    ui.settle()
    assert _target_row(page) == 10


def test_open_original_from_match_card_and_excluded(ui):
    page = ui.run_sample()
    page.click(".tab:has-text('配對')")
    page.click(".chip:has-text('全部')")
    card = page.locator(".match-card:has-text('INV-1001')").first
    card.locator(".side").nth(1).locator("button.row-source").click()     # 報關單那一列
    page.wait_for_selector(".source-grid")
    assert "報關" in page.locator(".tab-body .chips .chip.active").inner_text() and _target_row(page) == 2
    page.click(".tab:has-text('排除')")
    page.locator("table.grid tbody td.rowno button").first.click()
    page.wait_for_selector(".source-grid")
    assert ui.state("state.tab") == "source" and _target_row(page) == ui.state("state.result.excluded[0].row")


def test_original_in_pop_out_window(ui):
    page = ui.run_sample()
    page.click(".tab:has-text('原始資料')")
    page.wait_for_selector(".source-grid")
    with ui.context.expect_page() as info:
        page.click(".tab-tools button:has-text('Pop out')")
    w = ui.watch(info.value, "pop")
    w.wait_for_selector(".source-grid")
    # 主視窗看結果、另一個螢幕看原始資料：點欄位的儲存格位置，交給 pop out 視窗顯示
    page.click(".tab:has-text('結果')")
    ui.row("INV-1003").click()
    ui.field("金額").hover()
    ui.field("金額").locator("button.cell-link").click()
    w.wait_for_selector(".source-grid td.src-cell")
    assert w.locator(".source-grid td.src-cell").inner_text() == "2,000"
    assert ui.state("state.tab") == "rows" and page.is_visible("#drawer")
    ui.shot("source-popout", page=w)


def test_horizontal_scroll_snaps_to_column(ui):
    """要看的格子在右邊時，左右捲動要對齊到欄的開頭，不能把左邊的欄位切一半。"""
    ui.context.pages[0].set_viewport_size({"width": 1180, "height": 800})
    page = ui.run_sample()
    ui.row("INV-1003").click()
    ui.field("金額").hover()
    ui.field("金額").locator("button.cell-link").click()
    page.wait_for_selector(".source-grid td.src-cell")
    page.wait_for_timeout(300)
    view = page.evaluate("""() => {
      const wrap = document.querySelector('.source-wrap');
      const edge = wrap.querySelector('tbody th.rowno').getBoundingClientRect().right;
      const lefts = [...wrap.querySelectorAll('thead th')].slice(1).map((th) => th.getBoundingClientRect().left);
      const cell = wrap.querySelector('td.src-cell').getBoundingClientRect();
      return { scroll: wrap.scrollLeft, edge, lefts, cellRight: cell.right, wrapRight: wrap.getBoundingClientRect().right };
    }""")
    assert view["cellRight"] <= view["wrapRight"] + 1, "要看的格子要完整看得到"
    if view["scroll"] > 0:   # 有左右捲動時，列號右邊緊接著的必須是一欄的開頭，不能切到半欄
        assert any(abs(left - view["edge"]) <= 1 for left in view["lefts"]), view
    ui.shot("source-snap")
