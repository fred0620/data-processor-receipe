"""新功能發版檢查（check_whatsnew.py）的單元測試。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import check_whatsnew  # noqa: E402


def test_real_whatsnew_passes():
    assert check_whatsnew.check() == []


def test_missing_version_fails(tmp_path):
    p = tmp_path / "whatsnew.json"
    p.write_text(json.dumps({"versions": [{"version": "0.1.0", "items": []}]}), encoding="utf-8")
    errs = check_whatsnew.check(whatsnew_path=p, version="0.2.0")
    assert any("缺少目前版本 0.2.0" in e for e in errs)


def test_unknown_spotlight_and_length_limits_fail(tmp_path):
    p = tmp_path / "whatsnew.json"
    p.write_text(json.dumps({
        "versions": [{
            "version": "0.2.0",
            "items": [{
                "id": "bad",
                "title": "這是一個超過十六個字上限的非常長標題文字",
                "body": "這是一段超過四十個字上限的非常長說明文字，用來確認檢查腳本真的會把太長的內容擋下來。",
                "spotlight": "no-such-spotlight",
            }],
        }]
    }, ensure_ascii=False), encoding="utf-8")
    errs = check_whatsnew.check(whatsnew_path=p, version="0.2.0")
    assert any("title" in e for e in errs)
    assert any("body" in e for e in errs)
    assert any("no-such-spotlight" in e for e in errs)
