"""導覽 v2：指令條跟著捲動（sticky dock）、目標在畫面外的浮標、關卡 A 要做完才下載、舊進度續玩。"""
from __future__ import annotations

from playwright.sync_api import expect

from guide_checks import assert_pointer_text_and_direction, pointer_report


def _start_review(ui, height=600):
    page = ui.open()
    page.set_viewport_size({"width": 1440, "height": height})
    page.click('[data-guide="welcome-review"]')
    expect(page.locator("#runButton")).to_be_enabled()
    page.click("#runButton")
    expect(page.locator("#result table.grid")).to_be_visible()
    return page


def _go_step(page, n):
    page.locator("#guideBar .guide-dot-btn").nth(n - 1).click()
    page.wait_for_timeout(500)


def _scroll_work_to_bottom(page):
    box = page.locator(".work").bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    for _ in range(12):
        page.mouse.wheel(0, 800)
    page.wait_for_timeout(300)


def _dock_state(page):
    return page.evaluate("""() => {
      const work = document.querySelector('.work').getBoundingClientRect();
      const dock = document.querySelector('.guide-dock');
      const d = dock.getBoundingClientRect();
      const action = document.querySelector('#missionStrip .mission-action').getBoundingClientRect();
      // 沿著 dock 的中線取幾個點，最上層元素都要屬於 dock（表格表頭不能蓋過它）
      const covered = [0.1, 0.3, 0.5, 0.7, 0.9].every((f) => {
        const el = document.elementFromPoint(d.left + d.width * f, d.top + d.height / 2);
        return el && el.closest('.guide-dock');
      });
      return { workTop: work.top, dockTop: d.top, dockBottom: d.bottom, dockHeight: d.height,
               actionTop: action.top, actionBottom: action.bottom, vh: window.innerHeight,
               scrollTop: document.querySelector('.work').scrollTop, covered,
               var: getComputedStyle(document.querySelector('.work')).getPropertyValue('--guide-dock-h').trim(),
               pad: getComputedStyle(document.querySelector('.work')).scrollPaddingTop };
    }""")


def test_dock_stays_on_top_when_work_scrolls(ui):
    page = _start_review(ui)
    for step in (3, 6, 7, 8):
        _go_step(page, step)
        _scroll_work_to_bottom(page)
        st = _dock_state(page)
        if step in (6, 7):
            assert st["scrollTop"] > 0, f"第 {step} 步沒有捲動，測不到 sticky"
        assert abs(st["dockTop"] - st["workTop"]) <= 1, f"第 {step} 步 dock 沒有貼齊 .work 頂端：{st}"
        assert st["actionTop"] >= st["dockTop"] and st["actionBottom"] <= st["dockBottom"] + 1, f"行動句不在 dock 內：{st}"
        assert st["covered"], f"dock 被表格或內容蓋住：{st}"
        assert page.locator("#missionStrip .mission-action").inner_text().strip()
        # dock 高度寫進 CSS 變數，scroll-padding-top 要比 dock 高
        assert st["var"].endswith("px") and abs(float(st["var"][:-2]) - st["dockHeight"]) <= 2, st
        assert float(st["pad"][:-2]) >= st["dockHeight"], st
    ui.shot("onboarding-08-dock-scrolled")


def test_dock_hidden_without_journey_and_not_in_drawer(ui):
    page = ui.open()
    expect(page.locator(".guide-dock")).to_be_hidden()
    page.click('[data-guide="welcome-review"]')
    expect(page.locator(".guide-dock")).to_be_visible()
    # 細節在右欄，不在 dock 裡
    assert page.locator(".guide-dock #drawer").count() == 0
    page.click('#guideBar button:has-text("關閉導覽")')
    expect(page.locator(".guide-dock")).to_be_hidden()


def test_target_under_dock_or_below_fold_shows_scroll_pointer(ui):
    page = _start_review(ui, height=520)
    _go_step(page, 7)
    target_js = "window.Spotlights.engine.lastTargetEl"

    # 目標在畫面下方：浮標貼在下緣，寫「往下捲」，三角形朝下
    page.evaluate("document.querySelector('.work').scrollTop = 0")
    page.wait_for_timeout(400)
    rep = assert_pointer_text_and_direction(page)
    assert rep and rep["text"].strip() == "往下捲" and rep["dir"] == "down", rep
    assert rep["pointer"]["bottom"] >= rep["viewport"][1] - 60

    # 目標被捲進 dock 底下：不算可見，浮標貼在 dock 下緣，寫「往上捲」，三角形朝上
    page.evaluate(f"""() => {{
      const work = document.querySelector('.work');
      const dock = document.querySelector('.guide-dock').getBoundingClientRect();
      const t = {target_js}.getBoundingClientRect();
      work.scrollTop += t.bottom - dock.bottom + 24;
    }}""")
    page.wait_for_timeout(400)
    cover = page.evaluate(f"""() => {{
      const dock = document.querySelector('.guide-dock').getBoundingClientRect();
      return {{ targetBottom: {target_js}.getBoundingClientRect().bottom, dockBottom: dock.bottom }};
    }}""")
    assert cover["targetBottom"] <= cover["dockBottom"] - 20, f"目標沒有被捲到 dock 底下：{cover}"
    rep = assert_pointer_text_and_direction(page)
    assert rep and rep["text"].strip() == "往上捲" and rep["dir"] == "up", rep
    assert rep["pointer"]["top"] >= cover["dockBottom"] - 1
    # 浮標不吃點擊：點浮標所在位置，點到的是底下的內容
    assert page.evaluate("getComputedStyle(document.getElementById('guidePointer')).pointerEvents") == "none"

    # 往回捲到目標看得到：浮標回到目標旁，三角形指向目標
    page.evaluate(f"""() => {{
      const work = document.querySelector('.work');
      const dock = document.querySelector('.guide-dock').getBoundingClientRect();
      const t = {target_js}.getBoundingClientRect();
      work.scrollTop += t.top - dock.bottom - 80;
    }}""")
    page.wait_for_timeout(400)
    rep = assert_pointer_text_and_direction(page)
    assert rep and rep["text"].strip() not in ("往上捲", "往下捲"), rep
    assert pointer_report(page)["side"] != "offscreen"
    ui.shot("onboarding-09-pointer-visible-after-scroll")


