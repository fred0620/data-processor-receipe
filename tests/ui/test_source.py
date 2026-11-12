"""原始資料：回到上傳的 Excel 核對。從細節、欄位、配對卡片、排除的列都能跳到原本的那一列或那一格。"""
from __future__ import annotations


def _target_row(scope):
    return int(scope.locator(".source-grid tr.src-target th.rowno").inner_text())


def test_peek_original_cell_beside_the_row(ui):
    """看原始資料預設在旁邊跳出小卡：不離開正在檢查的列，才能對照。"""
    page = ui.run_sample()
    ui.row("INV-1003").click()
    ui.field("金額").hover()
    ui.field("金額").locator("button.cell-link").click()
    card = page.locator("#peek")
    card.locator("td.src-cell").wait_for()
    assert ui.state("state.tab") == "rows" and page.is_visible("#drawer"), "不換分頁，細節留著"
    assert card.locator("td.src-cell").inner_text() == "2,000"
    compare = card.locator(".peek-compare").inner_text()
    assert "2,000" in compare and "2000" in compare, "原始與整理後的值並排"
    assert card.locator("tr.src-header th.rowno").inner_text() == "3"           # 表頭
    rows = [int(x) for x in card.locator("tbody th.rowno").all_inner_texts() if x.isdigit()]
    assert rows == [3, 4, 5, 6, 7, 8], "表頭加上那一列的前後兩列"
    # 小卡不擋住細節：可以邊看邊改
    box, drawer = card.bounding_box(), page.locator("#drawer").bounding_box()
    assert box["x"] + box["width"] <= drawer["x"] + drawer["width"]
    ui.shot("peek")
    page.keyboard.press("Escape")
    assert card.count() == 0 and page.is_visible("#drawer"), "Esc 先關小卡，細節還在"
    # 這一列的來源（發票、報關單、匯率表）
    section = page.locator("#drawer section:has(h4:text-is('原始 Excel'))")
    assert "發票明細・第 6 列" in section.inner_text() and "報關" in section.inner_text()
    section.locator("button:has-text('報關單')").first.click()
    card.locator("tr.src-target").wait_for()
    assert "報關單" in card.locator(".peek-title").inner_text()
    page.mouse.click(5, 300)                                                      # 點外面關掉
    assert card.count() == 0


def test_peek_opens_full_sheet(ui):
    page = ui.run_sample()
    ui.row("INV-1003").click()
    ui.field("金額").hover()
    ui.field("金額").locator("button.cell-link").click()
    page.locator("#peek button:has-text('完整工作表')").click()
    page.wait_for_selector(".tab-body .source-grid td.src-cell")
    assert ui.state("state.tab") == "source" and page.locator("#peek").count() == 0
    assert page.locator(".source-grid td.src-cell").inner_text() == "2,000"
    assert page.locator(".source-grid thead th.target-col").inner_text() == "E"
    assert "第 3 列是「發票」的表頭" in page.inner_text(".source-legend")
    assert page.is_visible("#drawer"), "看完整工作表時細節留著"


def test_sheet_switch_jump_and_paging(ui):
    page = ui.run_sample()
    page.click(".tab:has-text('原始資料')")
    page.wait_for_selector(".source-grid")
    chips = page.locator(".tab-body .toolbar .chips").first.locator(".chip")
    assert chips.count() == 3 and "發票" in chips.first.inner_text()
    chips.nth(1).click()
    page.wait_for_selector(".source-grid")
    assert page.locator(".tab-body .toolbar .chips").first.locator(".chip.active").inner_text() == chips.nth(1).inner_text()
    assert page.is_disabled("button[aria-label='上一段']") and page.is_disabled("button[aria-label='下一段']")
    chips.first.click()
    page.wait_for_selector(".source-grid")
    page.fill("input.jump", "10")
    page.press("input.jump", "Enter")
    ui.settle()
    assert _target_row(page) == 10


def test_peek_from_match_card_and_excluded(ui):
    page = ui.run_sample()
    page.click(".tab:has-text('配對')")
    page.click(".chip:has-text('全部 9')")
    card = page.locator(".match-card:has-text('INV-1001')").first
    card.locator(".side").nth(1).locator("button.row-source").click()     # 報關單那一列
    peek = page.locator("#peek")
    peek.locator("tr.src-target").wait_for()
    assert "報關單" in peek.inner_text() and _target_row(peek) == 2 and ui.state("state.tab") == "match"
    page.keyboard.press("Escape")
    page.click(".tab:has-text('排除')")
    page.locator("table.grid tbody td.rowno button").first.click()
    peek.locator("tr.src-target").wait_for()
    assert _target_row(peek) == ui.state("state.result.excluded[0].row") and ui.state("state.tab") == "excluded"


def test_full_sheet_in_pop_out_window(ui):
    """原始資料 pop out 到另一個螢幕：小卡的「完整工作表」交給那個視窗顯示。"""
    page = ui.run_sample()
    page.click(".tab:has-text('原始資料')")
    page.wait_for_selector(".source-grid")
    with ui.context.expect_page() as info:
        page.click(".tab-tools button:has-text('Pop out')")
    w = ui.watch(info.value, "pop")
    w.wait_for_selector(".source-grid")
    page.click(".tab:has-text('結果')")
    ui.row("INV-1003").click()
    ui.field("金額").hover()
    ui.field("金額").locator("button.cell-link").click()
    page.locator("#peek button:has-text('完整工作表')").click()
    w.wait_for_selector(".source-grid td.src-cell")
    assert w.locator(".source-grid td.src-cell").inner_text() == "2,000"
    assert ui.state("state.tab") == "rows" and page.is_visible("#drawer")


def test_horizontal_scroll_snaps_to_column(ui):
    """要看的格子在右邊時，左右捲動要對齊到欄的開頭，不能把左邊的欄位切一半。"""
    ui.context.pages[0].set_viewport_size({"width": 1180, "height": 800})
    page = ui.run_sample()
    ui.row("INV-1003").click()
    ui.field("金額").hover()
    ui.field("金額").locator("button.cell-link").click()
    page.locator("#peek button:has-text('完整工作表')").click()
    page.wait_for_selector(".tab-body .source-grid td.src-cell")
    page.wait_for_timeout(300)
    view = page.evaluate("""() => {
      const wrap = document.querySelector('.tab-body .source-wrap');
      const edge = wrap.querySelector('tbody th.rowno').getBoundingClientRect().right;
      const lefts = [...wrap.querySelectorAll('thead th')].slice(1).map((th) => th.getBoundingClientRect().left);
      const cell = wrap.querySelector('td.src-cell').getBoundingClientRect();
      return { scroll: wrap.scrollLeft, edge, lefts, cellRight: cell.right, wrapRight: wrap.getBoundingClientRect().right };
    }""")
    assert view["cellRight"] <= view["wrapRight"] + 1, "要看的格子要完整看得到"
    if view["scroll"] > 0:   # 有左右捲動時，列號右邊緊接著的必須是一欄的開頭，不能切到半欄
        assert any(abs(left - view["edge"]) <= 1 for left in view["lefts"]), view
    ui.shot("source-snap")
