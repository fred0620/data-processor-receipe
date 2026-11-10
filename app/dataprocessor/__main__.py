"""指令列入口。

    python -m dataprocessor                開啟網頁工具
    python -m dataprocessor doctor         檢查環境
    python -m dataprocessor --version      顯示版本

要加批次指令（給排程或熟悉指令的人用），在 main() 加 subparser，
並記得指令列模式不能停下來等使用者輸入。
"""
from __future__ import annotations

import argparse
import platform
import sys


def _command_doctor(_args) -> int:
    from . import __version__, paths

    print(f"資料處理器 {__version__}，Python {platform.python_version()}")
    print(f"資料位置：{paths.WORKSPACE}")
    healthy = True
    for name in ("flask",):  # 新增套件時加在這裡
        try:
            __import__(name)
            print(f"  OK   {name}")
        except ImportError as exc:
            healthy = False
            print(f"  缺少 {name}：{exc}")
    return 0 if healthy else 1


def main() -> int:
    from . import __version__

    parser = argparse.ArgumentParser(prog="dataprocessor", description="資料處理器")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("doctor", help="檢查環境")
    args = parser.parse_args()
    if args.command == "doctor":
        return _command_doctor(args)
    from .server import serve

    serve(args.port, not args.no_browser)
    return 0


if __name__ == "__main__":
    sys.exit(main())
