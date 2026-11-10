"""人工決定的存放：修改的值、指定的配對、確認過的警示、補上的對照。

人工決定跟 recipe 分開存，重新執行時再套上去；recipe 或資料改了，原本的決定不會消失，
對不上時會標記出來。修改的值一律保留原值。
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

from .textnorm import key

_lock = threading.Lock()


def _read(path: Path, default: dict) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else default
    except (OSError, ValueError):
        return default


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=1)
    os.replace(temp, path)  # 寫完才換掉，避免當機時留下寫到一半的檔案


class ReviewStore:
    """同一份 recipe 加同一份 workbook（以內容雜湊判斷）共用一組人工決定。"""

    def __init__(self, root: Path, recipe_id: str, workbook_hash: str):
        self.path = root / recipe_id / f"{workbook_hash}.json"
        self.data = _read(self.path, {})
        self.data.setdefault("edits", {})      # rid → 欄位 → {original, value}
        self.data.setdefault("matches", {})    # 配對名稱 → 左表 rid → 右表 rid 清單（空清單代表確定沒有配對）
        self.data.setdefault("dismissed", [])  # 確認過、不用再提醒的警示

    def save(self) -> None:
        with _lock:
            _write(self.path, self.data)

    def set_edit(self, rid: str, column: str, original, value) -> None:
        row = self.data["edits"].setdefault(rid, {})
        if value is None and column in row:
            del row[column]                    # 還原
        elif value is not None:
            keep = row.get(column, {}).get("original", original)
            row[column] = {"original": keep, "value": value}
        if not row:
            del self.data["edits"][rid]

    def set_match(self, match: str, left: str, rights: list[str] | None) -> None:
        decisions = self.data["matches"].setdefault(match, {})
        if rights is None:
            decisions.pop(left, None)          # 交回自動比對
        else:
            decisions[left] = list(rights)

    def set_dismissed(self, issue_key: str, on: bool) -> None:
        keys = set(self.data["dismissed"])
        keys.add(issue_key) if on else keys.discard(issue_key)
        self.data["dismissed"] = sorted(keys)


class MappingStore:
    """使用者在介面補上的對照，跟著 recipe 存在 workspace，下次處理其他檔案也會用到。"""

    def __init__(self, root: Path, recipe_id: str):
        self.path = root / f"{recipe_id}.json"
        self.data = _read(self.path, {})

    def entries(self, table: str) -> dict[str, dict]:
        return self.data.get(table, {})

    def values(self, table: str) -> list[str]:
        """使用者自己加的對應值（recipe 的 values 清單裡沒有的）。"""
        return list(self.data.get("_values", {}).get(table, []))

    def add(self, table: str, raw: str, target: str | None, new_value: bool = False) -> None:
        entries = self.data.setdefault(table, {})
        if target is None:
            entries.pop(key(raw), None)
        else:
            entries[key(raw)] = {"raw": raw, "target": target}
            if new_value:
                extra = self.data.setdefault("_values", {}).setdefault(table, [])
                if target not in extra:
                    extra.append(target)
        self._prune(table)
        with _lock:
            _write(self.path, self.data)

    def _prune(self, table: str) -> None:
        """自己加的對應值沒有任何對照在用時一併移除，清單不會越積越多。"""
        extra = self.data.get("_values", {}).get(table)
        if extra:
            used = {e["target"] for e in self.data.get(table, {}).values()}
            self.data["_values"][table] = [v for v in extra if v in used]
