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


def _drag(page, selector, dx):
    box = page.locator(selector).bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + 200
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + dx / 2, y, steps=4)
    page.mouse.move(x + dx, y, steps=4)
    page.mouse.up()


def test_panes_resize_collapse_and_remember(ui):
    ui.context.pages[0].set_viewport_size({"width": 1600, "height": 900})
    page = ui.run_sample()
    width = lambda sel: round(page.locator(sel).bounding_box()["width"])   # noqa: E731
    side = width(".setup")
    _drag(page, "#sideSplit", 120)
    assert abs(width(".setup") - (side + 120)) <= 4, "拖曳左欄的邊界要能調整寬度"
    _drag(page, "#sideSplit", -600)
    assert width(".setup") == 200, "左欄最窄 200px"
    page.dblclick("#sideSplit")
    assert width(".setup") == 272, "連按兩下恢復預設"
    page.focus("#sideSplit")
    page.keyboard.press("ArrowRight")
    assert width(".setup") == 288, "鍵盤左右鍵也能調整"
    # 細節面板
    ui.row("INV-1003").click()
    drawer = width("#drawer")
    _drag(page, "#drawerSplit", -200)
    assert abs(width("#drawer") - (drawer + 200)) <= 4, "拖曳細節的邊界要能調整寬度"
    work = width(".work")
    assert work >= 360, "中間至少留 360px"
    # 記在瀏覽器：重新整理後一樣
    page = ui.run_sample()
    assert width(".setup") == 288
    ui.row("INV-1003").click()
    assert abs(width("#drawer") - (drawer + 200)) <= 4
    # 左欄可以收起，結果變寬
    result = width("#result")
    page.click("#sideToggle")
    assert width(".setup") == 0 and width("#result") > result + 200
    ui.shot("layout-collapsed")
    page.click("#sideToggle")
    assert width(".setup") == 288


def test_result_uses_full_width(ui):
    ui.context.pages[0].set_viewport_size({"width": 2200, "height": 1000})
    page = ui.run_sample()
    work = page.locator(".work").bounding_box()["width"]
    result = page.locator("#result").bounding_box()["width"]
    assert result >= work - 80, "結果區不固定最大寬度，用滿可用空間"
