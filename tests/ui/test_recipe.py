"""Recipe：新增（貼上 → 看說明 → 儲存）、錯誤提示、查看、刪除。"""
from __future__ import annotations

from conftest import EXAMPLES  # noqa: F401  (tests/ui/conftest.py)

SAMPLE = (EXAMPLES / "recipes" / "invoice-declaration.yaml").read_text(encoding="utf-8")


def _copy(name: str, title: str) -> str:
    lines = SAMPLE.splitlines()
    out = []
    for line in lines:
        if line.startswith("name:"):
            line = f"name: {title}"
        out.append(line)
    text = "\n".join(out) + "\n"
    return text if "\nid:" not in text else text.replace("\nid: invoice-declaration", f"\nid: {name}")


def test_add_recipe_two_steps(ui):
    page = ui.open()
    page.click("#newRecipe")
    page.fill("#dialog textarea", _copy("invoice-copy", "發票對報關單（測試）"))
    page.click("#dialog button:has-text('下一步：確認說明')")
    page.wait_for_selector("#dialog .explain")
    text = page.inner_text("#dialog .explain")
    assert "每一列" in text and "如果" in text                                # 邏輯說明，不是設定的逐項翻譯
    ui.shot("recipe-explain")
    page.click("#dialog button:has-text('返回修改')")
    assert page.is_visible("#dialog textarea")
    page.click("#dialog button:has-text('下一步：確認說明')")
    page.click("#dialog button:has-text('確認並儲存')")
    ui.settle()
    assert page.locator("#recipeList .recipe-item:has-text('發票對報關單（測試）')").count() == 1


def test_bad_recipe_shows_problems(ui):
    page = ui.open()
    page.click("#newRecipe")
    page.fill("#dialog textarea", "name: x\nbase: &a {k: 1}\nother: *a\n")
    page.click("#dialog button:has-text('下一步：確認說明')")
    ui.settle()
    problems = page.locator("#dialog .problems")
    assert problems.count() == 1 and "錨點" in problems.inner_text()
    assert page.is_visible("#dialog button:has-text('複製問題給 AI')")
    page.click("#dialog button:has-text('取消')")


def test_view_and_delete_recipe(ui):
    page = ui.open()
    page.click("#recipeList .recipe-item")
    page.click("#recipeList button:has-text('查看')")
    page.wait_for_selector("#dialog .explain")
    page.click("#dialog .chip:has-text('YAML')")
    assert "inputs:" in page.locator("#dialog textarea").input_value()
    page.click("#dialog button:has-text('關閉')")
    page.click("#recipeList button:has-text('刪除')")                         # 確認對話框會自動按確定
    ui.settle()
    assert page.locator("#recipeList .recipe-item").count() == 0
