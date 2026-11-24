"""進階功能的小關卡（mission）與練習中心：用真的瀏覽器一步一步點，每一步都檢查強調、行動句與浮標。"""
from __future__ import annotations

import json
import re

from playwright.sync_api import expect

import dataprocessor.server as server
from guide_checks import assert_pointer_text_and_direction, assert_step_guidance

ORDER = ["mission-trace", "mission-source", "mission-bulk", "mission-reset", "mission-popout",
         "lab-gate", "lab-mapping", "lab-match", "lab-extract", "lab-validate", "mission-transform"]


def _seed_prefs(page, **fields):
    """直接寫進 localStorage 的導覽進度（只用來準備起始狀態），之後重新整理讓頁面讀到。"""
    page.evaluate("""(fields) => {
      const base = { dismissed: false, journeys: { review: { step: null, done: false, skipped: [], flags: {} },
        recipe: { step: null, done: false, skipped: [], flags: {} } }, cardsSeen: [], practiceDone: [],
        tipsSeen: { jk: 3 }, whatsnewSeen: '9.9.9' };
      localStorage.setItem('dp:onboarding.v1', JSON.stringify({ ...base, ...fields }));
    }""", fields)
    page.reload()
    page.wait_for_selector("#recipeList .recipe-item")


def _prefs(page):
    return page.evaluate("JSON.parse(localStorage.getItem('dp:onboarding.v1'))")


def _start_practice(page, title):
    page.click("#helpBtn")
    page.click(f'#helpPopover button:has-text("{title}")')
    expect(page.locator("#helpCard")).to_be_visible()
    page.click('#helpCard button:has-text("開始練習")')


def _action(page):
    return page.locator("#missionStrip .mission-action")


def _no_skip_button(page):
    assert page.locator('#missionStrip button:has-text("下一步")').count() == 0, "最後一步不能跳過"


def _complete(page, next_title):
    expect(_action(page)).to_have_text("練習完成")
    expect(page.locator('#missionStrip [data-guide="practice-next"]')).to_have_text(f"下一個：{next_title}")
    assert page.locator("#missionStrip button.primary").count() == 1


def _state(page, expression):
    return page.evaluate(expression)


def test_mission_trace_with_work_restore(ui):
    page = ui.run_sample()
    ui.row("INV-1006").click()
    before = _state(page, "({ run: state.result.run_id, selected: state.selected, tab: state.tab, filter: state.filter })")

    # 說明卡：主要按鈕是「開始練習」，沒有指過去就結束的動作，位置寫在內文
    page.click("#helpBtn")
    page.click('#helpPopover button:has-text("看這一格是怎麼來的")')
    card = page.locator("#helpCard")
    expect(card).to_contain_text("怎麼來的")
    text = card.inner_text()
    assert "試試看" not in text and "帶我去" not in text
    assert card.locator(".float-card-where").inner_text().strip()
    assert card.locator("button.primary").count() == 1
    card.locator('button:has-text("開始練習")').click()

    expect(page.locator("#guideBar")).to_contain_text("進階：看這一格是怎麼來的")
    expect(_action(page)).to_contain_text("INV1002")
    assert_step_guidance(page)
    ui.shot("practice-01-trace-step1")
    ui.row("INV1002").click()

    expect(_action(page)).to_contain_text("怎麼來的")
    assert_step_guidance(page)
    expect(page.locator('#drawer [data-guide="why-金額"]')).to_have_css("opacity", "1")   # 平常要滑過才看得到的按鈕，練習指它時先顯示出來
    page.locator("#drawer .field:has([data-guide='why-金額'])").hover()
    page.click('#drawer [data-guide="why-金額"]')

    expect(_action(page)).to_contain_text("USD 3,450.00")
    assert_step_guidance(page)
    ui.shot("practice-02-trace-step3")
    # 點原始儲存格位置也算看過（不用等 600ms）
    page.click("#drawer .field:has([data-guide='why-金額']) .cell-link")
    expect(page.locator("#peek")).to_be_visible()
    assert _state(page, "window.Spotlights.engine.flags.sawCell") is True
    page.keyboard.press("Escape")
    expect(page.locator("#peek")).to_have_count(0)

    expect(_action(page)).to_contain_text("這一列的處理過程")
    assert_step_guidance(page)
    _no_skip_button(page)
    page.click('#drawer [data-guide="row-trace"]')
    expect(page.locator("#drawer .row-trace .trace li").first).to_be_visible()

    _complete(page, "兩張表並排，找配對的答案")
    ui.shot("practice-03-trace-done")
    assert "mission-trace" in _prefs(page)["practiceDone"]
    # 有保存的工作時才有「回到我的工作」，接回原本的結果、分頁、選到的列
    page.click('#missionStrip button:has-text("回到我的工作")')
    page.wait_for_function("(id) => state.result?.run_id === id", arg=before["run"], timeout=5000)
    assert _state(page, "({ run: state.result.run_id, selected: state.selected, tab: state.tab, filter: state.filter })") == before
    expect(page.locator("#guideBar")).to_be_hidden()


