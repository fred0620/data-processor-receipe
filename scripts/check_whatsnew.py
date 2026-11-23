"""檢查 whatsnew.json：目前版本存在、每個 spotlight id 都在 spotlights.js、字數符合上限。

    uv run --project app python scripts/check_whatsnew.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WHATSNEW = ROOT / "app" / "dataprocessor" / "web" / "whatsnew.json"
SPOTLIGHTS = ROOT / "app" / "dataprocessor" / "web" / "spotlights.js"
PYPROJECT = ROOT / "app" / "pyproject.toml"

TITLE_LIMIT = 16
BODY_LIMIT = 40


def read_version(pyproject: Path = PYPROJECT) -> str:
    text = pyproject.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise ValueError("pyproject.toml 找不到 version")
    return match.group(1)


def known_spotlight_ids(spotlights_js: Path = SPOTLIGHTS) -> set[str]:
    text = spotlights_js.read_text(encoding="utf-8")
    return set(re.findall(r'id:\s*"([^"]+)"', text)) | set(re.findall(r'"([a-z0-9-]+)":\s*\{', text))


def check(whatsnew_path: Path = WHATSNEW, spotlights_path: Path = SPOTLIGHTS, version: str | None = None) -> list[str]:
    errors: list[str] = []
    target_version = version or read_version()
    data = json.loads(whatsnew_path.read_text(encoding="utf-8"))
    versions = data.get("versions") or []
    version_map = {v.get("version"): v for v in versions if isinstance(v, dict)}
    if target_version not in version_map:
        errors.append(f"whatsnew.json 缺少目前版本 {target_version} 的條目")

    known_ids = known_spotlight_ids(spotlights_path)
    for entry in versions:
        ver = entry.get("version", "?")
        for item in entry.get("items") or []:
            item_id = item.get("id", "?")
            title = str(item.get("title", ""))
            body = str(item.get("body", ""))
            spot = str(item.get("spotlight", ""))
            if not title or len(title) > TITLE_LIMIT:
                errors.append(f"{ver}/{item_id}：title 長度 {len(title)} 超過上限 {TITLE_LIMIT}")
            if not body or len(body) > BODY_LIMIT:
                errors.append(f"{ver}/{item_id}：body 長度 {len(body)} 超過上限 {BODY_LIMIT}")
            if spot not in known_ids:
                errors.append(f"{ver}/{item_id}：spotlight「{spot}」不存在於 spotlights.js")
    return errors


def main() -> int:
    errors = check()
    if errors:
        for err in errors:
            print("錯誤：", err, file=sys.stderr)
        return 1
    print("whatsnew.json 檢查通過")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
