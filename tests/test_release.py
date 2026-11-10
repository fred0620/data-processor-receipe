"""發布包與換版。

發布包的內容在每個作業系統都檢查。換版、退回實際上是 Windows 的 run.bat 加 PowerShell 5.1 在做，
檔案鎖住、cmd 的結束代碼、中文路徑這些行為只有 Windows 才有，所以只在 Windows 上實際執行
tests/release/test_update.ps1；Mac、Linux 會標示為略過，不會假裝通過。
都不需要網路。
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import build_release

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def release(tmp_path_factory) -> Path:
    return build_release.build(tmp_path_factory.mktemp("dist"), wheels=False)


def test_release_contains_only_the_app(release):
    version = build_release.read_version()
    root = f"data-processor-{version}/"
    with zipfile.ZipFile(release) as bundle:
        names = bundle.namelist()
        assert release.name == f"data-processor-{version}.zip"
        assert all(n.startswith(root) for n in names)
        top = {n[len(root):].split("/")[0] for n in names}
        assert top == {"run.bat", "run.sh", "app"}             # 沒有 workspace、runtime、測試或資料
        assert not any("__pycache__" in n or "/.venv/" in n for n in names)
        toml = bundle.read(root + "app/pyproject.toml").decode()
        assert re.search(rf'^version\s*=\s*"{re.escape(version)}"', toml, re.M)


def test_windows_files_are_readable_by_powershell_5(release):
    root = f"data-processor-{build_release.read_version()}/"
    with zipfile.ZipFile(release) as bundle:
        launcher = bundle.read(root + "app/launcher.ps1")
        bat = bundle.read(root + "run.bat")
        sh = bundle.read(root + "run.sh")
    assert launcher.startswith(b"\xef\xbb\xbf")                # 沒有 BOM，PowerShell 5.1 讀不懂中文
    assert b"\r\n" in launcher and b"\n" not in launcher.replace(b"\r\n", b"")
    lines = bat.rstrip(b"\r\n").split(b"\r\n")
    assert len(lines) == 1                                     # 換版時會覆蓋 run.bat，一行才不會讀到一半
    assert lines[0].endswith(b"call exit /b %%errorlevel%%")   # 要把結束代碼傳出去
    assert b"\r" not in sh


@pytest.mark.skipif(sys.platform != "win32", reason="換版與退回只在 Windows 上執行（run.bat 加 PowerShell 5.1）")
def test_update_and_rollback_on_windows(release, tmp_path):
    shell = shutil.which("powershell") or "powershell"        # Windows 內建的 5.1，不是 pwsh
    done = subprocess.run([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                           str(ROOT / "tests" / "release" / "test_update.ps1"), "-Zip", str(release),
                           "-Work", str(tmp_path / "work")],
                          capture_output=True, timeout=600)
    output = (done.stdout + done.stderr).decode("utf-8", "replace")
    assert done.returncode == 0, output