def test_mission_trace_dwell_counts_without_clicking_cell(ui):
    page = ui.open()
    _start_practice(page, "看這一格是怎麼來的")
    expect(_action(page)).to_contain_text("INV1002")
    ui.row("INV1002").click()
    page.locator("#drawer .field:has([data-guide='why-金額'])").hover()
    page.click('#drawer [data-guide="why-金額"]')
    # 來由顯示一陣子（600ms）就算看過，沒點原始儲存格也會往下
    expect(_action(page)).to_contain_text("這一列的處理過程", timeout=4000)
    assert _state(page, "window.Spotlights.engine.flags.sawCell") in (None, False)
    # 沒有保存的工作時，完成畫面沒有「回到我的工作」
    page.click('#drawer [data-guide="row-trace"]')
    expect(_action(page)).to_have_text("練習完成")
    assert page.locator('#missionStrip button:has-text("回到我的工作")').count() == 0


def test_mission_source_and_next_goes_to_first_unpracticed(ui):
    page = ui.open()
    _seed_prefs(page, practiceDone=["mission-trace", "mission-bulk"])
    _start_practice(page, "兩張表並排，找配對的答案")
    expect(page.locator("#guideBar")).to_contain_text("進階：兩張表並排，找配對的答案")
    expect(_action(page)).to_contain_text("INV-1008")
    assert_step_guidance(page)
    page.click('.tab[data-tab="match"]')

    card = page.locator('.match-card:has-text("INV-1008")')
    expect(_action(page)).to_contain_text("表格圖示")
    assert_step_guidance(page)
    card.locator('[data-guide="match-sheet"]').click()
    expect(page.locator("#peek")).to_be_visible()

    expect(_action(page)).to_contain_text("完整工作表")
    page.wait_for_timeout(300)
    assert_step_guidance(page)           # 小卡開著時，浮標畫在小卡裡
    ui.shot("practice-04-source-peek")
    page.click('#peek [data-guide="peek-full"]')

    expect(_action(page)).to_contain_text("左右並排")
    assert_step_guidance(page)
    page.click('[data-guide="source-split"]')
    expect(page.locator(".source-split.two")).to_be_visible()

    expect(_action(page)).to_contain_text("沒用到")
    assert_step_guidance(page)
    ui.shot("practice-05-source-unused")
    page.locator('.source-pane tr[data-unused="1"] td.mark').first.click()

    expect(_action(page)).to_contain_text("沒有配對")
    assert_step_guidance(page)
    _no_skip_button(page)
    assert _state(page, "state.tab") == "match"
    page.locator('.match-card:has-text("INV-1008") [data-guide="match-none"]').click()

    _complete(page, "清掉重來，按錯可以復原")     # 清單順序：trace、source、bulk 都練過，下一個是 reset
    page.click('#missionStrip [data-guide="practice-next"]')
    expect(page.locator("#guideBar")).to_contain_text("進階：清掉重來，按錯可以復原")


def test_mission_bulk(ui):
    page = ui.open()
    _start_practice(page, "一次確認很多筆")
    expect(_action(page)).to_contain_text("所有警示")
    assert_step_guidance(page)
    page.click('.tab[data-tab="issues"]')

    expect(_action(page)).to_contain_text("Validate")
    assert_step_guidance(page)
    page.click('[data-guide="stage-validate"]')
    expect(_action(page)).to_contain_text("查看")
    assert_step_guidance(page)
    page.click('#stageDetail [data-guide="stage-link"][data-code="check0"]')

    expect(_action(page)).to_contain_text("全選")
    assert_step_guidance(page)
    page.click('[data-guide="issues-all"]')
    expect(_action(page)).to_contain_text("確認無誤")
    assert_step_guidance(page)
    page.click('[data-guide="issues-confirm"]')

    expect(_action(page)).to_contain_text("已處理")
    assert_step_guidance(page)
    _no_skip_button(page)
    assert _state(page, "state.result.issues.filter(i => i.code === 'check0').every(i => i.dismissed)")
    page.locator("#tabBody .chip", has_text="已處理").click()

    expect(_action(page)).to_have_text("練習完成")
    assert page.locator("#tabBody .issue-row").count() >= 1
    _complete(page, "看這一格是怎麼來的")


