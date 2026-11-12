"""原始資料：回到上傳的 Excel 核對。從細節、欄位、配對卡片、排除的列都能跳到原本的那一列或那一格。"""
from __future__ import annotations

from playwright.sync_api import expect


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


def _assert_snapped(page, side=None):
    """要看的格子完整看得到；有左右捲動時，列號右邊緊接著一欄的開頭，不能切到半欄。"""
    scope = f".tab-body .source-pane[data-side='{side}']" if side else ".tab-body .source-pane"
    page.wait_for_timeout(400)
    view = page.evaluate("""(scope) => {
      const wrap = document.querySelector(scope + ' .source-wrap');
      const fixed = wrap.querySelector('tbody td.mark') || wrap.querySelector('tbody th.rowno');   // 固定在左邊的最後一欄
      const edge = fixed.getBoundingClientRect().right;
      const lefts = [...wrap.querySelectorAll('thead th:not(.corner):not(.mark-col)')].map((th) => th.getBoundingClientRect().left);
      const cell = wrap.querySelector('td.src-cell').getBoundingClientRect();
      return { scroll: wrap.scrollLeft, edge, lefts, cellRight: cell.right, wrapRight: wrap.getBoundingClientRect().right };
    }""", scope)
    assert view["cellRight"] <= view["wrapRight"] + 1, "要看的格子要完整看得到"
    if view["scroll"] > 0:
        assert any(abs(left - view["edge"]) <= 1 for left in view["lefts"]), view


def _pane(page, side):
    return page.locator(f".tab-body .source-pane[data-side='{side}']")


def _open_full_sheet(page):
    """從小卡打開完整工作表：在這個視窗的原始資料分頁。"""
    page.locator("#peek button:has-text('完整工作表')").click()
    page.wait_for_selector(".tab-body .source-grid tr.src-target")


def test_full_sheet_splits_with_matched_sheet(ui):
    """完整工作表在同一個視窗打開；這一列有配對時左右並排，兩邊都標出對應的那一列。"""
    page = ui.run_sample()
    ui.row("INV-1003").click()
    ui.field("金額").hover()
    ui.field("金額").locator("button.cell-link").click()
    _open_full_sheet(page)
    assert len(ui.context.pages) == 1, "不開新視窗"
    assert ui.state("state.tab") == "source" and page.is_visible("#drawer"), "細節留著，可以邊看邊改"
    left, right = _pane(page, "左"), _pane(page, "右")
    assert left.locator("select.sheet-select").input_value() == "發票明細"
    assert right.locator("select.sheet-select").input_value() == "報關單"
    assert left.locator("td.src-cell").inner_text() == "2,000"
    assert left.locator("thead th.target-col").inner_text() == "E"
    assert _target_row(left) == 6 and _target_row(right) == ui.state(
        "Number(Object.values(state.result.output.rows.find(r => r.rid === 'invoice:6').links).find(v => v.startsWith('declaration')).split(':').pop())")
    assert "第 3 列是「發票」的表頭" in left.locator(".source-legend").inner_text()
    _assert_snapped(page, "左")
    for side in (left, right):   # 窄的時候工作表選單也要看得到名稱
        assert side.locator("select.sheet-select").bounding_box()["width"] >= 130
    # 兩邊並排，各自捲動
    lb, rb = left.bounding_box(), right.bounding_box()
    assert abs(lb["y"] - rb["y"]) < 2 and lb["x"] + lb["width"] <= rb["x"]
    ui.shot("source-split")
    # 從報關單那一列打開：報關單仍然放右邊，發票明細放左邊
    page.click(".tab:has-text('結果')")
    ui.row("INV-1003").click()
    section = page.locator("#drawer section:has(h4:text-is('原始 Excel'))")
    section.locator("button:has-text('報關單')").first.click()
    _open_full_sheet(page)
    assert left.locator("select.sheet-select").input_value() == "發票明細" and _target_row(left) == 6
    assert right.locator("select.sheet-select").input_value() == "報關單"


