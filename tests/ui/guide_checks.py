"""導覽浮標的共用檢查：文字不寫方向箭頭，三角形（data-dir）一定指向目標。"""
from __future__ import annotations

ARROWS = "←→↑↓"


def pointer_report(page):
    """回傳浮標目前的文字、方向、位置與目標位置；浮標沒顯示時回傳 None。"""
    return page.evaluate("""() => {
      const ptr = document.getElementById('guidePointer');
      if (!ptr || ptr.hidden) return null;
      const pr = ptr.getBoundingClientRect();
      if (!pr.width || !pr.height) return null;
      const target = window.Spotlights?.engine?.lastTargetEl;
      const tr = target && target.isConnected ? target.getBoundingClientRect() : null;
      const box = (r) => r && ({ left: r.left, right: r.right, top: r.top, bottom: r.bottom });
      return { text: ptr.textContent, dir: ptr.dataset.dir || '', side: ptr.dataset.side || '',
               pointer: box(pr), target: box(tr), viewport: [window.innerWidth, window.innerHeight] };
    }""")


def assert_pointer_text_and_direction(page):
    """浮標可見時：文字不含 ← → ↑ ↓；三角形方向和浮標相對目標的位置一致。"""
    rep = pointer_report(page)
    if rep is None:
        return None
    text = rep["text"]
    assert not any(ch in text for ch in ARROWS), f"浮標文字含方向箭頭：{text!r}"
    assert text.strip(), "浮標文字不可為空"
    assert rep["dir"] in ("left", "right", "up", "down"), f"浮標沒有 data-dir：{rep}"
    if rep["side"] == "offscreen":
        want = {"往上捲": "up", "往下捲": "down"}
        assert text.strip() in want and want[text.strip()] == rep["dir"], f"畫面外浮標文字與方向不符：{rep}"
        return rep
    p, t, d = rep["pointer"], rep["target"], rep["dir"]
    if t is None:
        return rep
    ok = {
        "right": p["right"] <= t["left"] + 1,
        "left": p["left"] >= t["right"] - 1,
        "down": p["bottom"] <= t["top"] + 1,
        "up": p["top"] >= t["bottom"] - 1,
    }[d]
    assert ok, f"三角形朝{d}，但浮標不在目標的相反側：{rep}"
    return rep