def test_mission_reset_uses_scratch_decisions_and_undo(ui):
    page = ui.open()
    _start_practice(page, "清掉重來，按錯可以復原")
    expect(_action(page)).to_contain_text("重新檢查")
    # 前置的 2 個人工決定在範例的暫存空間，不寫進 workspace/reviews
    assert _state(page, "state.result.decisions") == 2
    assert not any(server.paths.REVIEWS.glob("**/*.json")), "範例的人工決定不能寫進 reviews"
    assert any((server.paths.SCRATCH / "demo" / "reviews").glob("**/*.json"))
    assert_step_guidance(page)
    page.click("#resetButton")
    expect(page.locator("#resetButton")).to_contain_text("清掉 2 項人工決定")

    expect(_action(page)).to_contain_text("再按一次，清掉這 2 項")
    assert_step_guidance(page)
    page.click("#resetButton")
    page.wait_for_function("() => state.result.decisions === 0")

    expect(_action(page)).to_contain_text("復原")
    page.wait_for_timeout(300)
    assert_step_guidance(page)
    _no_skip_button(page)
    ui.shot("practice-06-reset-undo")
    # 提示消失後，行動句旁出現「再顯示復原」
    page.evaluate("document.getElementById('toast').hidden = true; window.Spotlights.scheduleGuide()")
    page.locator("#missionStrip .mission-assist").click()
    expect(page.locator("#toast [data-guide='toast-action']")).to_be_visible()
    page.wait_for_timeout(300)
    page.click("#toast [data-guide='toast-action']")
    page.wait_for_function("() => state.result.decisions === 2")

    expect(_action(page)).to_have_text("練習完成")
    assert not any(server.paths.REVIEWS.glob("**/*.json"))


def test_mission_popout_with_real_second_window(ui):
    page = ui.open()
    _start_practice(page, "表格太寬，搬到另一個螢幕")
    expect(_action(page)).to_contain_text("Pop out")
    assert_step_guidance(page)
    with ui.context.expect_page() as info:
        page.click('[data-guide="popout-btn"]')
    win = ui.watch(info.value, "pop")
    win.set_viewport_size({"width": 1400, "height": 900})
    win.wait_for_selector("#result:not([hidden]) table.grid")
    win.wait_for_timeout(500)

    expect(_action(page)).to_contain_text("新視窗")
    assert page.locator(".tab.away:has-text('結果') .away-mark").count() == 1
    assert_step_guidance(page)
    ui.row("INV-1003", page=win).click()
    # 主視窗收到同步，進到第 3 步
    page.wait_for_function("() => state.selected === 'invoice:6'")
    expect(_action(page)).to_contain_text("Pop in")
    assert_step_guidance(page)
    _no_skip_button(page)
    win.click("#popInButton")
    expect(_action(page)).to_have_text("練習完成", timeout=5000)
    assert _state(page, "state.tab") == "rows" and _state(page, "state.selected") == "invoice:6"
    assert page.locator(".tab.away").count() == 0
    page.wait_for_timeout(500)
    assert win.is_closed()


def test_mission_popout_blocked_can_be_skipped(ui):
    ui.page.add_init_script("window.open = () => null;")
    page = ui.open()
    _start_practice(page, "表格太寬，搬到另一個螢幕")
    page.click('[data-guide="popout-btn"]')
    expect(page.locator("#missionStrip .mission-tip")).to_contain_text("擋下")
    expect(_action(page)).to_contain_text("Pop out")
    page.click('#missionStrip .mission-assist:has-text("跳過這條練習")')
    expect(page.locator("#guideBar")).to_be_hidden()
    assert "mission-popout" not in _prefs(page)["practiceDone"]