def test_split_panes_switch_jump_and_close(ui):
    """左右兩邊各自切換工作表、跳列、翻頁；可以交換、關掉右邊。"""
    page = ui.run_sample()
    page.click(".tab:has-text('原始資料')")
    page.wait_for_selector(".source-grid")
    assert page.locator(".tab-body .source-pane").count() == 1
    page.click(".tab-body [role=switch]:has-text('左右並排')")
    page.wait_for_selector(".tab-body .source-pane[data-side='右'] .source-grid")
    left, right = _pane(page, "左"), _pane(page, "右")
    assert left.locator("select.sheet-select").input_value() == "發票明細"
    assert right.locator("select.sheet-select").input_value() == "報關單"
    right.locator("select.sheet-select").select_option("匯率")
    expect(right.locator(".range")).to_contain_text("／4 列")   # 匯率表有 4 列
    assert left.locator("select.sheet-select").input_value() == "發票明細", "換右邊不影響左邊"
    left.locator("input.jump").fill("10")
    left.locator("input.jump").press("Enter")
    ui.settle()
    assert _target_row(left) == 10 and right.locator("tr.src-target").count() == 0
    page.click(".tab-body button:has-text('左右交換')")
    ui.settle()
    assert left.locator("select.sheet-select").input_value() == "匯率"
    assert right.locator("select.sheet-select").input_value() == "發票明細" and _target_row(right) == 10
    right.locator("button[aria-label='關掉右邊']").click()
    ui.settle()
    assert page.locator(".tab-body .source-pane").count() == 1
    assert page.locator(".tab-body .toolbar .chips .chip.active").first.inner_text().startswith("匯率")


def test_compare_match_sides(ui):
    """配對卡片的發票與報關單：打開完整工作表就是兩張表並排，換一筆配對兩邊一起跳。"""
    page = ui.run_sample()
    page.click(".tab:has-text('配對')")
    page.click(".chip:has-text('全部 9')")
    card = page.locator(".match-card:has-text('INV1002')").first
    card.locator(".side").nth(1).locator("button.row-source").click()      # 報關單那一列
    _open_full_sheet(page)
    left, right = _pane(page, "左"), _pane(page, "右")
    assert ui.state("state.tab") == "source"
    assert right.locator("select.sheet-select").input_value() == "報關單" and _target_row(right) == 3
    assert left.locator("select.sheet-select").input_value() == "發票明細" and _target_row(left) == 5
    ui.shot("compare-sheets")


def test_sheet_switch_jump_and_paging(ui):
    page = ui.run_sample()
    page.click(".tab:has-text('原始資料')")
    page.wait_for_selector(".source-grid")
    chips = page.locator(".tab-body .toolbar .chips").first.locator(".chip")
    assert chips.count() == 3 and "發票" in chips.first.inner_text()
    second = chips.nth(1).inner_text()
    chips.nth(1).click()
    expect(page.locator(".tab-body .toolbar .chips .chip.active")).to_have_text(second)   # 等重畫完，不讀到舊的表
    assert page.is_disabled("button[aria-label='上一段']") and page.is_disabled("button[aria-label='下一段']")
    chips.first.click()
    expect(page.locator(".tab-body .toolbar .chips .chip.active")).to_contain_text("發票")
    page.fill("input.jump", "10")
    page.press("input.jump", "Enter")
    expect(page.locator(".tab-body tr.src-target th.rowno")).to_have_text("10")


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


def test_source_pop_out_keeps_switching(ui):
    """原始資料 pop out 後一樣能切換工作表、左右並排；小卡的「完整工作表」交給那個視窗。"""
    page = ui.run_sample()
    page.click(".tab:has-text('原始資料')")
    page.wait_for_selector(".source-grid")
    page.click(".tab-body [role=switch]:has-text('左右並排')")
    page.wait_for_selector(".tab-body .source-pane[data-side='右'] .source-grid")
    with ui.context.expect_page() as info:
        page.click(".tab-tools button:has-text('Pop out')")
    w = ui.watch(info.value, "pop")
    w.wait_for_selector(".tab-body .source-pane[data-side='右'] .source-grid")   # 帶著並排過去
    _pane(w, "右").locator("select.sheet-select").select_option("匯率")
    _pane(w, "右").locator(".source-grid").wait_for()
    w.wait_for_timeout(300)
    assert _pane(w, "右").locator("select.sheet-select").input_value() == "匯率", "pop out 後可以換工作表"
    w.click(".tab-body [role=switch]:has-text('左右並排')")
    w.wait_for_selector(".tab-body .toolbar .chips")
    w.locator(".tab-body .toolbar .chips .chip").nth(1).click()
    w.wait_for_timeout(300)
    assert w.locator(".tab-body .toolbar .chips .chip.active").inner_text().startswith("報關單")
    # 主視窗的完整工作表交給 pop out 視窗，主視窗留在正在檢查的列
    page.click(".tab:has-text('結果')")
    ui.row("INV-1003").click()
    ui.field("金額").hover()
    ui.field("金額").locator("button.cell-link").click()
    page.locator("#peek button:has-text('完整工作表')").click()
    w.wait_for_selector(".source-pane[data-side='左'] td.src-cell")
    assert _pane(w, "左").locator("td.src-cell").inner_text() == "2,000"
    _assert_snapped(w, "左")
    assert ui.state("state.tab") == "rows" and page.is_visible("#drawer")
    assert len(ui.context.pages) == 2
    ui.shot("source-popout", page=w)
    # Pop in：帶回並排與看到的列
    w.click("#popInButton")
    page.wait_for_timeout(800)
    assert ui.state("state.tab") == "source" and page.locator(".tab-body .source-pane").count() == 2


