"""換版測試用：打包目前版本，再做出「下一版」與幾個壞掉的 ZIP。

    uv run --project app python tests/release/make_versions.py <輸出資料夾>

輸出 versions.json，給 test_update.ps1 讀。只在測試用，不會進到發布包。
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import build_release  # noqa: E402


def bump(version: str, step: int) -> str:
    major, minor, patch = (int(x) for x in version.split("."))
    return f"{major}.{minor}.{patch + step}"


def repack(base: Path, target: Path, content_version: str, *, marker: bool = True, keep_app: bool = True) -> None:
    """把 base 的內容換成另一個版本號，重新包成 target。"""
    old_root = base.stem
    new_root = f"{build_release.NAME}-{content_version}"
    with zipfile.ZipFile(base) as source, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as out:
        for info in source.infolist():
            name = info.filename.replace(old_root, new_root, 1)
            if not keep_app and "/app/" in name:
                continue
            data = source.read(info)
            if name.endswith("/app/pyproject.toml"):
                data = re.sub(rb'^version\s*=\s*"[^"]+"', f'version = "{content_version}"'.encode(), data,
                              count=1, flags=re.MULTILINE)
            out.writestr(name, data)
        if marker and keep_app:
            out.writestr(f"{new_root}/app/version-marker.txt", content_version)


def main() -> None:
    out = Path(sys.argv[1]).resolve()
    base = build_release.build(out / "base", wheels=False)
    current = build_release.read_version()
    nxt, after, mismatch, broken = (bump(current, n) for n in (1, 2, 3, 4))
    zips = out / "zips"
    zips.mkdir(parents=True, exist_ok=True)
    name = build_release.NAME
    repack(base, zips / f"{name}-{nxt}.zip", nxt)                         # 正常的下一版
    repack(base, zips / f"{name}-{after}.zip", after)                     # 再下一版（測試更新失敗後重試）
    repack(base, zips / f"{name}-{mismatch}.zip", nxt)                   # 檔名和內容版本不符
    repack(base, zips / f"{name}-{broken}.zip", broken, keep_app=False)  # 沒有 app 資料夾
    repack(base, zips / f"{name}-0.0.1.zip", "0.0.1")                    # 比目前舊
    info = {"base": str(base), "current": current, "next": nxt, "after": after,
            "mismatch": mismatch, "broken": broken, "zips": str(zips)}
    (out / "versions.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
