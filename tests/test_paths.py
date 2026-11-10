"""workspace 的建立與版本號。"""
import dataprocessor
from dataprocessor import paths


def _point_to(monkeypatch, home):
    workspace = home / "workspace"
    monkeypatch.setattr(paths, "HOME", home)
    monkeypatch.setattr(paths, "WORKSPACE", workspace)
    monkeypatch.setattr(paths, "OUTPUT", workspace / "output")
    monkeypatch.setattr(paths, "LOGS", workspace / "logs")


def test_first_run_seeds_examples_once(tmp_path, monkeypatch):
    _point_to(monkeypatch, tmp_path)
    paths.prepare()
    assert (paths.WORKSPACE / "README.txt").exists()
    assert paths.OUTPUT.is_dir() and paths.LOGS.is_dir()
    (paths.WORKSPACE / "README.txt").unlink()
    paths.prepare()  # 使用者刪掉的起始資料不會再出現
    assert not (paths.WORKSPACE / "README.txt").exists()


def test_version_comes_from_pyproject():
    text = (paths.APP / "pyproject.toml").read_text(encoding="utf-8")
    assert f'version = "{dataprocessor.__version__}"' in text
