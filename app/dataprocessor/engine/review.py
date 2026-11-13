"""人工決定的存放：修改的值、指定的配對、確認過的警示、補上的對照。

人工決定跟 recipe 分開存，重新執行時再套上去；recipe 或資料改了，原本的決定不會消失，
對不上時會標記出來。修改的值一律保留原值。
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
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
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=1)
        _replace(temp, path)  # 寫完才換掉，避免當機時留下寫到一半的檔案
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def _replace(source: str, target: Path, attempts: int = 20) -> None:
    """Windows 上，防毒或搜尋索引剛好在讀這個檔案時，換檔會被拒絕（WinError 5）。
    稍等再試，約 2 秒內都失敗才放棄。Mac 與 Linux 不會發生。"""
    for attempt in range(attempts):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.1)


class ReviewStore:
    """同一份 recipe 加同一份 workbook（以內容雜湊判斷）共用一組人工決定。"""

    def __init__(self, root: Path, recipe_id: str, workbook_hash: str):
        self.path = root / recipe_id / f"{workbook_hash}.json"
        self.data = self._load()

    def _load(self) -> dict:
        data = _read(self.path, {})
        data.setdefault("edits", {})      # rid → 欄位 → {original, value}
        data.setdefault("matches", {})    # 配對名稱 → 左表 rid → 右表 rid 清單（空清單代表確定沒有配對）
        data.setdefault("dismissed", [])  # 確認過、不用再提醒的警示
        return data

    def save(self) -> None:
        with _lock:
            _write(self.path, self.data)

    def update(self, change) -> None:
        """改人工決定一律走這裡：在鎖裡重新讀檔、套上這次的改變、立刻寫回。
        同一個檔案開在兩個分頁（兩次執行）時，各自手上的舊資料不會互相蓋掉對方的決定。"""
        with _lock:
            self.data = self._load()
            change(self)
            _write(self.path, self.data)

    def set_flagged(self, name: str, rids: list[str]) -> None:
        """執行時記下被驗證規則標記過的列。只改這一項並重新讀檔，不會用手上的舊資料蓋掉別的分頁剛做的決定。"""
        with _lock:
            fresh = self._load()
            fresh.setdefault("flagged", {})[name] = rids
            _write(self.path, fresh)

    @property
    def backup(self) -> Path:
        return self.path.with_name(self.path.stem + ".before-reset.json")

    def count(self) -> int:
        """人工決定的數量：修改的格子、指定的配對、確認過的警示。"""
        return (sum(len(cells) for cells in self.data["edits"].values())
                + sum(len(rows) for rows in self.data["matches"].values()) + len(self.data["dismissed"]))

    def reset(self) -> None:
        """清掉這個檔案的人工決定，從頭再檢查一次。清之前先留一份，可以復原。
        補上的對照表跟著 recipe，其他檔案也在用，不在這裡清。"""
        with _lock:
            self.data = self._load()
            if self.count():   # 沒有決定可清時不碰備份，免得把上一次能復原的內容蓋成空的
                _write(self.backup, self.data)
            self.data = {"edits": {}, "matches": {}, "dismissed": []}
            _write(self.path, self.data)

    def restore(self) -> bool:
        """回到重設之前。只能復原最近一次重設。重設之後又做的決定會保留，同一格兩邊都有時以新的為準。"""
        with _lock:
            saved = _read(self.backup, {})
            if not saved:
                return False
            current = self._load()
            merged = {"edits": {}, "matches": {}, "dismissed": []}
            for source in (saved, current):
                for rid, cells in (source.get("edits") or {}).items():
                    merged["edits"].setdefault(rid, {}).update(cells)
                for name, rows in (source.get("matches") or {}).items():
                    merged["matches"].setdefault(name, {}).update(rows)
            merged["dismissed"] = sorted({*(saved.get("dismissed") or []), *current["dismissed"]})
            merged["flagged"] = {**(saved.get("flagged") or {}), **(current.get("flagged") or {})}
            self.data = merged
            _write(self.path, self.data)
            self.backup.unlink(missing_ok=True)
            return True

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
        with _lock:   # 重新讀檔再改，兩個請求同時補對照時不會只留下一筆
            self.data = _read(self.path, {})
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
            _write(self.path, self.data)

    def _prune(self, table: str) -> None:
        """自己加的對應值沒有任何對照在用時一併移除，清單不會越積越多。"""
        extra = self.data.get("_values", {}).get(table)
        if extra:
            used = {e["target"] for e in self.data.get(table, {}).values()}
            self.data["_values"][table] = [v for v in extra if v in used]
