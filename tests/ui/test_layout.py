"""版面：不同螢幕寬度下不會撐破、多行儲存格與細節不會讓版面亂掉。截圖存在 tests/ui/screens/ 給人看。"""
from __future__ import annotations

import pytest

OVERFLOW = "document.documentElement.scrollWidth - document.documentElement.clientWidth"


@pytest.mark.parametrize("width,height", [(1024, 700), (1440, 900), (1920, 1080)])
def test_no_page_overflow(ui, width, height):
    ui.context.pages[0].set_viewport_size({"width": width, "height": height})
    page = ui.run_sample()
    assert ui.state(OVERFLOW) <= 0, "整頁出現橫向捲軸"
    ui.row("INV-1003").click()
    ui.settle()
    assert ui.state(OVERFLOW) <= 0, "打開細節後整頁出現橫向捲軸"
    box = page.locator("#drawer").bounding_box()
    assert box["x"] + box["width"] <= width + 1, "細節面板超出視窗"
    # 表格太寬時在自己的區塊裡捲動，不會把頁面撐開
    wrap = page.locator(".table-wrap").evaluate("e => getComputedStyle(e).overflowX")
    assert wrap in ("auto", "scroll")
    ui.shot(f"layout-{width}")


def test_multiline_cells_stay_tidy(ui):
    page = ui.run_sample()
    page.click(".chip:has-text('全部')")
    plain = ui.row("INV-1001").bounding_box()["height"]
    one_line = ui.row("INV-1003").bounding_box()["height"]
    assert abs(one_line - plain) <= 2, "壓成一行時，多行的格子不應該讓這一列變高"
    page.click("button:has-text('顯示換行')")
    cell = ui.row("INV-1003").locator("td .cell-text").nth(2)
    lines = cell.evaluate("e => Math.round(e.getBoundingClientRect().height / parseFloat(getComputedStyle(e).lineHeight))")
    assert 2 <= lines <= 4, f"換行顯示最多 4 行，實際 {lines} 行"
    ui.shot("multiline-wrap")
    page.click("button:has-text('壓成一行')")
    ui.row("INV-1003").click()
    area = ui.field("品名").locator("textarea")
    assert area.evaluate("e => e.offsetHeight") > 40, "細節的文字框要長高顯示多行"
    assert area.evaluate("e => e.offsetHeight") <= 222, "文字框最高 220px，太長就捲動"


def test_dialog_fits_small_screen(ui):
    ui.context.pages[0].set_viewport_size({"width": 1024, "height": 640})
    page = ui.open()
    page.click("#recipeList .recipe-item")
    page.click("#recipeList button:has-text('查看')")
    page.wait_for_selector("#dialog .explain")
    box = page.locator("#dialog").bounding_box()
    assert box["y"] >= 0 and box["y"] + box["height"] <= 641, "對話框超出視窗高度"
    assert page.locator("#dialog button:has-text('關閉')").is_visible()
    ui.shot("dialog-small")