def test_mission_transform_draws_guide_inside_dialog(ui):
    page = ui.open()
    _start_practice(page, "用公式算出新欄位")
    expect(_action(page)).to_contain_text("任何一列")
    assert_step_guidance(page)
    ui.row("INV1002").click()

    expect(_action(page)).to_contain_text("台幣金額")
    assert_step_guidance(page)
    page.locator("#drawer .field:has([data-guide='why-台幣金額'])").hover()
    page.click('#drawer [data-guide="why-台幣金額"]')

    expect(_action(page)).to_contain_text("查看")
    assert_step_guidance(page)
    _no_skip_button(page)
    page.click('#recipeList [data-guide="recipe-view"]')
    expect(page.locator("#dialog")).to_be_visible()
    # 對話框（top layer）開著：指令條與浮標都畫進對話框裡（5.6）
    dg = page.locator("#dialog .dialog-guide")
    expect(dg).to_be_visible()
    expect(dg).to_contain_text("SQL 原文")
    page.wait_for_timeout(300)
    assert page.locator("#dialog #guidePointer").count() == 1
    assert_pointer_text_and_direction(page)
    ui.shot("practice-07-transform-dialog")
    page.locator('#dialog .flow-body:has(.flow-text:text-is("計算：換算台幣")) > details.explain-code > summary').click()
    expect(_action(page)).to_have_text("練習完成")
    expect(page.locator("#dialog .dialog-guide")).to_have_count(0)
    page.keyboard.press("Escape")

    _complete(page, "看這一格是怎麼來的")
    page.locator('#missionStrip button:has-text("複製給 AI 的提問")').click()
    expect(page.locator("#toast")).to_contain_text("已複製")


def _finish_review_journey(page, ui):
    """用真的點擊走完關卡 A（只為了讓新手導覽的完成畫面出現）；每一步等行動句換了再做下一步。"""
    page.click('[data-guide="welcome-review"]')
    expect(page.locator("#runButton")).to_be_enabled()
    page.click("#runButton")
    page.click('[data-guide="stage-match"]')
    ui.row("INV-1003").click()
    page.click('[data-guide="issue-trace"]')
    page.click('[data-guide="confirm-next"]')
    expect(_action(page)).to_contain_text("300")
    amt = page.locator('#drawer [data-guide="field-金額"]')
    amt.fill("300")
    amt.press("Enter")
    expect(_action(page)).to_contain_text("新增對應值")
    page.locator('#drawer [data-guide="map-select"]').select_option("__new")
    new_in = page.locator('#drawer [data-guide="map-new"]')
    new_in.fill("LAND")
    new_in.press("Enter")
    page.click('#drawer [data-guide="map-save"]')
    expect(_action(page)).to_contain_text("AA15A0005")
    page.locator('.match-card:has-text("INV-1009") .candidate:has-text("AA15A0005") button:has-text("選這筆")').click()
    expect(_action(page)).to_contain_text("原始表")
    page.locator('.match-card:has-text("INV-1008") [data-guide="match-sheet"]').click()
    page.keyboard.press("Escape")
    expect(_action(page)).to_contain_text("沒有配對")
    page.locator('.match-card:has-text("INV-1008") [data-guide="match-none"]').click()
    for _ in range(6):
        expect(_action(page)).to_contain_text(re.compile("INV-|確認無誤"))
        action = _action(page).inner_text()
        if "確認正確" not in action and "沒有配對" not in action:
            break
        invoice = re.search(r"INV-\d+", action).group(0)
        key = "match-confirm" if "確認正確" in action else "match-none"
        page.locator(f'.match-card:has-text("{invoice}") [data-guide="{key}"]').click()
        expect(_action(page)).not_to_have_text(action)
    for _ in range(6):
        if "下載" in _action(page).inner_text():
            break
        page.click('[data-guide="confirm-next"]')
        page.wait_for_timeout(300)
    with page.expect_download():
        page.click("#exportButton")
    expect(_action(page)).to_contain_text("核對流程走完了")


def test_practice_hub_entries_and_first_open_pointer(ui):
    page = ui.open()
    # 入口 2：說明選單上方的「練習中心」，附已練幾項
    page.click("#helpBtn")
    row = page.locator('#helpPopover [data-guide="help-practice"]')
    expect(row).to_contain_text("已練 0 / 11")
    box_menu = page.locator("#helpPopover .help-row").evaluate_all("els => els.map(e => e.textContent.trim())")
    assert box_menu.index(next(t for t in box_menu if t.startswith("練習中心"))) < box_menu.index("看這一格是怎麼來的")
    row.click()
    hub = page.locator("#practiceHub")
    expect(hub).to_be_visible()
    expect(hub).to_contain_text("進階功能練習")
    expect(hub).to_contain_text("已練 0 / 11")
    assert hub.locator(".practice-card").count() == 11
    # 一次都沒練過：浮標在對話框裡指向推薦的第一項，不蓋到別的按鈕（5.6）
    page.wait_for_timeout(400)
    assert page.locator("#practiceHub #guidePointer").count() == 1
    rep = assert_step_guidance_hub(page)
    assert rep["text"] == "從這裡開始"
    ui.shot("practice-08-hub-first-open")
    page.keyboard.press("Escape")
    expect(hub).not_to_be_visible()
    assert page.locator("#guidePointer").evaluate("e => e.parentElement === document.body || e.hidden")


