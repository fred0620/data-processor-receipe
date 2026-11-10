# 維護手冊

目標：新的負責人照著這份做一次，就能獨立修改、測試和發布。先看 [OWNER.md](../OWNER.md) 了解這個工具的定位。

## 1. 第一次接手

只需要安裝 [uv](https://docs.astral.sh/uv/) 和 Git，不用另外裝 Python。

```bash
git clone <GitLab 專案網址> data-processor
cd data-processor
uv sync --project app                      # 建立開發環境（app/.venv，含測試套件）
uv run --project app pytest tests          # 全部通過才算環境正確
bash run.sh                                # 或 Windows 雙擊 run.bat，用使用者的方式開啟
```

接手時請一併確認：

- [ ] OWNER.md 的負責人與備援人已改成自己
- [ ] 有 GitLab 專案的 Maintainer 權限，能建立版本標籤
- [ ] 看過一次 [設計決策](design.md)，特別是「發布、更新與資料夾分工」

## 2. 日常開發

| 要做的事 | 指令 |
|---|---|
| 跑全部測試 | `uv run --project app pytest tests` |
| 只跑一個檔案 | `uv run --project app pytest tests/test_server.py` |
| 用使用者的方式啟動 | `bash run.sh` 或 `run.bat` |
| 改了使用手冊的示意圖 | 改 `scripts/make_manual_figures.py` 後執行它 |
| 改了使用手冊或換版說明後重建 HTML | `uv run --project app python scripts/build_manual.py` |
| 新增套件 | `uv add --project app 套件名稱` |
| 試打包（不含離線套件） | `uv run --project app python scripts/build_release.py` |
| 換版與退回測試 | 包含在 `pytest tests` 裡（`tests/test_release.py`），只在 Windows 上實際執行；沒有 Python 的 Windows 電腦可以直接跑 `powershell -ExecutionPolicy Bypass -File tests\release\test_update.ps1`（加 `-Zip 發布包.zip` 測實際的發布包） |

規則：

- 程式放 `app/`，使用者資料只能寫到 `workspace/`。新的檔案位置一律加在 `app/dataprocessor/paths.py`。
- `app/` 裡不要放任何真實資料，它會整包發給所有人。
- 使用者存在 `workspace` 的檔案（設定、範本等）改格式時，加上版本欄位，並讓新版能讀舊格式。
- 改到核心邏輯時，用自己電腦上的真實樣本跑一次，和上一版的結果比對。真實樣本不進版控。
- 要發布新的資料夾或檔案時，加進 `scripts/build_release.py` 的清單；沒列的不會進發布包。
- 新增套件時，也加進 `__main__.py` 的 doctor 檢查。
- 改到 `app/launcher.ps1`（尤其換版與退回）時，一定要讓換版測試通過。它在 Windows PowerShell 5.1 上用有空白和中文的資料夾，實際跑更新、退回、壞掉的 ZIP、檔案被鎖住，確認 workspace 不會被動到、失敗時能用原本的版本、也不會弄丟可以退回的上一版。測試只用 Windows 內建的 PowerShell，不需要網路、Python 或 uv，沒有外網的公司電腦也能直接跑；建議發版前在自己的電腦上，用要發布的 ZIP 跑一次。推到 GitHub 時會自動在 Windows、macOS、Linux 上跑全部測試（`.github/workflows/tests.yml`）；GitLab 的 runner 是 Linux，這項會顯示略過，所以發版前要自己在 Windows 上跑一次。

## 3. 發布新版

### 版本號怎麼訂

| 改了什麼 | 例子 | 版本 |
|---|---|---|
| 修錯、小調整 | 0.2.0 → 0.2.1 | 第三碼 +1 |
| 新功能，舊資料照樣能用 | 0.2.1 → 0.3.0 | 第二碼 +1 |
| 舊資料要重做，或操作方式大改 | 0.3.0 → 1.0.0 | 第一碼 +1 |

### 步驟

1. 改 `app/pyproject.toml` 的 `version`，然後執行 `uv lock --project app` 讓 `uv.lock` 跟著更新。
2. 在 `CHANGELOG.md` 最上面加一段 `## 版本號 - 日期`，用使用者看得懂的話條列改了什麼。
3. 跑測試，並依 [發版檢查清單](security-checklist.md) 勾選。另外在能連到 pypi.org 的電腦做兩件 CI 做不到的事：
   - 弱點檢查：`python3 scripts/audit.py`（公司鏡像沒有弱點資料庫，所以不放在 CI）
   - 換版測試：在 Windows 電腦執行 `powershell -ExecutionPolicy Bypass -File tests\release\test_update.ps1`（不需要網路；GitLab 的 runner 是 Linux，會顯示略過）
4. 合併到 main 後打標籤：

   ```bash
   git tag v0.2.1
   git push origin v0.2.1
   ```

5. GitLab 會自動跑測試、打包（離線套件逐一比對 uv.lock 的 SHA256），把 ZIP 和 `SHA256SUMS.txt` 上傳到套件庫，並在 **Deploy > Releases** 建立 Release。任何一步失敗都不會發布。
   runner 連不到 pypi.org 時，在 Settings > CI/CD > Variables 設定 `PIP_MIRROR`（公司內部 PyPI 鏡像）；用公司自己的憑證時再加 File 類型的 `CA_BUNDLE`。說明在 `.gitlab-ci.yml` 開頭。
6. 通知同事：到 Releases 頁下載新版 ZIP 和 `SHA256SUMS.txt`，兩個都放進工具資料夾，雙擊 `run.bat`。可以直接把 CHANGELOG 這一段貼給大家，並附上 [換版說明](update-guide.md) 的連結（工具裡也能從使用手冊連過去）。

### 第一次設定（只做一次）

1. **受保護的標籤**（Settings > Repository > Protected tags）：保護 `v*`，只允許 Maintainer 建立。這樣只有負責人能發布。
2. **每月弱點檢查**：每月在自己的電腦跑一次 `python3 scripts/audit.py`。
3. **同事的權限**：同事要能看到專案的 Releases 頁才能下載，通常給 Reporter 權限即可。
4. 公司要用內部映像檔或 PyPI 鏡像時，在 Settings > CI/CD > Variables 設定 `UV_IMAGE`、`UV_DEFAULT_INDEX`。

## 4. 例行維護

| 頻率 | 做什麼 |
|---|---|
| 每月 | 執行 `python3 scripts/audit.py`。有弱點就升級該套件並發布修正版 |
| 每半年 | 升級全部套件與 uv，發一個小版本；順便確認 OWNER.md 還正確、還有人在用 |
| 交接時 | 新負責人照第 1 節做一次，並在備援人陪同下發布一次 |

### 升級套件

```bash
uv lock --project app --upgrade-package 套件名稱       # 只升級一個（處理弱點時）
uv lock --project app --upgrade                       # 全部升級
uv run --project app pytest tests
python3 scripts/audit.py                              # 本機先檢查一次弱點
```

負責讀取外部檔案（PDF、Excel、圖片）的套件最需要跟上更新。

### 升級 uv

1. 到 uv 的 GitHub Release 頁，找新版本的 `.sha256` 檔。
2. 改 `app/launcher.ps1` 的 `$UvVersion` 和 `$UvSha256`，以及 `app/launcher.sh` 的 `UV_VERSION` 和各平台的 `SHA`。
3. 改 `.gitlab-ci.yml` 的 `UV_IMAGE` 版本。
4. 刪掉本機的 `runtime/` 後用 `run.bat` 啟動一次，確認能下載並通過驗證。

### 升級 Python

改 `app/.python-version`，執行 `uv lock --project app`，跑測試，再改 `.gitlab-ci.yml` 的映像檔版本。使用者更新後會自動建立新的環境。

## 5. 使用者回報問題時

請對方提供：

- 版本號（畫面左上角，或 `run.bat version`）
- `workspace/logs/app.log`（只有代號和數量，不含檔名與資料內容）
- 可以的話，一份能重現問題、已去識別化的範例

先請對方執行 `run.bat rollback`，確認是不是新版造成的。環境壞掉時，刪除 `runtime` 資料夾重新啟動即可，workspace 不受影響。

## 6. 緊急處理

### 發現嚴重錯誤

1. 通知所有使用者先暫停使用，改回人工作業。
2. 修正後照第 3 節發布，通知大家更新。
3. 要回到上一版的行為時，把有問題的修改 revert，用新的版本號（例如 0.2.2）發布。安裝程式只會往新版更新。

## 7. 資料夾與檔案一覽

| 位置 | 用途 | 進版控 | 進發布包 |
|---|---|---|---|
| `run.bat`、`run.sh` | 使用者入口 | 是 | 是 |
| `app/` | 程式、啟動程式、起始資料、使用手冊 | 是 | 是（逐一列在 `scripts/build_release.py`） |
| `app/wheels/` | Windows 離線套件 | 否 | 是（CI 打包時下載） |
| `workspace/` | 使用者資料，第一次啟動時建立 | 否 | 否 |
| `runtime/` | uv、Python、套件 | 否 | 否 |
| `app.old/` | 使用者電腦上的上一版 | 否 | 否 |
| `docs/`、`scripts/`、`tests/` | 開發用 | 是 | 否 |
| `dist/` | 打包產物 | 否 | — |
