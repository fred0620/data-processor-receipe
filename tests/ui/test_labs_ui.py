"""實地練習（labs）介面測試：寫錯看提示、修到對、最後一步不可跳過、不汙染左欄並完整恢復原本工作。"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LABS = {item["id"]: item for item in json.loads((ROOT / "app" / "dataprocessor" / "demo" / "labs.json").read_text(encoding="utf-8"))["labs"]}


def test_lab_match_full_flow_and_work_restore(ui):
    # 先跑一份正式工作
    page = ui.run_sample()
    ui.row("INV-1006").click()
    page.wait_for_timeout(250)
    orig_run_id = ui.state("state.result.run_id")
    orig_selected = ui.state("state.selected")

    # 從說明選單開 lab-match
    page.click("#helpBtn")
    page.wait_for_selector("#helpPopover")
    page.click('#helpPopover button:has-text("號碼寫法不同也配得到")')
    page.wait_for_selector("#helpCard")
    page.click('#helpCard button:has-text("實地練習")')
    page.wait_for_selector('[data-guide="lab-editor"]')
    page.wait_for_timeout(350)

    # 練習 recipe 不出現在左欄清單
    assert page.locator('#recipeList .recipe-item:has-text("練習：號碼寫法不同也配得到")').count() == 0

    # 點一下編輯框並送出空白片段（寫錯）→ 看到「哪一列、抓到什麼、應該是什麼」
    editor = page.locator('[data-guide="lab-editor"]')
    editor.click()
    page.wait_for_timeout(150)
    editor.fill("# 還沒寫規則")
    editor.blur()
    page.wait_for_timeout(200)

    # 到第 4 步（試算驗證）：最後一步沒有「下一步」可跳過
    assert "試算" in page.locator("#missionStrip .mission-action").inner_text()
    assert page.locator('#missionStrip button:has-text("下一步")').count() == 0

    # 試算 1 次失敗：看到提示（1004、配到沒有、應該是 AA15A0004）
    page.click('[data-guide="lab-try"]')
    page.wait_for_selector(".lab-check.fail")
    fail_text = page.locator(".lab-checks").inner_text()
    assert "1004" in fail_text and "AA15A0004" in fail_text
    ui.shot("labs-01-fail-hint")

    # 再失敗第 2 次 → 出現「幫我帶入」
    page.click('[data-guide="lab-try"]')
    page.wait_for_selector('[data-guide="lab-fill-answer"]')

    # 點「幫我帶入」再按「試算」→ 通過並顯示完成畫面
    page.click('[data-guide="lab-fill-answer"]')
    page.wait_for_timeout(250)
    page.click('[data-guide="lab-try"]')
    page.wait_for_selector(".lab-done-box")
    assert "練習完成" in page.locator("#missionStrip .mission-action").inner_text()
    ui.shot("labs-02-done")

    # 按「回到我的工作」完整恢復
    page.click('.lab-done-box button:has-text("回到我的工作")')
    page.wait_for_timeout(450)
    assert ui.state("state.result.run_id") == orig_run_id
    assert ui.state("state.selected") == orig_selected
    assert page.locator("#guideBar").is_hidden()


def test_all_other_labs_pass_in_ui(ui):
    page = ui.open()
    for lab_id in ("lab-gate", "lab-mapping", "lab-extract", "lab-validate"):
        lab = LABS[lab_id]
        page.click("#helpBtn")
        page.wait_for_selector("#helpPopover")
        page.click(f'#helpPopover button:has-text("{lab["title"]}")')
        page.wait_for_selector("#helpCard")
        page.click('#helpCard button:has-text("實地練習")')
        page.wait_for_selector('[data-guide="lab-editor"]')
        page.wait_for_timeout(250)

        editor = page.locator('[data-guide="lab-editor"]')
        editor.fill(lab["answer"])
        page.click('[data-guide="lab-try"]')
        page.wait_for_selector(".lab-done-box")
        page.click('.lab-done-box button:has-text("回到我的工作")')
        page.wait_for_timeout(250)