def assert_step_guidance_hub(page):
    from guide_checks import pointer_overlap, pointer_report
    rep = assert_pointer_text_and_direction(page)
    assert rep is not None, "練習中心第一次打開要有浮標"
    assert pointer_overlap(page) is None, pointer_overlap(page)
    assert pointer_report(page)["text"] == "從這裡開始"
    return pointer_report(page)


def test_practice_hub_state_primary_and_narrow_layout(ui):
    page = ui.open()
    _seed_prefs(page, practiceDone=["mission-trace", "lab-gate"])
    page.click("#helpBtn")
    page.click('#helpPopover [data-guide="help-practice"]')
    hub = page.locator("#practiceHub")
    expect(hub).to_contain_text("已練 2 / 11")
    done_card = hub.locator('.practice-card[data-practice="mission-trace"]')
    expect(done_card.locator(".practice-check")).to_have_text("✓")
    expect(done_card.locator("button")).to_have_text("再練一次")
    # 推薦項目（清單順序第一個沒練過的）是唯一的 primary，用 accent 細框
    assert hub.locator("button.primary").count() == 1
    nxt = hub.locator('.practice-card[data-practice="mission-source"]')
    expect(nxt.locator("button.primary")).to_have_text("開始")
    assert "next" in nxt.get_attribute("class")
    other = hub.locator('.practice-card[data-practice="lab-match"] button')
    expect(other).to_have_text("開始")
    assert "primary" not in other.get_attribute("class")
    # 先沒有練過的卡片時才有浮標；已經練過就沒有
    assert page.locator("#practiceHub #guidePointer").count() == 0 or page.locator("#guidePointer").is_hidden()
    ui.shot("practice-09-hub")
    # 兩欄；1000px 寬時一欄，不超出視窗，內容可捲動
    cols = hub.locator(".practice-grid").first.evaluate("e => getComputedStyle(e).gridTemplateColumns.split(' ').length")
    assert cols == 2
    page.set_viewport_size({"width": 1000, "height": 700})
    page.wait_for_timeout(300)
    cols = hub.locator(".practice-grid").first.evaluate("e => getComputedStyle(e).gridTemplateColumns.split(' ').length")
    assert cols == 1
    box = hub.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= 1000 and box["y"] >= 0 and box["y"] + box["height"] <= 700
    assert hub.evaluate("e => e.scrollHeight > e.clientHeight")
    ui.shot("practice-10-hub-narrow")


def test_old_labs_done_key_migrates_to_practice_done(ui):
    page = ui.open()
    page.evaluate("""() => localStorage.setItem('dp:onboarding.v1', JSON.stringify({
      dismissed: false, journeys: { review: { step: null, done: false, skipped: [], flags: {} }, recipe: { step: null, done: false, skipped: [], flags: {} } },
      cardsSeen: [], labsDone: ['lab-gate', 'lab-match'], tipsSeen: { jk: 3 }, whatsnewSeen: '9.9.9' }))""")
    page.reload()
    page.wait_for_selector("#recipeList .recipe-item")
    page.click("#helpBtn")
    expect(page.locator('#helpPopover [data-guide="help-practice"]')).to_contain_text("已練 2 / 11")
    prefs = _prefs(page)
    assert prefs["practiceDone"] == ["lab-gate", "lab-match"] and "labsDone" not in prefs


def test_hub_start_saves_work_and_resumes_it(ui):
    page = ui.run_sample()
    ui.row("INV-1006").click()
    run = _state(page, "state.result.run_id")
    page.click("#helpBtn")
    page.click('#helpPopover [data-guide="help-practice"]')
    page.click('#practiceHub .practice-card[data-practice="mission-bulk"] button')
    expect(page.locator("#practiceHub")).not_to_be_visible()
    expect(page.locator("#guideBar")).to_contain_text("進階：一次確認很多筆")
    assert _state(page, "state.result.demo") is True
    page.click('#guideBar button:has-text("結束練習")')
    page.wait_for_function("(id) => state.result?.run_id === id", arg=run, timeout=5000)
    assert _state(page, "state.selected") == "invoice:9"
    # 從練習中心換到寫 recipe 的練習（lab）也能開
    page.click("#helpBtn")
    page.click('#helpPopover [data-guide="help-practice"]')
    page.click('#practiceHub .practice-card[data-practice="lab-gate"] button')
    expect(page.locator('[data-guide="lab-editor"]')).to_be_visible()
    expect(page.locator("#practiceHub")).not_to_be_visible()


