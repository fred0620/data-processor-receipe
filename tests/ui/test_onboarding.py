"""新手導覽（關卡 A 共 10 步、關卡 B）、說明選單、說明卡、續玩、浮動卡縮放、工作保存與 popout 隔離的介面測試。"""
from __future__ import annotations

import re
from pathlib import Path

from playwright.sync_api import expect

import dataprocessor.server as server
from guide_checks import assert_pointer_text_and_direction

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "app" / "examples" / "workspace"


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


def _assert_pointer_clear(page):
    """浮標可見時，不可和導覽列、指令條、頂列，或目標以外同列可點元素重疊。"""
    overlap = page.evaluate("""() => {
      const ptr = document.getElementById('guidePointer');
      if (!ptr || ptr.hidden) return null;
      const pr = ptr.getBoundingClientRect();
      if (!pr.width || !pr.height) return null;
      const hit = (r) => !(pr.right <= r.left + 1 || pr.left >= r.right - 1 || pr.bottom <= r.top + 1 || pr.top >= r.bottom - 1);
      if (!ptr.closest('#dialog')) {
        for (const [name, node] of [
          ['header.bar', document.querySelector('header.bar')],
          ['.guide-dock', document.querySelector('.guide-dock')],
          ['#guideBar', document.getElementById('guideBar')],
          ['#missionStrip', document.getElementById('missionStrip')],
        ]) {
          if (!node || node.hidden) continue;
          if (hit(node.getBoundingClientRect())) return name;
        }
      }
      const target = window.Spotlights?.engine?.lastTargetEl;
      const bar = target?.closest('.lab-actions, .dialog-actions, .drawer-foot, .actions, .toolbar, .inline-fix, .mission-actions');
      if (bar) {
        for (const sib of bar.querySelectorAll('button, a, input, select, textarea')) {
          if (sib === target || sib.contains(target) || target.contains(sib) || sib.hidden) continue;
          const r = sib.getBoundingClientRect();
          if (r.width > 0 && r.height > 0 && hit(r)) return `sibling:${sib.textContent.trim()}`;
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
    _assert_pointer_clear(page)
    assert_pointer_text_and_direction(page)


def test_welcome_help_menu_and_cards(ui):
    page = ui.open()
    expect(page.locator('[data-guide="welcome-review"]')).to_be_visible()
    ui.shot("onboarding-01-welcome")

    # 打開說明選單與說明卡，Esc 依序關閉
    page.click("#helpBtn")
    expect(page.locator("#helpPopover")).to_be_visible()
    ui.shot("onboarding-02-help-menu")
    page.click('#helpPopover button:has-text("看這一格是怎麼來的")')
    expect(page.locator("#helpCard")).to_be_visible()
    assert "USD 3,450.00" in page.locator("#helpCard").inner_text()
    ui.shot("onboarding-03-help-card")
    page.keyboard.press("Escape")
    expect(page.locator("#helpCard")).to_have_count(0)

    # 開始導覽後按關閉導覽，重整後 #helpBtn 仍在且能開說明卡
    page.click('[data-guide="welcome-review"]')
    expect(page.locator("#guideBar")).to_be_visible()
    page.click('#guideBar button:has-text("關閉導覽")')
    expect(page.locator("#guideBar")).to_be_hidden()
    page.reload()
    expect(page.locator("#helpBtn")).to_be_visible()
    page.click("#helpBtn")
    expect(page.locator("#helpPopover")).to_be_visible()
    page.click('#helpPopover button:has-text("一次確認很多筆")')
    expect(page.locator("#helpCard")).to_be_visible()


def test_journey_a_full_walkthrough_and_guards(ui):
    page = ui.open()
    page.click('[data-guide="welcome-review"]')
    expect(page.locator("#guideBar")).to_be_visible()
    expect(page.locator("#runButton")).to_be_enabled()
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("執行")

    # 第 1 步：執行
    _assert_step_has_guidance(page)
    ui.shot("onboarding-04-journey-a-step1")
    page.click("#runButton")
    expect(page.locator("#result table.grid")).to_be_visible()

    # 第 2 步：看流程卡片（自動推進）
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("Match")
    expect(page.locator("#missionStrip .status-legend")).to_be_visible()
    _assert_step_has_guidance(page)
    ui.shot("onboarding-05-journey-a-step2")
    page.click('[data-guide="stage-match"]')

    # 第 3 步 1/2：怎麼判斷的
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("怎麼判斷的")
    _assert_step_has_guidance(page)

    # 先點 INV-1006 不應讓第 3 步完成
    ui.row("INV-1006").click()
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("怎麼判斷的")

    # 切回 INV-1003 按「怎麼判斷的」
    ui.row("INV-1003").click()
    expect(page.locator('[data-guide="issue-trace"]')).to_be_visible()
    page.click('[data-guide="issue-trace"]')

    # 第 3 步 2/2：確認無誤，下一筆
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("確認無誤，下一筆")
    _assert_step_has_guidance(page)
    page.click('[data-guide="confirm-next"]')

    # 第 4 步：修改讀不懂的值（虛線框）
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("300")
    expect(page.locator(".guide-outline")).to_be_visible()
    _assert_step_has_guidance(page)
    ui.shot("onboarding-06-journey-a-step4-outline")

    # 選錯：輸入「約300」出現 ⚠ 提示
    amt = page.locator('#drawer [data-guide="field-金額"]')
    amt.fill("約300")
    amt.press("Enter")
    expect(page.locator("#missionStrip .mission-tip")).to_contain_text("⚠")

    # 逐字輸入「300」中途不推進
    amt.click()
    amt.press("Control+a")
    amt.press("Backspace")
    amt.press_sequentially("30", delay=30)
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("300")
    amt.press_sequentially("0", delay=30)
    amt.press("Enter")

    # 第 5 步 1/3：選錯 AIR 出現 ⚠ 提示，再改選新增對應值
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("新增對應值")
    _assert_step_has_guidance(page)
    sel = page.locator('#drawer [data-guide="map-select"]')
    sel.select_option("AIR")
    expect(page.locator("#missionStrip .mission-tip")).to_contain_text("⚠")
    sel.select_option("__new")

    # 第 5 步 2/3：逐字輸入 LAND 中途不推進，按 Enter 後推進到 3/3
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("LAND")
    _assert_step_has_guidance(page)
    new_in = page.locator('#drawer [data-guide="map-new"]')
    new_in.press_sequentially("LAN", delay=30)
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("LAND")
    new_in.press_sequentially("D", delay=30)
    new_in.press("Enter")

    # 第 5 步 3/3：按補上對照
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("補上對照")
    _assert_step_has_guidance(page)
    page.click('#drawer [data-guide="map-save"]')

    # 第 6 步：選配對候選（先選錯 AA15A0006 看到 ⚠，再交回自動並選 AA15A0005）
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("AA15A0005")
    _assert_step_has_guidance(page)
    page.locator('.match-card:has-text("INV-1009") .candidate:has-text("AA15A0006") button:has-text("選這筆")').click()
    expect(page.locator("#missionStrip .mission-tip")).to_contain_text("⚠")
    page.locator('.match-card:has-text("INV-1009") button:has-text("交回自動")').click()
    right_cand = page.locator('.match-card:has-text("INV-1009") .candidate:has-text("AA15A0005") button:has-text("選這筆")')
    expect(right_cand).to_be_visible()
    right_cand.click()

    # 第 7 步 1/2：按表格圖示看原始表
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("原始表")
    _assert_step_has_guidance(page)
    page.locator('.match-card:has-text("INV-1008") [data-guide="match-sheet"]').click()
    expect(page.locator("#peek")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("#peek")).to_have_count(0)

    # 第 7 步 2/2：按沒有配對
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("沒有配對")
    _assert_step_has_guidance(page)
    page.locator('.match-card:has-text("INV-1008") [data-guide="match-none"]').click()

    # 第 8 步：把配對做完（子步驟依還沒處理的配對動態產生）
    expect(page.locator("#missionStrip .mission-badge")).to_have_text(re.compile(r"^8"))
    handled = []
    for _ in range(6):
        action = page.locator("#missionStrip .mission-action").inner_text()
        if "確認正確" not in action and "沒有配對" not in action:
            break
        _assert_step_has_guidance(page)
        invoice = re.search(r"INV-\d+", action).group(0)
        handled.append(invoice)
        if "確認正確" in action:
            page.locator(f'.match-card:has-text("{invoice}") [data-guide="match-confirm"]').click()
        else:
            page.locator(f'.match-card:has-text("{invoice}") [data-guide="match-none"]').click()
        # 處理完的卡片離開「需處理」清單，行動句換成下一張
        expect(page.locator("#missionStrip .mission-action")).not_to_have_text(action)
    assert sorted(handled) == ["INV-1005", "INV-1006", "INV-1010"], handled
    ui.shot("onboarding-10-journey-a-step8-done")
    assert ui.state("state.result.matches.every(m => m.counts.todo === 0)")

    # 第 9 步：把剩下的列看完，提醒行的 n 即時更新
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("確認無誤，下一筆")
    expect(page.locator("#missionStrip .mission-badge")).to_have_text(re.compile(r"^9"))
    remaining = ui.state("state.result.output.rows.filter(r => r.status === 'review').length")
    assert remaining >= 1
    for n in range(remaining, 0, -1):
        expect(page.locator("#missionStrip .mission-tip")).to_contain_text(f"還有 {n} 列")
        _assert_step_has_guidance(page)
        page.click('[data-guide="confirm-next"]')

    # 第 10 步：下載 Excel（看完才推進）
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("下載 Excel")
    assert ui.state("state.result.output.rows.filter(r => r.status === 'review').length") == 0
    expect(page.locator("#missionStrip .mission-badge")).to_have_text(re.compile(r"^10"))
    expect(page.locator("#guideBar")).to_contain_text("10/10")
    _assert_step_has_guidance(page)
    with page.expect_download() as dl_info:
        page.click("#exportButton")
    assert dl_info.value.suggested_filename.startswith("示範_")

    # 完成狀態
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("核對流程走完了")
    expect(page.locator("#missionStrip .mission-tip")).to_contain_text("每一列都處理過才下載")
    ui.shot("onboarding-07-journey-a-done")
    assert ui.state("state.result.matches.every(m => m.counts.todo === 0)")
    assert ui.state("state.result.output.rows.filter(r => r.status === 'review').length") == 0


def test_journey_b_dialog_top_layer_and_user_recipe_safe(ui):
    # 使用者先放一份同名的 practice-invoice.yaml（P1-1）
    user_file = server.paths.RECIPES / "practice-invoice.yaml"
    user_yaml = (EXAMPLES / "recipes" / "invoice-declaration.yaml").read_text(encoding="utf-8").replace(
        "id: invoice-declaration", "id: practice-invoice"
    ).replace("name: 發票對報關單（範例）", "name: 我的正式規則")
    user_file.write_text(user_yaml, encoding="utf-8")

    page = ui.open()
    expect(page.locator('#recipeList .recipe-item:has-text("我的正式規則")')).to_be_visible()
    # 使用者的同名 recipe 不應有「練習」標籤
    assert page.locator('#recipeList .recipe-item:has-text("我的正式規則") .demo-tag').count() == 0

    page.click('[data-guide="welcome-recipe"]')
    expect(page.locator("#guideBar")).to_be_visible()
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("新增")

    # 1: 打開新增
    _assert_step_has_guidance(page)
    page.click("#newRecipe")
    expect(page.locator("#dialog[open]")).to_be_visible()
    expect(page.locator("#dialog .dialog-guide")).to_be_visible()
    expect(page.locator("#dialog #guidePointer")).to_be_visible()
    _assert_pointer_clear(page)
    ui.shot("onboarding-08-journey-b-dialog")

    # 2: 複製規格
    page.click('[data-guide="spec-copy"]')
    expect(page.locator("#dialog .dialog-guide .mission-action")).to_contain_text("練習回覆")

    # 3: 貼上練習回覆並按下一步
    page.click('#dialog [data-guide="dialog-assist"]')
    page.click('[data-guide="recipe-next"]')
    expect(page.locator('[data-guide="problems-copy"]')).to_be_visible()

    # 4-1: 複製問題給 AI
    page.click('[data-guide="problems-copy"]')
    expect(page.locator("#dialog .dialog-guide .mission-action")).to_contain_text("修正版")

    # 4-2: 貼上修正版並按下一步
    page.click('#dialog [data-guide="dialog-assist"]')
    page.click('[data-guide="recipe-next"]')
    expect(page.locator('[data-guide="recipe-save"]')).to_be_visible()

    # 第 5 步：還沒按「確認並儲存」前，不因使用者有同名 recipe 就自動完成
    expect(page.locator("#dialog .dialog-guide .mission-action")).to_contain_text("確認並儲存")
    page.click('[data-guide="recipe-save"]')
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("recipe 放好了")
    expect(page.locator('#recipeList .recipe-item:has-text("發票對報關單（練習）") .demo-tag')).to_be_visible()
    ui.shot("onboarding-09-journey-b-done")

    # 按「用它處理範例資料」走進關卡 A，再透過 /api/demo/clear 清掉範例 → 使用者的 recipe 完好無缺
    page.click('#missionStrip button:has-text("用它處理範例資料")')
    expect(page.locator("#guideBar")).to_be_visible()
    page.evaluate("fetch('/api/demo/clear', { method: 'POST' })")
    page.reload()
    expect(page.locator('#recipeList .recipe-item:has-text("我的正式規則")')).to_be_visible()
    assert page.locator('#recipeList .recipe-item:has-text("我的正式規則") .demo-tag').count() == 0
    assert user_file.read_text(encoding="utf-8") == user_yaml


def _setup_user_work(ui):
    """建立使用者的正式工作狀態：選第 2 筆列、切配對分頁、篩選改全部、結果搜尋有字。"""
    page = ui.run_sample()
    rows = ui.state("state.result.output.rows.filter(r => r.status === 'review').map(r => r.rid)")
    second_rid = rows[1]
    page.locator(f'table.grid tbody tr[data-rid="{second_rid}"]').click()
    page.locator('input.search[data-key="rows"]').fill("100")
    page.wait_for_timeout(260)
    page.click('.tab[data-tab="match"]')
    page.click('.tab-body .chip:has-text("全部")')
    snap = ui.state("""() => ({
      recipeId: state.recipeId,
      wbName: state.workbook?.name,
      runId: state.result?.run_id,
      tab: state.tab,
      filter: state.filter,
      search: state.search,
      selected: state.selected,
      matchFilter: state.matchFilter,
    })""")
    return page, snap


def _assert_same_work(ui, snap):
    now = ui.state("""() => ({
      recipeId: state.recipeId,
      wbName: state.workbook?.name,
      runId: state.result?.run_id,
      tab: state.tab,
      filter: state.filter,
      search: state.search,
      selected: state.selected,
      matchFilter: state.matchFilter,
    })""")
    assert now == snap, f"工作狀態未完整還原：\n預期 {snap}\n實際 {now}"


def test_leave_demo_all_exits_restore_user_work(ui):
    """P1-2：所有離開範例／練習的出口都完整還原使用者的工作。"""
    page, snap = _setup_user_work(ui)

    # 在自己的結果上開說明卡再關閉，畫面不動
    page.click("#helpBtn")
    page.click('#helpPopover button:has-text("看這一格是怎麼來的")')
    expect(page.locator("#helpCard")).to_be_visible()
    page.keyboard.press("Escape")
    _assert_same_work(ui, snap)

    # 出口 1：關卡 A 進行到第 3 步 → 按「關閉導覽」
    page.click("#helpBtn")
    page.click('#helpPopover button:has-text("核對一份資料")')
    page.click('#confirmDemoCard button:has-text("用範例資料開始")')
    expect(page.locator("#guideBar")).to_be_visible()
    expect(page.locator("#runButton")).to_be_enabled()
    page.click("#runButton")
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("Match")
    page.click('[data-guide="stage-match"]')
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("怎麼判斷的")
    page.click('#guideBar button:has-text("關閉導覽")')
    expect(page.locator("#guideBar")).to_be_hidden()
    page.wait_for_function("(id) => state.result?.run_id === id", arg=snap["runId"], timeout=5000)
    _assert_same_work(ui, snap)

    # 出口 2：實地練習（lab-match）第 2 步 → 按「關閉導覽」
    page.click("#helpBtn")
    page.click('#helpPopover button:has-text("號碼寫法不同也配得到")')
    page.click('#helpCard button:has-text("實地練習")')
    expect(page.locator('[data-guide="lab-editor"]')).to_be_visible()
    page.click('#guideBar button:has-text("關閉導覽")')
    page.wait_for_function("(id) => state.result?.run_id === id", arg=snap["runId"], timeout=5000)
    _assert_same_work(ui, snap)

    # 出口 3：實地練習 → 按「結束練習」，且 prefs.dismissed 維持 false
    page.evaluate("""() => {
      const p = JSON.parse(localStorage.getItem('dp:onboarding.v1') || '{}');
      p.dismissed = false;
      localStorage.setItem('dp:onboarding.v1', JSON.stringify(p));
      window.Spotlights.engine.loadPrefs();
    }""")
    page.click("#helpBtn")
    page.click('#helpPopover button:has-text("號碼寫法不同也配得到")')
    page.click('#helpCard button:has-text("實地練習")')
    expect(page.locator('[data-guide="lab-editor"]')).to_be_visible()
    page.click('#guideBar button:has-text("結束練習")')
    page.wait_for_function("(id) => state.result?.run_id === id", arg=snap["runId"], timeout=5000)
    _assert_same_work(ui, snap)
    assert ui.state("JSON.parse(localStorage.getItem('dp:onboarding.v1')).dismissed") is False

    # 出口 4：關卡 A 第 2 步重新整理頁面 → 續玩後按「關閉導覽」仍從 sessionStorage 接回
    page.click("#helpBtn")
    page.click('#helpPopover button:has-text("核對一份資料")')
    page.click('#confirmDemoCard button:has-text("用範例資料開始")')
    expect(page.locator("#guideBar")).to_be_visible()
    page.reload()
    expect(page.locator("#helpBtn")).to_be_visible()
    page.click("#helpBtn")
    page.click('#helpPopover button:has-text("核對一份資料")')
    expect(page.locator("#guideBar")).to_be_visible()
    page.click('#guideBar button:has-text("關閉導覽")')
    page.wait_for_function("(id) => state.result?.run_id === id", arg=snap["runId"], timeout=5000)
    _assert_same_work(ui, snap)

    # 出口 5：從關卡 A 進實地練習 → 按「結束練習」：接回使用者的工作，不是範例
    page.click("#helpBtn")
    page.click('#helpPopover button:has-text("核對一份資料")')
    page.click('#confirmDemoCard button:has-text("用範例資料開始")')
    expect(page.locator("#guideBar")).to_be_visible()
    page.click("#helpBtn")
    page.click('#helpPopover button:has-text("號碼寫法不同也配得到")')
    page.click('#helpCard button:has-text("實地練習")')
    expect(page.locator('[data-guide="lab-editor"]')).to_be_visible()
    page.click('#guideBar button:has-text("結束練習")')
    page.wait_for_function("(id) => state.result?.run_id === id", arg=snap["runId"], timeout=5000)
    _assert_same_work(ui, snap)


def test_resume_journey_auto_prepares_and_falls_back(ui):
    """P2-3：續玩關卡 A 自動準備範例資料、保留看懂旗標；失敗或關卡 B 沒開對話框時退回第 1 步。"""
    page = ui.open()
    # 完成第 1 步
    page.click('[data-guide="welcome-review"]')
    expect(page.locator("#runButton")).to_be_enabled()
    page.click("#runButton")
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("Match")

    # 重新整理 → 從說明選單續玩 → 自動準備結果並停在第 2 步且 Match 有外框
    page.reload()
    page.click("#helpBtn")
    page.click('#helpPopover button:has-text("核對一份資料")')
    expect(page.locator("#result table.grid")).to_be_visible()
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("Match")
    expect(page.locator('[data-guide="stage-match"].guide-target')).to_be_visible()
    _assert_step_has_guidance(page)

    # 完成第 2 步後重新整理 → 續玩應停在第 3 步（不回到第 2 步）
    page.click('[data-guide="stage-match"]')
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("怎麼判斷的")
    page.reload()
    page.click("#helpBtn")
    page.click('#helpPopover button:has-text("核對一份資料")')
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("怎麼判斷的")
    _assert_step_has_guidance(page)

    # 範例準備失敗 → 退回第 1 步並更新 prefs
    page.reload()
    page.route("**/api/demo/start", lambda route: route.fulfill(status=500, body='{"error":"boom"}'))
    page.click("#helpBtn")
    page.click('#helpPopover button:has-text("核對一份資料")')
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("執行")
    assert ui.state("JSON.parse(localStorage.getItem('dp:onboarding.v1')).journeys.review.step") == "review-1"
    page.unroute("**/api/demo/start")

    # 關卡 B 第 3 步重新整理 → 續玩應退回第 1 步並指 #newRecipe
    page.evaluate("""() => {
      const p = JSON.parse(localStorage.getItem('dp:onboarding.v1') || '{}');
      p.journeys = p.journeys || {};
      p.journeys.recipe = { step: 'recipe-3', done: false, skipped: [], flags: { openedRecipeDialog: true, copiedSpec: true } };
      localStorage.setItem('dp:onboarding.v1', JSON.stringify(p));
    }""")
    page.reload()
    page.click("#helpBtn")
    page.click('#helpPopover button:has-text("放入 recipe")')
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("新增")
    _assert_step_has_guidance(page)


def test_float_cards_stay_in_viewport_on_resize(ui):
    """P2-4：1440px 打開浮動卡，縮到 1024px 與 1000×600 時都完全在視窗內且可點。"""
    page = ui.open()
    page.click("#helpBtn")
    expect(page.locator("#helpPopover")).to_be_visible()

    for w, h in ((1024, 768), (1000, 600)):
        page.set_viewport_size({"width": w, "height": h})
        page.wait_for_timeout(150)
        box = page.locator("#helpPopover").bounding_box()
        assert box and box["x"] >= 0 and box["x"] + box["width"] <= w + 1, f"{w}x{h} 選單超出水平視窗：{box}"
        assert box["y"] >= 0 and box["y"] + box["height"] <= h + 1, f"{w}x{h} 選單超出垂直視窗：{box}"
        manual_link = page.locator('#helpPopover a:has-text("使用手冊")')
        manual_link.scroll_into_view_if_needed()
        expect(manual_link).to_be_visible()

    # 說明卡也檢查
    page.set_viewport_size({"width": 1440, "height": 900})
    page.click('#helpPopover button:has-text("看這一格是怎麼來的")')
    expect(page.locator("#helpCard")).to_be_visible()
    page.set_viewport_size({"width": 1000, "height": 600})
    page.wait_for_timeout(150)
    cbox = page.locator("#helpCard").bounding_box()
    assert cbox and cbox["x"] >= 0 and cbox["x"] + cbox["width"] <= 1001 and cbox["y"] + cbox["height"] <= 601

    # 1000px 導覽列一行、按鈕不換行
    page.keyboard.press("Escape")
    page.click('[data-guide="welcome-review"]')
    expect(page.locator("#guideBar")).to_be_visible()
    metrics = page.evaluate("""() => {
      const bar = document.getElementById('guideBar');
      const btns = [...bar.querySelectorAll('button')];
      return { barH: bar.getBoundingClientRect().height, wrapped: btns.some(b => b.getBoundingClientRect().height > 34) };
    }""")
    assert metrics["barH"] <= 40 and not metrics["wrapped"]
    ui.shot("onboarding-10-narrow-1000")


def test_popout_isolation_and_cross_window_advance(ui):
    page = ui.run_sample()
    with ui.context.expect_page() as pop_info:
        page.click('[data-guide="popout-btn"]')
    pop = ui.watch(pop_info.value, "popout")
    expect(pop.locator("#result table.grid")).to_be_visible()

    # popout 視窗看不到任何導覽元件，但 J/K 與確認按鈕可用
    expect(pop.locator("#helpBtn")).to_be_hidden()
    expect(pop.locator("#guideBar")).to_be_hidden()
    expect(pop.locator("#missionStrip")).to_be_hidden()
    assert pop.locator(".jk-tip").count() == 0
    first_sel = pop.evaluate("state.selected")
    pop.keyboard.press("j")
    pop.wait_for_function("(prev) => state.selected !== prev", arg=first_sel, timeout=3000)
    pop.close()