def test_horizontal_scroll_snaps_to_column(ui):
    """要看的格子在右邊時，左右捲動要對齊到欄的開頭，不能把左邊的欄位切一半。"""
    ui.context.pages[0].set_viewport_size({"width": 1180, "height": 800})
    page = ui.run_sample()
    ui.row("INV-1003").click()
    ui.field("金額").hover()
    ui.field("金額").locator("button.cell-link").click()
    _open_full_sheet(page)
    page.wait_for_timeout(300)
    _assert_snapped(page)
    ui.shot("source-snap")


def test_match_status_on_source_sheets(ui):
    """原始表標出每一列的配對狀態：已配對淡化並寫配到哪一列，找不到、沒用到要處理的標橘色；按「→ 4」另一邊跳過去。"""
    page = ui.run_sample()
    page.click(".tab:has-text('原始資料')")
    page.click(".tab-body [role=switch]:has-text('左右並排')")
    page.wait_for_selector(".tab-body .source-pane[data-side='右'] .source-grid td.mark")
    left, right = _pane(page, "左"), _pane(page, "右")
    match = ui.state("state.result.matches[0]")
    row_of = lambda rid: int(rid.split(":")[-1])

    def mark(pane, row):
        tr = pane.locator(f"tbody tr[data-row='{row}']")
        return tr.get_attribute("class") or "", tr.locator("td.mark").inner_text().strip()

    for item in match["rows"]:
        cls, text = mark(left, row_of(item["left"]))
        if item["rights"]:
            assert text == "→ " + "、".join(str(row_of(r)) for r in item["rights"][:3]), (item, text)
            assert ("m-open" if item["status"] == "review" else "m-done") in cls
        elif item["status"] == "unmatched":
            assert text == "找不到" and "m-open" in cls
        elif item["status"] == "ambiguous":
            assert "候選" in text and "m-open" in cls
    assert match["unused_right"], "範例裡報關單有沒用到的列"
    candidates = {row_of(c["rid"]) for x in match["rows"] for c in x["candidates"] if x["status"] == "ambiguous"}
    for rid in match["unused_right"]:
        cls, text = mark(right, row_of(rid))
        assert text == ("候選" if row_of(rid) in candidates else "沒用到") and "m-open" in cls, (rid, text)
    assert any(row_of(r) not in candidates for r in match["unused_right"]), "範例要有真的沒用到的列"
    excluded = ui.state("state.result.excluded[0].row")
    cls, text = mark(left, excluded)
    assert text == "已排除" and "m-skip" in cls
    # 要處理的列數寫在上方
    open_left = left.locator("tbody tr.m-open").count()
    assert f"{open_left} 列要處理" in left.locator(".match-legend").inner_text()
    # 已配對的列文字淡化，要處理的列明顯
    done = left.locator("tbody tr.m-done td:not(.mark)").first.evaluate("e => getComputedStyle(e).color")
    plain = left.locator("tbody tr.src-header td:not(.mark)").first.evaluate("e => getComputedStyle(e).color")
    assert done != plain
    ui.shot("source-match-marks")
    # 按「→ 4」：右邊跳到配到的那一列
    paired = next(x for x in match["rows"] if x["rights"] and x["status"] != "review")
    left.locator(f"tbody tr[data-row='{row_of(paired['left'])}'] .mark-link").click()
    expect(right.locator("tr.src-target th.rowno")).to_have_text(str(row_of(paired["rights"][0])))
    # 右邊按「← 6」：左邊跳回來
    right.locator(f"tbody tr[data-row='{row_of(paired['rights'][0])}'] .mark-link").click()
    expect(left.locator("tr.src-target th.rowno")).to_have_text(str(row_of(paired["left"])))


def test_single_sheet_mark_opens_split(ui):
    """只有一張表時按「→ 4」：打開並排，右邊是配到的那一列。"""
    page = ui.run_sample()
    page.click(".tab:has-text('原始資料')")
    page.wait_for_selector(".tab-body .source-grid td.mark")
    assert page.locator(".tab-body .source-pane").count() == 1
    page.locator(".tab-body .source-grid .mark-link").first.click()
    right = _pane(page, "右")
    right.locator("tr.src-target").wait_for()
    assert right.locator("select.sheet-select").input_value() == "報關單"
