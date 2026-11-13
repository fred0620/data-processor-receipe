"""檢查時的可讀性：選到的列看得出問題格、用鍵盤選檔、筆電寬度下表格不被擠扁、確認後畫面立刻更新。"""
from __future__ import annotations

WARNING_SOFT = "rgba(245, 158, 11, 0.14)"


def test_selected_row_keeps_flagged_cell(ui):
    page = ui.run_sample()
    ui.row("INV-1003").click()
    ui.settle()
    page.mouse.move(5, 5)                        # 滑鼠移開：滑過時本來就會顯示，要量的是沒滑過的樣子
    cell = ui.row("INV-1003").locator("td.cell-review").first
    assert cell.count() == 1
    assert cell.evaluate("e => getComputedStyle(e).backgroundColor") == WARNING_SOFT, \
        "選到的列裡，有問題的那一格要保留橘色標記"
    other = ui.row("INV-1003").locator("td:not(.cell-review):not(.status-col):not(.rowno)").first
    assert other.evaluate("e => getComputedStyle(e).backgroundColor") != WARNING_SOFT
    ui.shot("selected-flagged", clip={"x": 0, "y": 0, "width": 1280, "height": 720})


def test_pick_workbook_with_keyboard(ui):
    page = ui.open()
    for _ in range(20):
        page.keyboard.press("Tab")
        if page.evaluate("document.activeElement.id") == "dropZone":
            break
    else:
        raise AssertionError("按 Tab 到不了選檔區")
    with page.expect_file_chooser() as chooser:
        page.keyboard.press("Enter")
    assert chooser.value is not None
    focus = page.locator("#dropZone").evaluate("e => getComputedStyle(e).boxShadow")
    assert focus != "none", "選檔區有鍵盤焦點時要看得出來"


def test_laptop_width_gives_the_table_room(ui):
    ui.context.pages[0].set_viewport_size({"width": 1366, "height": 768})
    page = ui.open()
    width = lambda sel: round(page.locator(sel).bounding_box()["width"])   # noqa: E731
    assert width(".setup") > 0, "還沒打開細節時，左欄照常顯示"
    page = ui.run_sample()                       # 執行完會自動打開第一筆需檢查的列
    assert page.is_visible("#drawer")
    assert width(".work") >= 900, "細節打開後中間至少留 900px"
    assert width(".setup") == 0, "太窄時左欄暫時收起"
    assert page.locator("#sideToggle").get_attribute("aria-label") == "展開左欄"
    rows = {}
    for card in page.locator(".pipeline > li").all():
        rows.setdefault(round(card.bounding_box()["y"]), []).append(card)
    assert len({len(r) for r in rows.values()}) == 1, "步驟卡每一行一樣多張，不會剩一張在第二行"
    tabs = page.locator("#tabs .tab")
    assert tabs.first.bounding_box()["y"] == tabs.last.bounding_box()["y"], "分頁不換行"
    ui.shot("fit-1366")
    # 想看左欄時可以打開，關掉細節後回到原本的樣子，而且沒有改到使用者的收起設定
    page.click("#sideToggle")
    assert width(".setup") > 0
    page.click("#drawerClose")
    ui.settle()
    assert width(".setup") > 0
    ui.row("INV-1003").click()
    ui.settle()
    assert width(".setup") == 0, "下一次打開細節，太窄時一樣暫時收起"
    page = ui.open()
    assert width(".setup") > 0, "暫時收起不寫進設定"


def test_narrow_window_overlays_details(ui):
    ui.context.pages[0].set_viewport_size({"width": 800, "height": 800})
    page = ui.run_sample()
    ui.row("INV-1003").click()
    ui.settle()
    assert page.locator(".layout.drawer-over").count() == 1
    work = page.locator(".work").bounding_box()
    assert work["width"] >= 760, "細節蓋在表格上，結果區用滿寬度"
    drawer = page.locator("#drawer").bounding_box()
    assert drawer["x"] + drawer["width"] <= 801
    assert ui.state("document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 0
    ui.shot("fit-800")


def test_confirm_updates_without_full_rerun(ui):
    page = ui.run_sample()
    ui.row("INV-1003").click()
    ui.settle()
    before = page.locator("#progress").inner_text()
    with page.expect_response(lambda r: "/dismiss" in r.url) as response:
        page.click("#drawer .issue .link:text-is('確認無誤')")
    assert response.value.status == 200
    ui.settle()
    after = page.locator("#progress").inner_text()
    assert after != before and "1 / 6" in after, f"確認後進度要更新（{before} → {after}）"
