# 給 Claude 的工作規則（data-processor）

專案說明見 `README.md`、`docs/design.md`、`docs/maintain.md`。與使用者溝通用繁體中文（台灣），不要用破折號。

## 修改介面之後一定要跑介面測試

只要改到下面任何一項，提交前都要執行介面測試，全部通過、並親自看過截圖才算完成：

- `app/dataprocessor/web/`（app.js、style.css、index.html）
- `app/dataprocessor/server.py` 的 API 或回傳欄位
- 會影響畫面的結果欄位（pipeline 的 stages、rows、issues、matches 等）

```bash
uv run --project app --with playwright pytest tests/ui --ui
```

- 第一次在新環境要先下載 Chromium：`uv run --project app --with playwright python -m playwright install chromium`。
  已經有 Chrome 時改設 `DP_CHROME=Chrome 執行檔路徑`。
- 跑完用 Read 看 `tests/ui/screens/` 的截圖，確認版面沒有亂掉、顏色與文字正確。
- 新增或改變介面功能時，在 `tests/ui/` 補上對應的測試：用真的瀏覽器點按鈕操作，不要直接呼叫 JavaScript 函式代替使用者操作。
  確認新測試在功能拿掉時會失敗，避免測試量不到東西。
- 介面測試不在 CI 跑（需要下載瀏覽器，公司的 GitLab 不能連外網），一般的 `pytest tests` 也不會收集它。

## 其他固定要做的

- 一般測試：`uv run --project app pytest tests`。
- 改到 `app/launcher.ps1`、`run.bat`：Windows 上的換版測試見 `docs/maintain.md`。
- 改了使用手冊（`docs/user-guide.md`）：`uv run --project app python scripts/build_manual.py`。
- 使用者看得到的改變寫進 `CHANGELOG.md`；設計決定寫進 `docs/design.md`。
