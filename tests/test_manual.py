"""使用手冊測試：說明卡的所有手冊錨點都存在於產生的 HTML，且卡片標題與手冊章節標題一致。"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPOTLIGHTS = ROOT / "app" / "dataprocessor" / "web" / "spotlights.js"
MANUAL_HTML = ROOT / "app" / "user-guide.html"


def _extract_cards() -> list[tuple[str, str]]:
    """從 spotlights.js 擷取所有帶 anchor 的 (anchor, title)。"""
    text = SPOTLIGHTS.read_text(encoding="utf-8")
    pairs = []
    for match in re.finditer(r'anchor:\s*"([^"]+)"', text):
        anchor = match.group(1)
        after = text[match.end() : match.end() + 180]
        before = text[max(0, match.start() - 180) : match.start()]
        title_m = re.search(r'title:\s*"([^"]+)"', after) or re.search(r'title:\s*"([^"]+)"', before)
        assert title_m, f"anchor={anchor} 找不到 title"
        pairs.append((anchor, title_m.group(1)))
    assert len(pairs) >= 11, f"預期至少 11 張說明卡，只找到 {len(pairs)}"
    return pairs


def test_all_card_anchors_and_titles_match_manual_html():
    html = MANUAL_HTML.read_text(encoding="utf-8")
    for anchor, title in _extract_cards():
        match = re.search(rf'<h([2-4])[^>]*id="{re.escape(anchor)}"[^>]*>(.*?)</h\1>', html, re.S)
        assert match is not None, f"app/user-guide.html 缺少錨點 id=\"{anchor}\""
        heading = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        if anchor == "help-ai-recipe":
            # recipe-overview 總覽卡連到「讓 AI 幫你寫 recipe」章節
            assert "recipe" in heading
        else:
            assert heading == title, f"錨點 #{anchor} 標題不一致：手冊「{heading}」!= 卡片「{title}」"


def test_manual_html_has_no_inline_script_for_csp():
    html = MANUAL_HTML.read_text(encoding="utf-8")
    # 不允許沒有 src 的 inline <script>（會被 /docs/ 的 CSP 擋住）
    inline_scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", html, re.I)
    assert not inline_scripts, f"手冊 HTML 不應有 inline script：{inline_scripts}"
    assert "/web/manual-search.js" in html
