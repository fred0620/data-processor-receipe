"""實地練習（labs）介面測試：寫錯看提示、浮標不蓋住按鈕（含 280px 細節寬度）、修到對、不可跳過、完整恢復原本工作。"""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import expect

from guide_checks import assert_pointer_text_and_direction

ROOT = Path(__file__).resolve().parents[2]
LABS = {item["id"]: item for item in json.loads((ROOT / "app" / "dataprocessor" / "demo" / "labs.json").read_text(encoding="utf-8"))["labs"]}


def _assert_lab_pointer_not_covering_buttons(page):
    overlap = page.evaluate("""() => {
      const ptr = document.getElementById('guidePointer');
      if (!ptr || ptr.hidden) return null;
      const pr = ptr.getBoundingClientRect();
      if (!pr.width || !pr.height) return null;
      const target = window.Spotlights?.engine?.lastTargetEl;
      const hit = (r) => !(pr.right <= r.left + 1 || pr.left >= r.right - 1 || pr.bottom <= r.top + 1 || pr.top >= r.bottom - 1);
      for (const el of document.querySelectorAll('#drawer button, #drawer a, #drawer textarea')) {
        if (el === target || el.contains(target) || target?.contains(el) || el.hidden) continue;
        const r = el.getBoundingClientRect();
        if (r.width > 0 && r.height > 0 && hit(r)) return el.textContent.trim() || el.tagName;
      }
      return null;
    }""")
    assert overlap is None, f"練習浮標蓋住按鈕：{overlap}"
    assert_pointer_text_and_direction(page)


def test_lab_match_full_flow_pointer_clear_and_work_restore(ui):
    # 先跑一份正式工作
    page = ui.run_sample()
    ui.row("INV-1006").click()
    orig_run_id = ui.state("state.result.run_id")
    orig_selected = ui.state("state.selected")

    # 從說明選單開 lab-match
    page.click("#helpBtn")
    expect(page.locator("#helpPopover")).to_be_visible()
    page.click('#helpPopover button:has-text("號碼寫法不同也配得到")')
    expect(page.locator("#helpCard")).to_be_visible()
    page.click('#helpCard button:has-text("實地練習")')
    expect(page.locator('[data-guide="lab-editor"]')).to_be_visible()

    # 練習 recipe 不出現在左欄清單
    assert page.locator('#recipeList .recipe-item:has-text("練習：號碼寫法不同也配得到")').count() == 0

    # 點一下編輯框並送出錯誤片段 → 到第 4 步（試算驗證）
    editor = page.locator('[data-guide="lab-editor"]')
    editor.click()
    editor.fill("# 還沒寫規則")
    editor.blur()

    # 最後一步沒有「下一步」可跳過
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("試算")
    assert page.locator('#missionStrip button:has-text("下一步")').count() == 0

    # 試算 1 次失敗：看到提示且浮標不蓋住「複製給 AI 的提問」
    page.click('[data-guide="lab-try"]')
    expect(page.locator(".lab-check.fail")).to_be_visible()
    fail_text = page.locator(".lab-checks").inner_text()
    assert "1004" in fail_text and "AA15A0004" in fail_text
    page.wait_for_timeout(150)
    _assert_lab_pointer_not_covering_buttons(page)
    ui.shot("labs-01-fail-hint")

    # 細節寬度縮到最小值 280px 時浮標仍不蓋住其他按鈕
    page.evaluate("document.querySelector('.layout').style.setProperty('--drawer-w', '280px')")
    page.wait_for_timeout(200)
    _assert_lab_pointer_not_covering_buttons(page)
    page.evaluate("document.querySelector('.layout').style.setProperty('--drawer-w', '360px')")

    # 再失敗第 2 次 → 出現「幫我帶入」
    page.click('[data-guide="lab-try"]')
    expect(page.locator('[data-guide="lab-fill-answer"]')).to_be_visible()
    _assert_lab_pointer_not_covering_buttons(page)

    # 點「幫我帶入」再按「試算」→ 通過並顯示完成畫面
    page.click('[data-guide="lab-fill-answer"]')
    page.click('[data-guide="lab-try"]')
    expect(page.locator(".lab-done-box")).to_be_visible()
    expect(page.locator("#missionStrip .mission-action")).to_contain_text("練習完成")
    ui.shot("labs-02-done")

    # 按「回到我的工作」完整恢復
    page.click('.lab-done-box button:has-text("回到我的工作")')
    page.wait_for_function("(id) => state.result?.run_id === id", arg=orig_run_id, timeout=5000)
    assert ui.state("state.selected") == orig_selected
    expect(page.locator("#guideBar")).to_be_hidden()


def test_all_other_labs_pass_in_ui(ui):
    page = ui.open()
    for lab_id in ("lab-gate", "lab-mapping", "lab-extract", "lab-validate"):
        lab = LABS[lab_id]
        page.click("#helpBtn")
        expect(page.locator("#helpPopover")).to_be_visible()
        page.click(f'#helpPopover button:has-text("{lab["title"]}")')
        expect(page.locator("#helpCard")).to_be_visible()
        page.click('#helpCard button:has-text("實地練習")')
        expect(page.locator('[data-guide="lab-editor"]')).to_be_visible()

        editor = page.locator('[data-guide="lab-editor"]')
        editor.click()
        editor.fill(lab["answer"])
        editor.blur()
        page.wait_for_timeout(150)
        _assert_lab_pointer_not_covering_buttons(page)
        page.click('[data-guide="lab-try"]')
        expect(page.locator(".lab-done-box")).to_be_visible()
        page.click('.lab-done-box button:has-text("回到我的工作")')
        expect(page.locator("#guideBar")).to_be_hidden()
