"""新手導覽（關卡 A、關卡 B）、說明選單、說明卡、窄螢幕、工作保存與 popout 隔離的介面測試。"""
from __future__ import annotations

import pytest


def _assert_single_emphasis(page):
    """同一時間 .guide-outline、#guidePointer、.guide-target 最多一種可見。"""
    counts = page.evaluate("""() => {
      const vis = (el) => {
        if (!el || el.hidden) return false;
        const cs = getComputedStyle(el);
        if (cs.display === 'none' || cs.visibility === 'hidden') return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
      };
      const ptr = document.getElementById('guidePointer');
      const outline = document.querySelector('.guide-outline');
      const frames = [...document.querySelectorAll('.guide-target')].filter(vis);
      return {
        pointer: vis(ptr) ? 1 : 0,
        outline: vis(outline) ? 1 : 0,
        frame: frames.length > 0 ? 1 : 0,
      };
    }""")
    total = counts["pointer"] + counts["outline"] + counts["frame"]
    assert total <= 1, f"同時出現多種強調：{counts}"
    return total


def _assert_pointer_not_overlapping_chrome(page):
    """浮標可見時，不可和 #guideBar、#missionStrip、header.bar 的矩形重疊。"""
    overlap = page.evaluate("""() => {
      const ptr = document.getElementById('guidePointer');
      if (!ptr || ptr.hidden) return null;
      if (ptr.closest('#dialog')) return null;
      const pr = ptr.getBoundingClientRect();
      if (!pr.width || !pr.height) return null;
      const checks = [
        ['header.bar', document.querySelector('header.bar')],
        ['#guideBar', document.getElementById('guideBar')],
        ['#missionStrip', document.getElementById('missionStrip')],
      ];
      for (const [name, node] of checks) {
        if (!node || node.hidden) continue;
        const r = node.getBoundingClientRect();
        if (!(pr.right <= r.left || pr.left >= r.right || pr.bottom <= r.top || pr.top >= r.bottom)) {
          return name;
        }
      }
      return null;
    }""")
    assert overlap is None, f"浮標與 {overlap} 重疊"


def _assert_step_has_guidance(page):
    action = page.locator("#missionStrip .mission-action").inner_text().strip()
    assert action, "行動句不可為空"
    total = _assert_single_emphasis(page)
    assert total == 1, f"這一步（{action}）沒有可見的浮標、外框或虛線"
    _assert_pointer_not_overlapping_chrome(page)


def test_welcome_help_menu_and_cards(ui):
    page = ui.open()
    assert page.locator('[data-guide="welcome-review"]').is_visible()
    ui.shot("onboarding-01-welcome")

    # 打開說明選單與說明卡，Esc 依序關閉
    page.click("#helpBtn")
    page.wait_for_selector("#helpPopover")
    ui.shot("onboarding-02-help-menu")
    page.click('#helpPopover button:has-text("看這一格是怎麼來的")')
    page.wait_for_selector("#helpCard")
    assert "USD 3,450.00" in page.locator("#helpCard").inner_text()
    ui.shot("onboarding-03-help-card")
    page.keyboard.press("Escape")
    assert page.locator("#helpCard").count() == 0

    # 開始導覽後按關閉導覽，重整後 #helpBtn 仍在且能開說明卡
    page.click('[data-guide="welcome-review"]')
    page.wait_for_selector("#guideBar:not([hidden])")
    page.click('#guideBar button:has-text("關閉導覽")')
    assert page.locator("#guideBar").is_hidden()
    page.reload()
    page.wait_for_selector("#helpBtn")
    page.click("#helpBtn")
    page.wait_for_selector("#helpPopover")
    page.click('#helpPopover button:has-text("一次確認很多筆")')
    page.wait_for_selector("#helpCard")


