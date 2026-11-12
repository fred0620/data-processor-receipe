import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "app"), str(ROOT / "scripts")]

UI_DIR = Path(__file__).resolve().parent / "ui"


def pytest_addoption(parser):
    parser.addoption("--ui", action="store_true", default=False,
                     help="執行 tests/ui 的介面測試（需要 playwright 與 Chromium，不在 CI 跑）")


def pytest_ignore_collect(collection_path, config):
    """介面測試只在明確加上 --ui 時執行：修改介面後由開發者（或 Claude）手動跑，CI 不跑。"""
    if config.getoption("--ui"):
        return None
    path = Path(collection_path)
    if path == UI_DIR or UI_DIR in path.parents:
        return True
    return None
