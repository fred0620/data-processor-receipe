"""所有檔案位置集中在這裡。新增任何要讀寫的位置，都加在這個檔案。

發布後的資料夾分成三塊，更新時只換 app/ 和 run.bat：

    data-processor/
      run.bat      使用者入口
      app/         程式（每次更新整包換掉，不要放自己的檔案）
      workspace/   使用者資料（更新不會動）
      runtime/     uv、Python 與套件（自動建立，可隨時刪掉重建）

啟動程式會設定 APP_HOME 指向最外層資料夾；沒有設定時（例如開發時直接跑 pytest），
就用 app/ 的上一層。
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
HOME = Path(os.environ.get("APP_HOME") or APP.parent).resolve()

WORKSPACE = HOME / "workspace"
OUTPUT = WORKSPACE / "output"        # 匯出給使用者的檔案
LOGS = WORKSPACE / "logs"            # 操作與錯誤紀錄，不含資料內容
UPLOADS = WORKSPACE / "uploads"      # 暫存，結束時清除

EXAMPLES = APP / "examples"
MANUAL = APP / "user-guide.html"
GUIDES = {"user-guide.html", "update-guide.html"}  # 工具裡可以開啟的說明文件


def prepare() -> None:
    """建立 workspace。第一次建立時，把 app/examples/workspace 的內容放進去當起始資料；
    之後使用者刪掉的東西不會再出現。"""
    first_time = not WORKSPACE.exists()
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    if first_time:
        seed = EXAMPLES / "workspace"
        if seed.is_dir():
            shutil.copytree(seed, WORKSPACE, dirs_exist_ok=True)
    for folder in (OUTPUT, LOGS):
        folder.mkdir(parents=True, exist_ok=True)