def test_journey_a_full_walkthrough_and_guards(ui):
    page = ui.open()
    page.click('[data-guide="welcome-review"]')
    page.wait_for_selector("#guideBar:not([hidden])")
    page.wait_for_timeout(300)

    # 第 1 步：執行
    assert "執行" in page.locator("#missionStrip .mission-action").inner_text()
    _assert_step_has_guidance(page)
    ui.shot("onboarding-04-journey-a-step1")
    page.click("#runButton")
    page.wait_for_selector("#result:not([hidden]) table.grid")
    page.wait_for_timeout(400)

    # 第 2 步：看流程卡片（自動推進）
    assert "Match" in page.locator("#missionStrip .mission-action").inner_text()
    assert page.locator("#missionStrip .status-legend").is_visible()
    _assert_step_has_guidance(page)
    ui.shot("onboarding-05-journey-a-step2")
    page.click('[data-guide="stage-match"]')
    page.wait_for_timeout(300)

    # 第 3 步 1/2：怎麼判斷的
    assert "怎麼判斷的" in page.locator("#missionStrip .mission-action").inner_text()
    _assert_step_has_guidance(page)

    # 先測試：去改第 4 步的 INV-1006，不應讓第 3 步完成
    ui.row("INV-1006").click()
    page.wait_for_timeout(200)
    assert "怎麼判斷的" in page.locator("#missionStrip .mission-action").inner_text()

    # 切回 INV-1003 按「怎麼判斷的」
    ui.row("INV-1003").click()
    page.wait_for_timeout(200)
    page.click('[data-guide="issue-trace"]')
    page.wait_for_timeout(350)

    # 第 3 步 2/2：確認無誤，下一筆
    assert "確認無誤，下一筆" in page.locator("#missionStrip .mission-action").inner_text()
    _assert_step_has_guidance(page)
    page.click('[data-guide="confirm-next"]')
    page.wait_for_timeout(450)

    # 第 4 步：修改讀不懂的值（虛線框）
    assert "300" in page.locator("#missionStrip .mission-action").inner_text()
    _assert_step_has_guidance(page)
    assert page.locator(".guide-outline").is_visible()
    ui.shot("onboarding-06-journey-a-step4-outline")

    # 選錯：輸入「約300」出現 ⚠ 提示
    amt = page.locator('#drawer [data-guide="field-金額"]')
    amt.fill("約300")
    amt.press("Enter")
    page.wait_for_timeout(350)
    assert "⚠" in page.locator("#missionStrip .mission-tip").inner_text()

    # 逐字輸入「300」中途不推進
    amt.fill("")
    amt.press_sequentially("30", delay=40)
    page.wait_for_timeout(150)
    assert "300" in page.locator("#missionStrip .mission-action").inner_text()
    amt.press_sequentially("0", delay=40)
    amt.press("Enter")
    page.wait_for_timeout(450)

    # 第 5 步 1/3：選錯 AIR 出現 ⚠ 提示，再改選新增對應值
    assert "新增對應值" in page.locator("#missionStrip .mission-action").inner_text()
    _assert_step_has_guidance(page)
    sel = page.locator('#drawer [data-guide="map-select"]')
    sel.select_option("AIR")
    page.wait_for_timeout(200)
    assert "⚠" in page.locator("#missionStrip .mission-tip").inner_text()
    sel.select_option("__new")
    page.wait_for_timeout(250)

    # 第 5 步 2/3：逐字輸入 LAND 中途不推進，按 Enter 後推進到 3/3
    assert "LAND" in page.locator("#missionStrip .mission-action").inner_text()
    _assert_step_has_guidance(page)
    new_in = page.locator('#drawer [data-guide="map-new"]')
    new_in.press_sequentially("LAN", delay=40)
    page.wait_for_timeout(150)
    assert "LAND" in page.locator("#missionStrip .mission-action").inner_text()
    new_in.press_sequentially("D", delay=40)
    new_in.press("Enter")
    page.wait_for_timeout(250)

    # 第 5 步 3/3：按補上對照
    assert "補上對照" in page.locator("#missionStrip .mission-action").inner_text()
    _assert_step_has_guidance(page)
    page.click('#drawer [data-guide="map-save"]')
    page.wait_for_timeout(450)

    # 第 6 步：選配對候選（先選錯 AA15A0006 看到 ⚠，再交回自動並選 AA15A0005）
    assert "AA15A0005" in page.locator("#missionStrip .mission-action").inner_text()
    _assert_step_has_guidance(page)
    wrong_cand = page.locator('.match-card:has-text("INV-1009") .candidate:has-text("AA15A0006") button:has-text("選這筆")')
    wrong_cand.click()
    page.wait_for_timeout(400)
    assert "⚠" in page.locator("#missionStrip .mission-tip").inner_text()
    page.locator('.match-card:has-text("INV-1009") button:has-text("交回自動")').click()
    page.wait_for_timeout(400)
    right_cand = page.locator('.match-card:has-text("INV-1009") .candidate:has-text("AA15A0005") button:has-text("選這筆")')
    right_cand.click()
    page.wait_for_timeout(450)

    # 第 7 步 1/2：按表格圖示看原始表
    assert "原始表" in page.locator("#missionStrip .mission-action").inner_text()
    _assert_step_has_guidance(page)
    page.locator('.match-card:has-text("INV-1008") [data-guide="match-sheet"]').click()
    page.wait_for_timeout(300)
    page.keyboard.press("Escape")
    page.wait_for_timeout(250)

    # 第 7 步 2/2：按沒有配對
    assert "沒有配對" in page.locator("#missionStrip .mission-action").inner_text()
    _assert_step_has_guidance(page)
    page.locator('.match-card:has-text("INV-1008") [data-guide="match-none"]').click()
    page.wait_for_timeout(450)

    # 第 8 步：下載 Excel
    assert "下載 Excel" in page.locator("#missionStrip .mission-action").inner_text()
    _assert_step_has_guidance(page)
    with page.expect_download() as dl_info:
        page.click("#exportButton")
    assert dl_info.value.suggested_filename.startswith("示範_")
    page.wait_for_timeout(300)

    # 完成狀態
    assert "核對流程走完了" in page.locator("#missionStrip .mission-action").inner_text()
    ui.shot("onboarding-07-journey-a-done")


