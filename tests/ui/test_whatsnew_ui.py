"""新功能導覽介面測試：全新使用者不跳、升級者跳一次、returning 使用者跳、看完小點消失、導覽中只亮小點。"""
from __future__ import annotations

import dataprocessor.server as server


def test_whatsnew_triggers_and_clears(ui):
    # 1. 全新使用者（無 whatsnewSeen 且 returning=False）：不跳小卡也不亮小點
    page = ui.open()
    page.wait_for_timeout(1500)
    assert page.locator("#whatsNewCard").count() == 0
    assert page.locator("#helpBtn .help-dot").is_hidden()

    # 2. 舊版本使用者（whatsnewSeen = "0.1.0"）：亮小點並於 1.2 秒後跳出小卡
    page.evaluate("""() => {
      localStorage.setItem('dp:onboarding.v1', JSON.stringify({
        dismissed: false,
        journeys: { review: { step: null, done: false, skipped: [] }, recipe: { step: null, done: false, skipped: [] } },
        cardsSeen: [], labsDone: [], tipsSeen: { jk: 0 },
        whatsnewSeen: '0.1.0'
      }));
    }""")
    page.reload()
    page.wait_for_selector("#helpBtn .help-dot:not([hidden])")
    page.wait_for_selector("#whatsNewCard", timeout=3000)
    ui.shot("whatsnew-01-popup")

    # 按「看看」並逐項看完到結束 → 小點消失
    page.click('#whatsNewCard button:has-text("看看")')
    page.wait_for_selector("#whatsNewTourCard")
    page.click('#whatsNewTourCard button:has-text("結束")')
    page.wait_for_timeout(200)
    assert page.locator("#helpBtn .help-dot").is_hidden()

    # 3. returning=True 且沒有 whatsnewSeen：跳出新功能小卡
    server.paths.REVIEWS.mkdir(parents=True, exist_ok=True)
    (server.paths.REVIEWS / "existing.json").write_text("{}", encoding="utf-8")
    page.evaluate("localStorage.removeItem('dp:onboarding.v1')")
    page.reload()
    page.wait_for_selector("#helpBtn .help-dot:not([hidden])")
    page.wait_for_selector("#whatsNewCard", timeout=3000)

    # 4. 導覽進行中：只亮小點、不跳小卡
    page.evaluate("localStorage.removeItem('dp:onboarding.v1')")
    page.reload()
    page.wait_for_selector('[data-guide="welcome-review"]')
    page.click('[data-guide="welcome-review"]')
    page.wait_for_selector("#guideBar:not([hidden])")
    page.wait_for_timeout(1500)
    assert page.locator("#helpBtn .help-dot").is_visible()
    assert page.locator("#whatsNewCard").count() == 0
