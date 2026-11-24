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


def emphasis_counts(page):
    """可見的浮標、虛線框、外框各有幾個（同一時間最多一種）。"""
    return page.evaluate("""() => {
      const vis = (el) => {
        if (!el || el.hidden) return false;
        const cs = getComputedStyle(el);
        if (cs.display === 'none' || cs.visibility === 'hidden') return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
      };
      return { pointer: vis(document.getElementById('guidePointer')) ? 1 : 0,
               outline: vis(document.querySelector('.guide-outline')) ? 1 : 0,
               frame: [...document.querySelectorAll('.guide-target')].filter(vis).length > 0 ? 1 : 0 };
    }""")


def pointer_overlap(page):
    """浮標可見時，回傳它蓋到的東西（頂列、指令條，或目標以外看得到的可點元素）；沒有就回傳 None。"""
    return page.evaluate("""() => {
      const ptr = document.getElementById('guidePointer');
      if (!ptr || ptr.hidden) return null;
      const pr = ptr.getBoundingClientRect();
      if (!pr.width || !pr.height) return null;
      const hit = (r) => Math.min(pr.right, r.right) - Math.max(pr.left, r.left) > 1
        && Math.min(pr.bottom, r.bottom) - Math.max(pr.top, r.top) > 1;
      const dialog = ptr.closest('dialog');
      if (!dialog) {
        for (const [name, node] of [['header.bar', document.querySelector('header.bar')], ['.guide-dock', document.querySelector('.guide-dock')]]) {
          if (node && !node.hidden && node.getClientRects().length && hit(node.getBoundingClientRect())) return name;
        }
      }
      const target = window.Spotlights?.engine?.lastTargetEl;
      const root = dialog || document;
      for (const el of root.querySelectorAll('button, a[href], input, select, textarea, summary, [role=switch]')) {
        if (el === ptr || !el.getClientRects().length) continue;
        if (target && (el === target || el.contains(target) || target.contains(el))) continue;
        if (getComputedStyle(el).opacity === '0') continue;
        const r = el.getBoundingClientRect();
        if (!r.width || !r.height || !hit(r)) continue;
        const at = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        if (at && (at === el || el.contains(at))) return `${el.tagName.toLowerCase()}:${(el.textContent || el.getAttribute('aria-label') || '').trim().slice(0, 20)}`;
      }
      // 目標鄰近（同一行、同一卡片或同一列）看得到的文字不能被浮標蓋住
      if (target && target.isConnected) {
        const tr = target.getBoundingClientRect();
        const scope = target.closest('tr, li, .card, .practice-card, .help-row, .field') || target.parentElement;
        const sr = scope ? scope.getBoundingClientRect() : null;
        const near = (r) => (r.top < tr.bottom + 4 && r.bottom > tr.top - 4 && r.right > tr.left - 300 && r.left < tr.right + 300)
          || (sr && r.top >= sr.top - 1 && r.bottom <= sr.bottom + 1 && r.left >= sr.left - 1 && r.right <= sr.right + 1);
        const walker = document.createTreeWalker(root === document ? document.body : root, NodeFilter.SHOW_TEXT);
        const range = document.createRange();
        for (let n = walker.nextNode(); n; n = walker.nextNode()) {
          if (!n.nodeValue.trim()) continue;
          const parent = n.parentElement;
          if (!parent || ptr.contains(parent) || target.contains(parent)) continue;
          if (['SCRIPT', 'STYLE', 'OPTION'].includes(parent.tagName) || parent.closest('[hidden], .guide-dock, header.bar')) continue;
          range.selectNodeContents(n);
          for (const r of range.getClientRects()) {
            if (r.width < 2 || r.height < 2 || !hit(r) || !near(r)) continue;
            const at = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
            if (at && (at === parent || parent.contains(at) || at.contains(parent)) && at !== ptr && !ptr.contains(at)) {
              return `文字：${n.nodeValue.trim().slice(0, 20)}`;
            }
          }
        }
      }
      return null;
    }""")


def assert_step_guidance(page):
    """關卡每一步與子步驟的共用檢查：行動句不為空、恰好一種可見的強調、浮標不寫箭頭、不蓋到別的可點元素。"""
    action = page.locator("#missionStrip .mission-action").inner_text().strip()
    assert action, "行動句不可為空"
    counts = emphasis_counts(page)
    assert sum(counts.values()) == 1, f"這一步（{action}）要剛好一種可見的強調：{counts}"
    covered = pointer_overlap(page)
    assert covered is None, f"這一步（{action}）的浮標蓋到 {covered}"
    assert_pointer_text_and_direction(page)
    return action