def test_journey_b_dialog_top_layer(ui):
    page = ui.open()
    page.click('[data-guide="welcome-recipe"]')
    page.wait_for_selector("#guideBar:not([hidden])")
    page.wait_for_timeout(250)

    # 1: 打開新增
    _assert_step_has_guidance(page)
    page.click("#newRecipe")
    page.wait_for_selector("#dialog[open]")
    page.wait_for_timeout(250)

    # 驗證對話框開啟時，對話框內指令條與浮標都在 #dialog 內且可見
    assert page.locator("#dialog .dialog-guide").is_visible()
    assert page.locator("#dialog #guidePointer").is_visible()
    ui.shot("onboarding-08-journey-b-dialog")

    # 2: 複製規格
    page.click('[data-guide="spec-copy"]')
    page.wait_for_timeout(250)

    # 3: 貼上練習回覆並按下一步
    page.click('#dialog [data-guide="dialog-assist"]')
    page.wait_for_timeout(300)
    page.click('[data-guide="recipe-next"]')
    page.wait_for_timeout(350)

    # 4-1: 複製問題給 AI
    assert page.locator('[data-guide="problems-copy"]').is_visible()
    page.click('[data-guide="problems-copy"]')
    page.wait_for_timeout(250)

    # 4-2: 貼上修正版並按下一步
    page.click('#dialog [data-guide="dialog-assist"]')
    page.wait_for_timeout(300)
    page.click('[data-guide="recipe-next"]')
    page.wait_for_timeout(350)

    # 5: 確認並儲存
    assert page.locator('[data-guide="recipe-save"]').is_visible()
    page.click('[data-guide="recipe-save"]')
    page.wait_for_timeout(450)
    assert "recipe 放好了" in page.locator("#missionStrip .mission-action").inner_text()
    assert page.locator('#recipeList .recipe-item:has-text("發票對報關單（練習）")').is_visible()
    ui.shot("onboarding-09-journey-b-done")


def test_narrow_viewport_and_preserve_work(ui):
    # 先建立自己的結果並選到特定列
    page = ui.run_sample()
    ui.row("INV-1006").click()
    page.wait_for_timeout(250)
    orig_run_id = ui.state("state.result.run_id")
    orig_selected = ui.state("state.selected")

    # 窄螢幕 1000px、1100px 檢查導覽列一行、按鈕不換行
    for width in (1000, 1100):
        page.set_viewport_size({"width": width, "height": 800})
        page.wait_for_timeout(150)

    # 從說明選單開始關卡 A → 應該先跳確認卡
    page.click("#helpBtn")
    page.wait_for_selector("#helpPopover")
    page.click('#helpPopover button:has-text("核對一份資料")')
    page.wait_for_selector("#confirmDemoCard")
    page.click('#confirmDemoCard button:has-text("用範例資料開始")')
    page.wait_for_selector("#guideBar:not([hidden])")
    page.wait_for_timeout(250)

    # 確認 1000px 寬度下 #guideBar 一行且按鈕不換行
    page.set_viewport_size({"width": 1000, "height": 800})
    page.wait_for_timeout(200)
    metrics = page.evaluate("""() => {
      const bar = document.getElementById('guideBar');
      const btns = [...bar.querySelectorAll('button')];
      return {
        barH: bar.getBoundingClientRect().height,
        wrapped: btns.some(b => b.getBoundingClientRect().height > 34),
      };
    }""")
    assert metrics["barH"] <= 40 and not metrics["wrapped"], f"窄螢幕導覽列跑版：{metrics}"
    ui.shot("onboarding-10-narrow-1000")

    # 恢復視窗並還原原本的工作
    page.set_viewport_size({"width": 1440, "height": 900})
    page.evaluate("window.Spotlights.engine.restoreWork()")
    page.wait_for_timeout(450)
    assert ui.state("state.result.run_id") == orig_run_id
    assert ui.state("state.selected") == orig_selected


def test_popout_isolation_and_cross_window_advance(ui):
    page = ui.run_sample()
    with ui.context.expect_page() as pop_info:
        page.click('[data-guide="popout-btn"]')
    pop = ui.watch(pop_info.value, "popout")
    pop.wait_for_selector("#result:not([hidden]) table.grid")
    pop.wait_for_timeout(300)

    # popout 視窗看不到任何導覽元件，但 J/K 與確認按鈕可用
    assert pop.locator("#helpBtn").is_hidden()
    assert pop.locator("#guideBar").is_hidden()
    assert pop.locator("#missionStrip").is_hidden()
    assert pop.locator(".jk-tip").count() == 0
    first_sel = pop.evaluate("state.selected")
    pop.keyboard.press("j")
    pop.wait_for_timeout(200)
    assert pop.evaluate("state.selected") != first_sel
    pop.close()