def test_hub_from_journey_done_welcome_and_help(ui):
    page = ui.open()
    _finish_review_journey(page, ui)
    # 入口 1：關卡 A 完成畫面，主要按鈕是「練習進階功能」，其他降為 ghost
    strip = page.locator("#missionStrip")
    assert strip.locator("button.primary").count() == 1
    expect(strip.locator("button.primary")).to_have_text("練習進階功能")
    assert "primary" not in strip.locator('button:has-text("用自己的資料開始")').get_attribute("class")
    ui.shot("practice-11-journey-done")
    strip.locator("button.primary").click()
    expect(page.locator("#practiceHub")).to_be_visible()
    page.keyboard.press("Escape")
    # 離開後，歡迎畫面的主要入口換成練習中心，原本的導覽變成「重看新手導覽」
    page.click('#missionStrip button:has-text("用自己的資料開始")')
    primary = page.locator('[data-guide="welcome-practice"]')
    expect(primary).to_contain_text("練習進階功能")
    expect(primary).to_contain_text("已練 0 / 11")
    expect(page.locator('[data-guide="welcome-review"]')).to_have_text("重看新手導覽")
    ui.shot("practice-12-welcome-after-journey")
    primary.click()
    expect(page.locator("#practiceHub")).to_be_visible()


def test_tip_after_first_own_run_shows_once(ui):
    page = ui.open()
    _seed_prefs(page, journeys={"review": {"step": None, "done": True, "skipped": [], "flags": {}},
                                "recipe": {"step": None, "done": False, "skipped": [], "flags": {}}})
    page.click("text=使用範例")
    page.click("#runButton")
    expect(page.locator("#result table.grid")).to_be_visible()
    strip = page.locator("#missionStrip")
    expect(strip).to_be_visible()
    expect(strip).to_contain_text("看完這份資料後，可以到說明 ▾ 練習進階功能")
    ui.shot("practice-13-tip")
    # 執行下一次後不再出現
    page.click("#runButton")
    expect(strip).to_be_hidden()
    page.click("#runButton")
    page.wait_for_timeout(500)
    expect(strip).to_be_hidden()
    assert _prefs(page)["tipsSeen"]["practice"] == 1

    # 另一個瀏覽器狀態：點「開練習中心」
    _seed_prefs(page, journeys={"review": {"step": None, "done": True, "skipped": [], "flags": {}},
                                "recipe": {"step": None, "done": False, "skipped": [], "flags": {}}})
    page.click("text=使用範例")
    page.click("#runButton")
    expect(strip).to_contain_text("練習進階功能")
    page.click('[data-guide="tip-open-practice"]')
    expect(page.locator("#practiceHub")).to_be_visible()
    page.keyboard.press("Escape")
    expect(strip).to_be_hidden()

    # 練習中心開過就不再提示；新手導覽沒走完也不提示
    _seed_prefs(page, tipsSeen={"jk": 3, "hub": 1}, journeys={"review": {"step": None, "done": True, "skipped": [], "flags": {}},
                                                              "recipe": {"step": None, "done": False, "skipped": [], "flags": {}}})
    page.click("text=使用範例")
    page.click("#runButton")
    page.wait_for_timeout(500)
    expect(strip).to_be_hidden()
    _seed_prefs(page)
    page.click("text=使用範例")
    page.click("#runButton")
    page.wait_for_timeout(500)
    expect(strip).to_be_hidden()


def test_whatsnew_points_to_practice_center(ui):
    page = ui.open()
    _seed_prefs(page, whatsnewSeen="0.2.0")
    page.wait_for_selector("#whatsNewCard", timeout=4000)
    expect(page.locator("#whatsNewCard")).to_contain_text("進階功能練習中心")
    assert json.loads(page.evaluate("JSON.stringify(window.Spotlights.EXTRA_SPOTLIGHTS['practice-center'])"))["target"] == "#helpBtn"