def test_download_before_everything_checked_warns_and_stays(ui):
    page = _start_review(ui)
    # 直接跳到第 9 步按下載：出現 ⚠，步驟停在原地
    _go_step(page, 9)
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("確認無誤，下一筆")
    with page.expect_download() as dl:
        page.click("#exportButton")
    assert dl.value.suggested_filename.startswith("示範_")
    page.wait_for_timeout(400)
    expect(page.locator("#missionStrip .mission-tip")).to_contain_text("⚠")
    expect(page.locator("#missionStrip .mission-tip")).to_contain_text("看完再下載")
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("確認無誤，下一筆")
    assert page.locator("#missionStrip .mission-badge").inner_text().startswith("9")
    assert ui.state("JSON.parse(localStorage.getItem('dp:onboarding.v1')).journeys.review.done") is False
    # 第 10 步也一樣：提醒還有幾列沒看，關卡沒有完成
    _go_step(page, 10)
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("下載 Excel")
    with page.expect_download():
        page.click("#exportButton")
    page.wait_for_timeout(400)
    expect(page.locator("#missionStrip .mission-tip")).to_contain_text("還有")
    expect(page.locator("#missionStrip .mission-tip")).to_contain_text("⚠")
    assert ui.state("JSON.parse(localStorage.getItem('dp:onboarding.v1')).journeys.review.done") is False
    assert "核對流程走完了" not in page.locator("#missionStrip").inner_text()


def test_old_progress_at_review_8_resumes_at_first_undone_step(ui):
    """舊版第 8 步是下載；續玩時不能直接當作第 8 步（把配對做完）的前面都做完了。"""
    page = ui.open()
    page.evaluate("""() => {
      localStorage.setItem('dp:onboarding.v1', JSON.stringify({ journeys: { review:
        { step: 'review-8', done: false, skipped: [], flags: { sawStage: true } } } }));
    }""")
    page.reload()
    page.click("#helpBtn")
    page.click('#helpPopover button:has-text("核對一份資料")')
    expect(page.locator("#result table.grid")).to_be_visible()
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("怎麼判斷的")
    assert ui.state("JSON.parse(localStorage.getItem('dp:onboarding.v1')).journeys.review.step") == "review-3"


def test_step9_pointer_goes_to_the_blocking_alert(ui):
    """選到的列有一定要處理的警示時，浮標不再指「確認無誤」，改指那個警示的處理動作。"""
    page = _start_review(ui, height=900)
    _go_step(page, 9)
    ui.row("INV-1006").click()
    page.wait_for_timeout(500)
    expect(page.locator('#drawer [data-guide="foot-todo"]')).to_be_visible()
    rep = assert_pointer_text_and_direction(page)
    assert rep and rep["text"].strip() == "改這一格", rep
    expect(page.locator("#missionStrip .mission-tip")).to_contain_text("金額讀不懂，改成數字後按 Enter")
    # 改好數字後，同一列還有「找不到配對」：浮標換指「前往配對」
    amt = page.locator('#drawer [data-guide="field-金額"]')
    amt.fill("300")
    amt.press("Enter")
    expect(page.locator('#drawer [data-guide="issue-goto-match"]')).to_be_visible()
    page.wait_for_timeout(400)
    rep = assert_pointer_text_and_direction(page)
    assert rep and rep["text"].strip() == "前往配對", rep
    # 沒有一定要處理的警示時（INV-1004 只有金額不同要判斷），浮標指「確認無誤，下一筆」
    ui.row("990").click()   # 發票 1004，報關金額 990
    expect(page.locator('#drawer [data-guide="confirm-next"]')).to_be_visible()
    page.wait_for_timeout(400)
    rep = assert_pointer_text_and_direction(page)
    assert rep and rep["text"].strip() == "確認無誤，下一筆", rep
