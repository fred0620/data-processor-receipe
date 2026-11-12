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


def _open_full_sheet(ui, page):
    """從小卡打開完整工作表：預設開在自己的視窗。"""
    with ui.context.expect_page() as info:
        page.locator("#peek button:has-text('完整工作表')").click()
    w = ui.watch(info.value, "sheet")
    w.wait_for_selector(".source-grid tr.src-target")
    return w


def test_full_sheet_opens_in_its_own_window(ui):
    page = ui.run_sample()
    ui.row("INV-1003").click()
    ui.field("金額").hover()
    ui.field("金額").locator("button.cell-link").click()
    w = _open_full_sheet(ui, page)
    assert ui.state("state.tab") == "rows" and page.is_visible("#drawer"), "主視窗留在正在檢查的列"
    assert page.locator("#peek").count() == 0
    assert w.locator(".source-grid td.src-cell").inner_text() == "2,000"
    assert w.locator(".source-grid thead th.target-col").inner_text() == "E"
    assert "第 3 列是「發票」的表頭" in w.inner_text(".source-legend")
    assert w.title().startswith("發票明細") and "發票明細" in w.inner_text(".tab-body .toolbar")
    assert not w.is_visible(".result-head") and not w.is_visible("#progress"), "工作表視窗只放工作表"
    # 主視窗的原始資料分頁：這張工作表在外面，只留說明
    page.click(".tab:has-text('原始資料')")
    assert page.is_visible(".popped-note:has-text('發票明細')") and page.locator(".tab-body .source-grid").count() == 0
    # 再看同一張表的另一格：交給已經開著的視窗，不會多開
    page.click(".tab:has-text('結果')")
    ui.row("INV-1005").click()
    ui.field("金額").hover()
    ui.field("金額").locator("button.cell-link").click()
    page.locator("#peek button:has-text('完整工作表')").click()
    w.locator(".source-grid tr.src-target th.rowno:text-is('8')").wait_for()
    assert len(ui.context.pages) == 2
    ui.shot("sheet-window", page=w)


def test_compare_two_sheets_side_by_side(ui):
    """配對時把發票與報關單各開一個視窗並排比對，兩個視窗各自跟著要看的那一列。"""
    page = ui.run_sample()
    page.click(".tab:has-text('配對')")
    page.click(".chip:has-text('全部 9')")
    card = page.locator(".match-card:has-text('INV-1001')").first
    card.locator(".side").nth(0).locator("button.row-source").click()      # 發票那一列
    invoice = _open_full_sheet(ui, page)
    card.locator(".side").nth(1).locator("button.row-source").click()      # 報關單那一列
    declaration = _open_full_sheet(ui, page)
    assert invoice.title().startswith("發票明細") and declaration.title().startswith("報關單")
    assert _target_row(invoice) == 4 and _target_row(declaration) == 2
    # 換另一筆配對：兩個視窗都跳到新的那一列，不會多開
    card = page.locator(".match-card:has-text('INV1002')").first
    card.locator(".side").nth(0).locator("button.row-source").click()
    page.locator("#peek button:has-text('完整工作表')").click()
    invoice.locator(".source-grid tr.src-target th.rowno:text-is('5')").wait_for()
    card.locator(".side").nth(1).locator("button.row-source").click()
    page.locator("#peek button:has-text('完整工作表')").click()
    declaration.locator(".source-grid tr.src-target th.rowno:text-is('3')").wait_for()
    assert len(ui.context.pages) == 3
    # 從工作表視窗也能把另一張表開出來
    invoice.click("summary:has-text('並排比對')")
    with ui.context.expect_page() as info:
        invoice.click(".menu-item:has-text('匯率')")
    rates = ui.watch(info.value, "rates")
    rates.wait_for_selector(".source-grid")
    assert rates.title().startswith("匯率")
    rowno = rates.locator(".source-grid tbody th.rowno").first.bounding_box()["width"]
    assert rowno <= 60, f"欄數少的工作表，列號欄不能被拉寬（{rowno}px）"
    # 主視窗的原始資料分頁標出哪些工作表在外面
    page.click(".tab:has-text('原始資料')")
    labels = page.locator(".tab-body .toolbar .chips").first.inner_text()
    assert labels.count("↗") == 3
    # Pop in：工作表回到主視窗，帶回看到的那一列
    invoice.click("#popInButton")
    page.wait_for_timeout(800)
    assert invoice.is_closed()
    assert ui.state("state.tab") == "source" and ui.state("state.source.sheet") == "發票明細"
    assert _target_row(page.locator(".tab-body")) == 5
    page.click(".tab-tools button:has-text('全部 Pop in')")
    page.wait_for_timeout(800)
    assert declaration.is_closed() and rates.is_closed()
    ui.shot("compare-sheets", page=page)


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
    w = _open_full_sheet(ui, page)
    page = w
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
