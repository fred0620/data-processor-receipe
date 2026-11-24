"""把使用手冊與換版說明轉成單一 HTML（圖片內嵌、Stageshow 風格、左側固定目錄與離線搜尋）。

用 uv run --project app python scripts/build_manual.py 執行。
"""
import base64
import re
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

STYLE = """
:root {
  --canvas: #f6f5f4; --surface: #ffffff; --well: #efeeec;
  --ink-1: rgba(0,0,0,.04); --ink-2: rgba(0,0,0,.06); --ink-3: rgba(0,0,0,.08); --ink-4: rgba(0,0,0,.1);
  --line: rgba(0,0,0,.06); --text: #7a7a7d; --text-strong: #262628; --text-faint: #9a9a9d;
  --accent: #3b82f6; --accent-soft: rgba(59,130,246,.12); --accent-text: #306bca;
  --success: #22c55e; --warning: #f59e0b; --danger: #ef4444;
  --radius-sm: 6px; --radius-md: 8px; --radius-lg: 10px;
  --shadow-card: 0 1px 2px rgba(0,0,0,.04);
  --font: system-ui, -apple-system, "PingFang TC", "Microsoft JhengHei", "Noto Sans TC", sans-serif;
  --mono: "SF Mono", "SFMono-Regular", ui-monospace, Consolas, monospace;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--canvas); color: var(--text-strong);
  font: 400 15px/1.7 var(--font); -webkit-font-smoothing: antialiased; }
.manual-shell { display: flex; min-height: 100vh; }
.sidebar {
  position: sticky; top: 0; align-self: flex-start; width: 268px; flex: none;
  height: 100vh; overflow-y: auto; padding: 20px 16px;
  background: var(--surface); border-right: 1px solid var(--line);
}
.sidebar-title { font-size: 13.5px; font-weight: 600; color: var(--text-strong); margin: 0 0 10px; }
.sidebar-search {
  width: 100%; height: 32px; padding: 0 10px; margin-bottom: 6px;
  border: 1px solid var(--ink-4); border-radius: var(--radius-sm);
  background: var(--canvas); color: var(--text-strong); font: 400 13px var(--font);
}
.sidebar-search:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
.search-status { font-size: 12.5px; color: var(--text); min-height: 18px; margin-bottom: 8px; }
.sidebar-toc ul { list-style: none; margin: 0; padding: 0; }
.sidebar-toc ul ul { padding-left: 12px; margin-top: 2px; }
.sidebar-toc li { margin: 2px 0; }
.sidebar-toc a {
  display: block; padding: 3px 6px; border-radius: var(--radius-sm);
  color: var(--text-strong); text-decoration: none; font-size: 13px; line-height: 1.45;
}
.sidebar-toc ul ul a { color: var(--text); font-size: 12.5px; }
.sidebar-toc a:hover { background: var(--ink-1); color: var(--accent-text); }

main { flex: 1; min-width: 0; max-width: 860px; margin: 0 auto; padding: 36px 40px 80px; }
.doc-card { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card); padding: 32px 36px; }
h1 { font-size: 26px; line-height: 1.3; margin: 0 0 12px; letter-spacing: -0.01em; }
h2 { font-size: 19px; margin: 40px 0 12px; padding-top: 16px; border-top: 1px solid var(--line); }
h3 { font-size: 16px; margin: 28px 0 8px; color: var(--text-strong); }
h4 { font-size: 15px; margin: 22px 0 6px; color: var(--accent-text); scroll-margin-top: 20px; }
p { margin: 8px 0; }
ul, ol { margin: 8px 0; padding-left: 22px; }
li { margin: 4px 0; }
strong { font-weight: 600; }
a { color: var(--accent-text); text-decoration: none; }
a:hover { text-decoration: underline; }
img { display: block; max-width: 100%; height: auto; margin: 14px 0 20px;
  border: 1px solid var(--line); border-radius: var(--radius-md); box-shadow: var(--shadow-card); }
table { width: 100%; border-collapse: collapse; margin: 14px 0 22px; font-size: 13.5px; }
th { text-align: left; padding: 8px 10px 8px 0; font-weight: 600;
  border-top: 1.5px solid var(--text-strong); border-bottom: 1px solid var(--text-strong); }
td { text-align: left; padding: 7px 10px 7px 0; border-bottom: 1px solid var(--line); vertical-align: top; }
tbody tr:last-child td { border-bottom: 1.5px solid var(--text-strong); }
blockquote { margin: 14px 0; padding: 8px 14px; background: var(--accent-soft);
  border-left: 3px solid var(--accent); border-radius: 0 var(--radius-sm) var(--radius-sm) 0; }
code { background: var(--well); padding: 1px 5px; border-radius: 4px; font-size: 13px; font-family: var(--mono); }
pre { background: var(--well); padding: 12px 14px; border-radius: var(--radius-md); overflow-x: auto; font-size: 13px; }
pre code { background: none; padding: 0; }

@media (max-width: 900px) {
  .manual-shell { display: block; }
  .sidebar { position: static; width: auto; height: auto; border-right: 0; border-bottom: 1px solid var(--line); }
  main { padding: 20px 16px 60px; }
  .doc-card { padding: 20px; }
}
@media print {
  .sidebar { display: none !important; }
  body { background: #fff; }
  main { max-width: none; padding: 0; }
  .doc-card { border: 0; box-shadow: none; padding: 0; }
  h2 { break-after: avoid; }
  img { break-inside: avoid; }
}
"""


