"""DuckDB 沙箱。recipe 的 SQL 只在這裡執行。

資料先由程式載入，接著關閉外部存取並鎖住設定：之後的 SQL 讀寫不到任何檔案、
不能連網、不能安裝或載入擴充套件，也不能把設定改回來。
"""
from __future__ import annotations

import csv
import datetime as dt
import shutil
import tempfile
import threading
from pathlib import Path

import duckdb

from .recipe import RecipeError, quote

SQL_TIMEOUT_SECONDS = 120
SQL_TYPES = {"text": "VARCHAR", "number": "DOUBLE", "integer": "BIGINT", "date": "DATE"}

_FULL = "".join(chr(c) for c in range(0xFF01, 0xFF5F)) + "　"
_HALF = "".join(chr(c) for c in range(0x21, 0x7F)) + " "
MACROS = [
    # 和 textnorm.key 相同的寬鬆比對鍵：全半形相同、不分大小寫、忽略空白與標點
    f"CREATE MACRO dp_key(x) AS lower(regexp_replace(translate(CAST(x AS VARCHAR), '{_FULL.replace(chr(39), chr(39) * 2)}', "
    f"'{_HALF.replace(chr(39), chr(39) * 2)}'), '[^\\p{{L}}\\p{{N}}]+', '', 'g'))",
    # 只留數字，比對單號常用
    "CREATE MACRO dp_digits(x) AS regexp_replace(CAST(x AS VARCHAR), '[^0-9]+', '', 'g')",
]


class Sandbox:
    def __init__(self, scratch: Path):
        self.scratch = scratch
        self.con = duckdb.connect(config={"threads": 2, "memory_limit": "2GB",
                                          "autoinstall_known_extensions": False,
                                          "autoload_known_extensions": False})
        self.locked = False
        for macro in MACROS:
            self.con.execute(macro)

    def load(self, table: str, columns: dict[str, str], rows: list[dict]) -> None:
        """建立資料表並載入資料。只能在 lock() 之前呼叫。columns 是 欄位 → SQL 型別。"""
        if self.locked:
            raise RuntimeError("沙箱已鎖定，不能再載入資料")
        self.scratch.mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(dir=self.scratch))
        try:
            path = folder / "data.csv"
            names = list(columns)
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle, quoting=csv.QUOTE_MINIMAL)
                writer.writerow(names)
                for row in rows:
                    writer.writerow([_csv_value(row.get(n)) for n in names])
            spec = ", ".join(f"{quote(n)}: '{t}'" for n, t in columns.items())
            self.con.execute(
                f"CREATE TABLE {quote(table)} AS SELECT * FROM read_csv(?, header = true, quote = '\"', "
                f"escape = '\"', nullstr = '', columns = {{{spec}}}, auto_detect = false)", [str(path)])
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def lock(self) -> None:
        self.con.execute("SET enable_external_access = false")
        self.con.execute("SET lock_configuration = true")
        self.locked = True

    def query(self, sql: str, where: str, params: list | None = None) -> list[tuple]:
        result = self._run(sql, where, params)
        return result.fetchall() if result is not None else []

    def execute(self, sql: str, where: str, params: list | None = None) -> None:
        self._run(sql, where, params)

    def columns(self, table: str) -> list[str]:
        return [row[0] for row in self.con.execute(f"DESCRIBE {quote(table)}").fetchall()]

    def count(self, table: str) -> int:
        return self.con.execute(f"SELECT count(*) FROM {quote(table)}").fetchone()[0]

    def insert_values(self, table: str, rows: list[tuple]) -> None:
        """少量的系統資料（例如已決定的配對）用分批 INSERT，不經過檔案。"""
        if not rows:
            return
        width = len(rows[0])
        placeholder = "(" + ",".join(["?"] * width) + ")"
        for start in range(0, len(rows), 500):
            chunk = rows[start:start + 500]
            self.con.execute(f"INSERT INTO {quote(table)} VALUES " + ",".join([placeholder] * len(chunk)),
                             [v for row in chunk for v in row])

    def _run(self, sql: str, where: str, params: list | None):
        if not self.locked:
            raise RuntimeError("執行 recipe 的 SQL 前要先 lock()")
        timer = threading.Timer(SQL_TIMEOUT_SECONDS, self.con.interrupt)
        timer.start()
        try:
            return self.con.execute(sql, params or [])
        except duckdb.InterruptException:
            raise RecipeError([f"{where}：執行超過 {SQL_TIMEOUT_SECONDS} 秒被中止，"
                               "通常是比對條件讓兩張表每一列都互相比較，請先用等值條件縮小範圍"]) from None
        except duckdb.Error as exc:
            message = str(exc).splitlines()[0][:400]
            raise RecipeError([f"{where}：{message}"]) from None
        finally:
            timer.cancel()

    def close(self) -> None:
        self.con.close()


def _csv_value(value):
    if value is None:
        return ""
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return repr(value) if isinstance(value, float) else str(value)
    return str(value)
