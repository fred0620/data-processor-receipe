# 資料處理器

把 Excel 裡的原始資料依照 recipe 整理成可以交出去的資料表：篩選、清理、多種方式配對、對照代碼、計算與驗證，有疑慮的地方標記出來，在畫面上修正後下載。recipe 由使用者和自己的 AI 依照 [recipe 規格](app/recipe-spec.md) 寫成，不含程式碼。全部在本機執行，資料不會離開這台電腦。

| 你是 | 請看 |
|---|---|
| 使用者 | [使用手冊](docs/user-guide.md)（工具右上角也能開啟）、[換版說明](docs/update-guide.md) |
| 負責人、接手的人 | [工具卡](OWNER.md) → [維護手冊](docs/maintain.md) → [設計決策](docs/design.md) |
| 要發布新版 | [維護手冊的發布步驟](docs/maintain.md) 與 [發版檢查清單](docs/security-checklist.md) |

## 使用

不需要先安裝 Python。從 GitLab 的 Releases 頁下載 `data-processor-版本.zip`，解壓後雙擊 `run.bat`（macOS / Linux 執行 `bash run.sh`）。第一次會自動準備 uv 和 Python，約 1 到 3 分鐘。

更新時，把新版 ZIP 直接放進工具資料夾，雙擊 `run.bat` 就會詢問要不要安裝。更新只換掉 `app` 和 `run.bat`，`workspace` 裡的資料不受影響；新版有問題時執行 `run.bat rollback` 就能退回。

```text
data-processor/
  run.bat       入口
  app/          程式，每次更新整包換掉，不要放自己的檔案
  workspace/    使用者資料（第一次啟動時建立，更新不會動）
  runtime/      uv、Python 和套件（自動建立，刪掉會重建）
```

## 專案結構

```text
run.bat, run.sh          使用者入口（只有一行，轉給 app/launcher）
app/                     發布時整包給使用者的內容
  launcher.ps1           Windows 啟動程式：環境、安裝新版、回滾
  launcher.sh            macOS / Linux 啟動程式（開發用）
  pyproject.toml         套件與版本號（版本只寫在這裡）
  uv.lock                鎖定的套件版本
  dataprocessor/
    paths.py             所有檔案位置
    logs.py              本機日誌（不記資料內容）
    server.py            本機網頁後端（已含安全檢查與自動結束）
    engine/              recipe 引擎
      recipe.py          讀取與檢查 recipe，問題一次列出
      workbook.py        讀 Excel、依別名找表頭
      textnorm.py        文字、數字、日期的整理規則
      sandbox.py         DuckDB 沙箱（不能讀檔、連網、裝擴充套件）
      pipeline.py        Load → Gate → Normalize → Match → Transform → Validate → Mapping → Export
      review.py          人工修改、指定配對、確認的警示、補上的對照
      export.py          輸出 Excel
    web/                 前端，無外部相依
  examples/workspace/    第一次啟動時複製到 workspace 的起始資料（範例 recipe 與範例資料）
  recipe-spec.md         給 AI 讀的 recipe 規格（工具裡可以一鍵複製）
  user-guide.html、update-guide.html   由 docs/ 產生
docs/                    使用手冊、換版說明、設計決策、維護手冊、發版檢查清單
scripts/                 打包發布、重建手冊與示意圖、產生範例資料
tests/
.gitlab-ci.yml           測試、弱點檢查、打包與 Release
OWNER.md                 工具卡
CHANGELOG.md             每一版改了什麼（發布時必填）
```

## 開發

```bash
uv sync --project app                                 # 含開發用套件
uv run --project app pytest tests
bash run.sh                                           # 用使用者的方式啟動
uv run --project app python scripts/build_release.py  # 打包到 dist/
```

詳細流程見 [維護手冊](docs/maintain.md)。