def inline_image(match: re.Match) -> str:
    path = DOCS / match.group(1)
    if not path.is_file():
        return match.group(0)
    mime = "image/svg+xml" if path.suffix == ".svg" else "image/png"
    data = base64.b64encode(path.read_bytes()).decode()
    return f'src="data:{mime};base64,{data}"'


def wrap_sections(html: str) -> str:
    """把每個 h2 區塊包成 <section data-sec>，讓離線搜尋可以逐節過濾。"""
    parts = re.split(r"(?=<h2\b)", html)
    if len(parts) <= 1:
        return html
    head = parts[0]
    wrapped = [f'<section data-sec="1">{part}</section>' for part in parts[1:]]
    return head + "".join(wrapped)


PAGES = {"user-guide": "資料處理器使用手冊", "update-guide": "資料處理器換版說明"}  # 檔名用英文，避免 ZIP 與上傳工具不支援中文路徑


def build(name: str, title: str) -> None:
    converter = markdown.Markdown(
        extensions=["tables", "fenced_code", "toc", "sane_lists", "attr_list"],
        extension_configs={"toc": {"toc_depth": "2-4"}},
    )
    body = converter.convert((DOCS / f"{name}.md").read_text(encoding="utf-8"))
    body = re.sub(r'src="(images/[^"]+)"', inline_image, body)
    # 文件之間的連結改指向 HTML，在工具裡和直接雙擊開啟都能用
    for other in PAGES:
        body = body.replace(f'href="{other}.md"', f'href="{other}.html"')
    body = wrap_sections(body)
    sidebar = (
        '<aside class="sidebar">'
        f'<div class="sidebar-title">{title}</div>'
        '<input id="manualSearch" class="sidebar-search" type="search" placeholder="搜尋標題或關鍵字…" aria-label="搜尋手冊">'
        '<div id="manualSearchStatus" class="search-status"></div>'
        f'<nav class="sidebar-toc" aria-label="目錄">{converter.toc}</nav>'
        "</aside>"
    )
    page = (
        '<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{title}</title><style>{STYLE}</style></head>"
        f'<body><div class="manual-shell">{sidebar}<main><article class="doc-card">{body}</article></main></div>'
        '<script src="/web/manual-search.js" defer></script></body></html>'
    )
    (ROOT / "app" / f"{name}.html").write_text(page, encoding="utf-8")


def main() -> None:
    for name, title in PAGES.items():
        build(name, title)
    print("完成")


if __name__ == "__main__":
    main()
