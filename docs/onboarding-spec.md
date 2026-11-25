# data-processor Onboarding Journey 開發規格書 v1（給 Antigravity）

資料處理器（data-processor）的新手導覽、進階功能入口、實地練習、新功能導覽與使用手冊改版。依照《Onboarding Journey 設計手冊》（pdf-mapper 0.4.0 整理）套用到本專案，並依本專案現況調整。

開工前先讀：`CLAUDE.md`（工作規則與介面測試，對 Antigravity 一樣適用）、`docs/design.md`（設計決策）、`app/recipe-spec.md`（recipe 規格）、`docs/user-guide.md`（現行手冊）。本規格和這些文件衝突時，以本規格為準，並把新決策寫回 `docs/design.md`。

---

## 0. 給實作者的工作方式

### 0.1 分批交付

依第 12 節分成 8 批，每批一個 PR（或一組 commit），每批結束時：

1. 先寫會失敗的測試，再實作到通過。
2. 一般測試：`uv run --project app pytest tests`。
3. 介面測試：`uv run --project app --with playwright pytest tests/ui --ui`，並**逐張看過** `tests/ui/screens/` 的截圖。
4. 回報限制在 20 行內：做了什麼、測試結果、和規格不同的地方與理由、待確認事項。

### 0.2 不可違反的限制

- 本機離線執行，只有 uv 與 Python。前端純 Vanilla JS/CSS，不加 npm、CDN、外部字型或新的 Python 相依。
- CSP：不用 `eval`、inline script、inline event handler。新 JS 檔用 `<script src>` 載入。
- 所有資料用 `textContent` 放進畫面，不用 `innerHTML`。
- 樣式只用 `style.css` `:root` 既有的 Stageshow token，不寫死色碼；缺 token 就在 `:root` 補，並在旁邊註記（`:root` 要和 pdf-mapper 一致，新增的 token 在回報時列出來，之後同步到 pdf-mapper）。字級不低於 12.5px。
- 沿用既有安全檢查：127.0.0.1、Host、`Sec-Fetch-Site`、Origin；日誌不記檔名與資料內容。
- 文案：台灣繁體中文、短句、不用破折號、不寫「歡迎」「恭喜」「太棒了」「請您」。按鈕叫什麼，提示就寫什麼（以 `app.js` 裡實際的文字為準，寫進提示前先 grep 確認）。

### 0.3 名詞

| 名詞 | 意思 |
|---|---|
| 關卡 | 新手導覽的一條流程，由多個步驟組成。本專案有兩條：「核對一份資料」與「放入 recipe」 |
| 範例模式 | 用 `app/` 內建的範例資料與範例 recipe 執行，所有結果與決定都不寫進使用者的正式資料 |
| 練習 | 進階功能的實地練習（lab）：前置做好，只練一個 recipe 設定，最後用實際執行結果驗證 |
| Spotlight | 統一的導覽引擎；關卡步驟、進階說明卡、練習步驟、新功能都是它的資料 |

---

## 1. 目標與本專案的特性

### 1.1 三個目標

1. **新手能用起來**：第一次打開就有清楚入口，用範例資料邊做邊學，走完會「執行、看卡片、確認、修改、補對照、選配對、回原始資料、下載」這條核對流程，也知道 recipe 怎麼放進來。
2. **進階功能找得到、學得會**：關掉導覽後仍有固定入口；寫 recipe 的進階設定（篩選、對照表、比對方式、取值、驗證）都有實地練習，最後用實際執行結果確認做對。
3. **每次更新知道多了什麼**：升級後「說明」按鈕出現小點，點開逐項看新功能在哪裡。

### 1.2 和 pdf-mapper 不同的地方（設計時要注意）

| pdf-mapper | data-processor | 對設計的影響 |
|---|---|---|
| 使用者在畫布上框選、建立範本 | 使用者不寫程式、不讀 YAML，recipe 由 AI 依規格寫；工具負責「確認說明」與「檢查修正」 | 「建立類」的新手關卡是「放入 recipe」：複製規格、貼回、看問題、看說明、儲存，而不是在工具裡逐欄設定 |
| 進階設定在右欄表單 | 進階設定都在 recipe 裡 | 實地練習的操作是「改 recipe 的一小段」，用練習專用的片段編輯器加試算，不是開表單 |
| 畫布上的虛線靶框 | 沒有畫布；要指的是表格的列、格子、卡片 | 「疊在內容上的指示」改成結果表與原始表上的深色虛線外框 |
| 主要互動在主畫面 | 新增 recipe 在 `<dialog>`（showModal，位於 top layer） | 導覽元件在對話框開啟時要畫進對話框裡，否則會被蓋住（見 5.6） |
| 人工決定存在範本 | 人工決定存在 `workspace/reviews`、`workspace/mappings` | 範例與練習一律改用暫存的決定與對照，不寫進正式資料夾（見 7.3） |

---

## 2. 核心原則（照設計手冊，摘要）

- 少看字、直接做：一次只講現在這 1 步，1 句行動、1 行提醒。
- 指出位置，不描述位置：浮標指按鈕，深色虛線框指表格上的列或格子。
- 工具負責教，手冊負責查：手冊不重寫導覽步驟。
- 知道在哪不等於會用：寫 recipe 的進階功能都有實地練習。
- 驗證看實際結果：完成條件綁真實狀態（`state.result`、issues、matches、mappings），練習最後跑真的 `engine.run` 比對預期值。
- 同時只有一個強調點：浮標、內容虛線框、外框三者擇一。
- 不遮擋工作區：引導元件放邊緣；疊在內容上的一律 `pointer-events: none`。
- 一切可跳過、可回頭、可重開；關掉後進度保留，從「說明 ▾」繼續。
- 不汙染正式資料：範例與練習的 recipe、決定、對照、匯出都標記並可清掉。
- 動態要有原因：換步驟時提醒一次，之後靜止。

---

## 3. 資訊架構與版面

### 3.1 三層入口

```
第 1 層 新手（主動出現）     起點歡迎畫面 → 關卡（#guideBar + #missionStrip）
第 2 層 進階（找得到）        頂列「說明 ▾」／ recipe 對話框與分頁旁的 ? ／ 完成畫面
第 3 層 新功能（升級時）      「說明」按鈕上的小點 → 新功能小卡 → 逐項導覽
```

### 3.2 版面位置

```
┌ header.bar  ‹  資料處理器 v0.2.0   [runStatus]                     說明 ▾● ┐
├──────────┬────────────────────────────────────────────┬──────────────┤
│ 左欄      │ #guideBar        進度列（一行，38px）          │ #drawer      │
│ Recipe    │ #missionStrip    指令條（52～64px）            │ 單列細節      │
│ 資料檔    ├────────────────────────────────────────────┤ 或 練習面板    │
│ 執行      │ #empty（歡迎畫面）或 #result                  │              │
│           │   result-head / pipeline 卡片 / tabs / 表格    │              │
└──────────┴────────────────────────────────────────────┴──────────────┘
```

- `#guideBar` 與 `#missionStrip` 只占中間 `.work` 欄，放在 `#empty`／`#result` 之前，不跨左欄與細節。
- 「說明 ▾」取代頂列現在的 `a.manual-link`（手冊連結移進選單）。
- 建議視窗寬度為 1000px 以上；寬度低於 900px 時自動收合左欄（不覆寫使用者偏好），指令條改為兩行、歡迎卡撐滿中間欄，確保所有按鈕可點擊。

---

## 4. 第 1 層：新手

### 4.1 起點歡迎畫面（取代現在的 `#empty`）

沒有結果（`!state.result`）時顯示：

```
┌──────────────────────────────────────────────┐
│  選一個方式開始                                 │  14px / 600 text-strong
│                                              │
│  ┌──────────────────────────────────────┐    │
│  │ 用範例資料邊做邊學              約 5 分鐘 │    │  主要入口，surface 卡片 + accent 細框
│  │ 發票對報關單，練習檢查、修正與下載         │    │
│  └──────────────────────────────────────┘    │
│  練習放入 recipe      用自己的資料開始           │  次要：ghost 按鈕並排
│                                              │
│  左邊選好 recipe、放入 Excel，按「執行」。       │  12.5px text
└──────────────────────────────────────────────┘
```

- 主要入口：開始關卡 A「核對一份資料」。
- 「練習放入 recipe」：開始關卡 B。
- 「用自己的資料開始」：浮標指左欄「資料檔」的拖放區，不開導覽。
- 已關閉導覽（`dismissed`）的使用者仍看到這三個入口，但主要入口降為 ghost 樣式。
- 入口卡寬度上限 420px，置於中間欄偏上，文字靠左。左欄拖放照常可用。

**重開導覽時已有工作**：目前有結果或已放入檔案時，從任何入口開始關卡 A 先開浮動卡：

```
要用範例資料開始嗎？
目前的結果會先收起來，你做的修改都已自動保存，
走完導覽按「回到我的工作」會原樣接回。
[ 用範例資料開始 ]   取消
```

本專案的人工決定本來就自動保存，所以不提供「在目前資料上繼續導覽」（關卡步驟綁定範例資料的特定列）。

### 4.2 關卡 A「核對一份資料」（10 步，v2 起）

用範例 recipe「發票對報關單（範例）」與範例 workbook（見 7.1）。範例資料會產生 7 列需檢查（v2 起），關卡挑其中 5 種情況教，並要求把配對與剩下的列做完才下載（見 onboarding-v2-spec.md）。

| 步 | 標題 | 行動句（≤ 22 字） | 提醒（≤ 30 字） | 強調 | 完成條件 |
|---|---|---|---|---|---|
| 1 | 執行 | 按「執行」處理範例資料 | 10 張發票要對 7 張報關單 | 浮標指 `#runButton` | `state.result?.demo === true` |
| 2 | 看流程卡片 | 點橘色的「Match」卡片看摘要 | 提醒行換成三色圖例（4.4） | 外框 `[data-guide="stage-match"]` | `guide.sawStage`（點開任一張橘色卡片時設為 true） |
| 3 | 看懂再確認 | 子步驟，見下 | | | INV-1003 的驗證警示已由使用者確認（不是修改造成的） |
| 4 | 修改讀不懂的值 | 把「約 300」改成 300，按 Enter | 原值會保留，按「還原」可以改回 | 內容虛線框指 INV-1006 的金額欄位 | INV-1006 的「金額」為 300，且是人工修改 |
| 5 | 補對照 | 子步驟，見下 | | | 對照 `ship_mode` 的「陸運」補到一個**新增**的值 |
| 6 | 選配對候選 | 選申報日期較近的 AA15A0005 | 兩筆品名金額都一樣，用日期判斷 | 外框指 AA15A0005 那張候選卡的「選這筆」 | `inv_decl` 中 INV-1009 人工指定為 AA15A0005 |
| 7 | 回原始資料找答案 | 子步驟，見下 | | | INV-1008 的 `inv_decl` 為「確認沒有」，且 `guide.sawSource` |
| 8 | 下載 | 按右上角「下載 Excel」 | 檔名會加「示範_」，和正式檔案分開 | 浮標指 `#exportButton` | `guide.demoExported` |

**子步驟**（指令條顯示「3　1/2」）：

| 步 | 子步驟 | 行動句 | 提醒 | 強調 | 子完成條件 |
|---|---|---|---|---|---|
| 3 | 1/2 | 按警示上的「怎麼判斷的」 | 規則和這一列用到的值都會列出 | 浮標指 INV-1003 警示的「怎麼判斷的」 | `guide.sawTrace`（展開了 INV-1003 驗證規則的處理過程） |
| 3 | 2/2 | 按「確認無誤，下一筆」 | 範例當作已向業務確認，差額沒問題 | 浮標指細節下方主要按鈕 | 步驟 3 完成 |
| 5 | 1/3 | 對應值選「新增對應值」 | 陸運不是空運、海運或快遞 | 浮標指 INV-1005 細節裡的對應值選單 | 選單值為新增 |
| 5 | 2/3 | 輸入 LAND | 代碼用英文大寫，和其他代碼一樣 | 浮標指新增值的輸入框 | 輸入框值為非空、且不是既有代碼（Enter 或離開輸入框才判斷） |
| 5 | 3/3 | 按「儲存」 | 實際使用時，之後的檔案也會套用 | 浮標指「儲存」 | 步驟 5 完成 |
| 7 | 1/2 | 按配對卡片的表格圖示看原始表 | 右邊橘色「沒用到」的就是剩下的候選 | 浮標指 INV-1008 配對卡的表格圖示 | `guide.sawSource`（打開了 INV-1008 的小卡或完整工作表） |
| 7 | 2/2 | 沒有合適的，按「沒有配對」 | 沒用到的 AA15A0007 寫的是 INV-1099 | 浮標指「沒有配對」 | 步驟 7 完成 |

**各步的 `setup()`**（只能呼叫局部重繪：`renderTabs()`、`renderDrawer()`，不可呼叫 `runNow()` 或會重進導覽的整頁重繪）：

- 3：`selectRow(INV-1003)`（執行完本來就會自動打開第一筆，通常就是它；不是時才選）。
- 4：`selectRow(INV-1006)`，捲到「金額」。
- 5：`selectRow(INV-1005)`，捲到「運送方式」。
- 6：`goTo({ tab: "match", matchName: "inv_decl" })`，聚焦 INV-1009。
- 7：配對分頁聚焦 INV-1008。
- 列用 `title`（發票號碼）找，不寫死 `_rid`。

**選錯時的提示**（提醒行換成 `--warning-text` 加 ⚠，寫看到什麼、為什麼、怎麼改）：

| 情況 | 提示 |
|---|---|
| 4：輸入「約300」或空白 | ⚠ 現在是「約300」，金額只能是數字，改成 300 |
| 5：選了 AIR／SEA／EXPRESS（還沒儲存） | ⚠ 選了 AIR，陸運不是空運，改選「新增對應值」 |
| 5：已經存成既有代碼 | ⚠ 陸運存成 AIR 了，到「對照表」分頁移除再補一次 |
| 6：選了 AA15A0006 | ⚠ 選到 AA15A0006（1/15），改選 1/14 的 AA15A0005；先按「移除」 |
| 3：先修改了金額而不是確認 | 照樣算完成第 3 步（修改也是處理），提醒行寫「改過也可以，這一步算完成」 |

撰寫時以 `app.js` 實際的按鈕文字為準（例如新增對應值的選項目前是「＋ 新增對應值…」，提示裡寫「新增對應值」即可；「移除」要確認 one_to_one 人工指定的移除按鈕實際文字）。

**完成狀態**：步驟號換成 ✓，行動句「核對流程走完了」，提醒「範例還有 n 列，可以照同樣方式做完」（n 用實際待處理數）。右側：`回到我的工作`（有保存的工作時，primary）或 `用自己的資料開始`（沒有時，primary）、`練習放入 recipe`（ghost）、`清掉範例資料`（文字連結）。

### 4.3 關卡 B「放入 recipe」（5 步）

教「請 AI 寫 recipe → 貼回 → 看問題 → 看說明 → 儲存」。不需要真的 AI：用一鍵輔助帶入「練習用的 AI 回覆」。

| 步 | 標題 | 行動句 | 提醒 | 強調 | 完成條件 |
|---|---|---|---|---|---|
| 1 | 打開新增 | 按 Recipe 旁的「新增」 | recipe 寫好資料怎麼讀、怎麼配對 | 浮標指 `#newRecipe` | 新增 recipe 對話框開啟 |
| 2 | 複製規格 | 按「複製規格給 AI」 | 實際使用時連同欄位與規則貼給 AI | 浮標指該連結 | `guide.copiedSpec` |
| 3 | 貼上 AI 的回覆 | 按「幫我貼上練習回覆」，再按下一步 | 這份回覆故意留了 2 個問題 | 先指一鍵輔助，貼上後指「下一步：確認說明」 | 對話框顯示問題清單（`guide.sawProblems`） |
| 4 | 修正問題 | 子步驟 1/2「按『複製問題給 AI』」；2/2「按『幫我貼上修正版』，再按下一步」 | 1/2：問題附行號，AI 看得懂；2/2：實際使用時貼 AI 改好的版本 | 依序指兩個按鈕，再指「下一步：確認說明」 | 對話框顯示邏輯說明（`guide.sawExplain`） |
| 5 | 看說明再儲存 | 讀完說明，按「確認並儲存」 | 每一列會經過哪些判斷都寫在這裡 | 浮標指「確認並儲存」 | 練習 recipe 出現在左欄清單 |

- 練習回覆放在 `app/dataprocessor/demo/recipe-draft.yaml`，故意的 2 個問題必須是現有檢查會抓到的（例如不認得的設定 `stratagies`、`mode: one-to-one`）。修正版 `recipe-fixed.yaml` 與範例 recipe 邏輯相同，`id: practice-invoice`、`name: 發票對報關單（練習）`。
- 關卡 B 進行中按下「確認並儲存」時送 `POST /api/recipes { text, practice: true }`；伺服器一律寫入暫存空間 `paths.SCRATCH / "demo" / "recipes" / "invoice.yaml"`，對外 id 固定為 `practice:invoice`，絕不寫入或刪除 `workspace/recipes`。
- 開始關卡 B 時只刪暫存空間裡的 `practice:invoice`（每次示範都從頭來），第 5 步完成條件為這次關卡 B 開始之後已儲存且清單中有 `practice: true` 的 recipe。
- 一鍵輔助只把文字放進輸入框，「下一步」「確認並儲存」留給使用者按。
- 完成狀態：行動句「recipe 放好了」，右側 `用它處理範例資料`（primary，開始關卡 A，但改用剛存的 `practice:invoice`）、`刪除練習 recipe`（文字連結）。

### 4.4 三色圖例（關卡 A 第 2 步與速查共用 `statusLegendRow()`）

```
■ 沒問題  ■ 需檢查  ■ 找不到或無法執行  ■ 你處理過的
  綠         橘          紅                  藍
```

- 色塊 10×10、圓角 3px，用狀態 token：`--success`、`--warning`、`--danger`、`--accent`。每個色塊後接文字（色盲靠文字）。
- 這四個顏色只代表狀態。導覽介面用 accent（見 9），疊在表格上的指示用深色虛線，避免和「藍色是你處理過的」混淆。

### 4.5 一直保留的靜默提醒（不依賴導覽）

既有的這些維持不動，導覽關閉後照常出現：細節下方「確認無誤，下一筆」與 J／K、上方進度 Meter、「還有 n 個要處理」、recipe 有問題時的「問題清單」、流程卡片的「查看」。新增一個：結果表頂列的操作提示「點一列看細節，J／K 換列」，使用者成功用 J／K 換列 3 次後自動隱藏（記在 `tipsSeen`）。

---

## 5. 架構

### 5.1 一個 Spotlight 引擎

新增 `app/dataprocessor/web/spotlights.js`（在 `app.js` 之前載入）：

```js
{
  id: "review-confirm",
  journey: "review",            // "review"（關卡 A）| "recipe"（關卡 B）| null（進階、新功能）
  setup(ctx) {},                // 切分頁、選列；只能呼叫局部重繪
  target: '[data-guide="confirm-next"]',   // 用 id 或 data-guide，不用樣式 class
  outline: null,                // 疊在內容上的深色虛線：(ctx) => Element（列或格子）
  pointer: "↓ 確認無誤，下一筆",   // ≤ 12 字
  action: "按「確認無誤，下一筆」",
  tip: "範例當作已向業務確認，差額沒問題",
  wrong(ctx) { return null; },  // 選錯時回傳提示字串
  sub: null,                    // 子步驟陣列，格式同上（不含 sub）
  done(ctx) { return false; },
}
```

- 引擎函式：`startJourney(id)`、`openSpotlight(id, opts)`、`closeSpotlight()`、`scheduleGuide()`、`renderGuide()`、`syncEmphasis()`、`positionPointer(el, label)`。
- 進階說明卡、練習步驟、新功能逐項導覽都用同一種資料，不另寫定位與高亮邏輯。
- 需要指的元素一律加 `data-guide` 屬性（下表至少要有），不依賴 class：

| `data-guide` | 元素 |
|---|---|
| `stage-<stage>` | 流程卡片（load、gate、…、export） |
| `confirm-next` | 細節下方「確認無誤，下一筆」 |
| `issue-trace` + `data-rid` | 警示上的「怎麼判斷的」 |
| `field-<column>` + `data-rid` | 細節裡的欄位輸入框 |
| `map-select`、`map-new`、`map-save` | 細節裡補對照的選單、新增值輸入框、儲存 |
| `pick` + `data-rid` | 配對候選卡的「選這筆」 |
| `match-none`、`match-sheet` | 配對卡的「沒有配對」、表格圖示 |
| `spec-copy`、`problems-copy`、`recipe-next`、`recipe-save` | recipe 對話框的連結與按鈕 |

### 5.2 推關規則

- 只有「停在未完成的步驟，且它剛轉為完成」時自動推進；推進到**第一個未完成的步驟**，不是 +1。
- 使用者主動點回已完成的步驟時，不拉走。
- 推關時先更新 `lastStepId`、`lastStepDone` 再呼叫 `setup()`，避免遞迴。
- 關卡完成後維持完成，之後再改資料不會被拉回。
- 子步驟同樣推到第一個未完成的子步驟。
- 「下一步」在未完成時也可以按（跳過），進度點顯示為已跳過；練習的最後一步不能跳過。

### 5.3 完成條件怎麼寫

| 情況 | 做法 |
|---|---|
| 填文字（新增對應值、修改欄位） | 按 Enter 或離開輸入框才判斷；逐字輸入時不推進 |
| 「看懂」類（流程卡片、怎麼判斷的、原始資料） | 用實際行為設旗標（點開卡片、展開處理過程、打開小卡或完整工作表），不和下一步共用條件 |
| 處理警示 | 看 `state.result` 裡該列的 issue 狀態，排除剛被其他動作順帶處理的情況（例如第 3 步不能因為第 4 步的修改而完成） |
| 非同步動作（執行、修改後重算、補對照、配對、試算） | `act()` 與 `setResult()` 結束後呼叫 `scheduleGuide()` |
| 另一個視窗的操作 | BroadcastChannel 收到結果同步後也呼叫 `scheduleGuide()` |

### 5.4 事件與效能

- 影響完成條件的事件只呼叫 `scheduleGuide()`，用 `requestAnimationFrame` 合併同一畫格的多次呼叫。
- 浮標位置：中間欄、細節、結果表、原始表的 `scroll` 以 rAF 節流；視窗與 `#drawer` 寬度變化（含拖曳 splitter）用 `ResizeObserver`。
- `scrollIntoView({ block: "nearest" })` 只在目標改變且焦點不在輸入框時執行。
- 浮動卡（說明選單、說明卡、新功能卡、原始資料小卡 peek）開啟時，浮標與外框退讓。
- 搜尋會重畫分頁（design.md 已記）：導覽重繪不可搶走輸入框焦點。

### 5.5 偏好與進度

沿用 `prefs`，單一鍵 `dp:onboarding.v1`：

```json
{
  "dismissed": false,
  "journeys": { "review": { "step": "review-5", "done": false, "skipped": [] }, "recipe": { "step": null, "done": false, "skipped": [] } },
  "cardsSeen": ["card-trace"],
  "labsDone": ["lab-gate"],
  "tipsSeen": { "jk": 2 },
  "whatsnewSeen": "0.2.0"
}
```

- 讀取失敗一律當新使用者（`prefs.get` 已包 try/catch）。只存 id 與旗標，不存任何資料內容、檔名或 recipe 文字。
- 「關閉導覽」只收起 `#guideBar` 與 `#missionStrip`，進度保留。

### 5.6 對話框、popout、Esc

- **對話框（top layer）**：新增 recipe 的 `<dialog>` 用 `showModal()`，外面的浮標會被蓋住。關卡 B 進行中且對話框開啟時，指令條改畫在對話框內頂端（`.dialog-guide`，同指令條樣式、較精簡），浮標也 append 到 `#dialog` 內並以對話框座標定位。關閉對話框時移回。測試要驗證對話框開啟時浮標可見且在最上層。
- **popout**（`/?run=…&tab=…`）：隱藏所有導覽與教學元件（`#guideBar`、`#missionStrip`、浮標、虛線框、`.help-hint`、新功能卡與小點）。實用元件（J／K、確認無誤下一筆、Meter）保留。
- 步驟目標所在的分頁被 pop out 時，提醒行寫「這一步在另一個視窗，按『全部 Pop in』回來」，浮標指「全部 Pop in」。
- **Esc** 依序關閉：說明選單 → 說明卡 → 新功能小卡 → 外框。焦點在輸入框時 Esc 先交給輸入框；原始資料小卡維持現有的 Esc 行為且優先。J／K 在導覽進行中照常可用。

### 5.7 版本不一致偵測

pdf-mapper 曾發生「頁面是新的、伺服器是舊的」。新增 `app/dataprocessor/web/build.json`（`{"version": "0.2.0"}`，由測試確保和 `pyproject.toml` 一致）。頁面載入時比對 `build.json`（讀磁碟）與 `/api/status` 的版本（記憶體），不同就在頂列下方顯示一行：「工具已更新，關掉所有視窗後重新執行 run.bat」。

---

## 6. 第 2 層：進階功能

### 6.1 常駐「說明 ▾」選單

```html
<button id="helpBtn" type="button" class="ghost small help-trigger"
        aria-haspopup="dialog" aria-expanded="false">說明<span class="help-dot" hidden></span></button>
```

點開 `#helpPopover`（`.float-card`，寬 320）：

```
┌ 說明 ─────────────────────────────────┐
│ 新手導覽                                │
│   核對一份資料 8 步          進行到 5/8   │
│   放入 recipe 5 步           已完成 ✓    │
│ ─────────────────────────────────── │
│ 檢查與修正                              │
│   看這一格是怎麼來的                      │
│   兩張表並排，找配對的答案                 │
│   一次確認很多筆                          │
│   清掉重來，按錯可以復原                   │
│   表格太寬，搬到另一個螢幕                 │
│ 寫 recipe                    實地練習     │
│   排除不用處理的列                 ✓     │
│   各種寫法統一成同一個代碼                 │
│   號碼寫法不同也配得到                    │
│   一格有好幾行，只取需要的那行              │
│   數字對不上時提醒我                      │
│   用公式算出新欄位                        │
│ ─────────────────────────────────── │
│ 新功能   0.2 新增 4 項          ●        │
│ 使用手冊                         ↗      │
└─────────────────────────────────────┘
```

- 新手導覽兩列：未開始或進行中時開始或繼續，已完成時「重看」。
- 每個進階項目點下去開說明卡（6.3）。練過的練習標 ✓（`--text-faint`），不計入新手進度。
- 導覽關閉並重整後，選單仍在。

### 6.2 情境 `?`

只放在需要概念才看得懂的地方，每個區塊最多 1 顆（16×16，`.help-hint`，`aria-label="說明：…"`）：

- recipe 對話框標題旁：開「寫 recipe」分組的總覽卡（請 AI 寫、怎麼看說明）。
- 配對分頁的篩選列旁：開「兩張表並排，找配對的答案」。
- 對照表分頁標題旁：開「各種寫法統一成同一個代碼」。

### 6.3 說明卡

固定結構：目標導向標題、什麼時候用（1 句）、例子（原始內容 → 結果，識別碼用 monospace）、動作列。卡片內文 ≤ 60 字。

動作列依類型：

| 類型 | 動作 |
|---|---|
| 寫 recipe 類 | **實地練習**（primary）、複製給 AI 的提問、看手冊 ↗ |
| 檢查與修正類 | **試試看**（primary，用範例資料打開到那個位置並指出按鈕；沒有結果時先載入範例）、帶我去（有結果時）、看手冊 ↗ |

卡片內容（標題三處一字不差：說明卡、選單、手冊章節）：

| id | 標題 | 什麼時候用 | 例子 |
|---|---|---|---|
| `card-trace` | 看這一格是怎麼來的 | 不懂某個值為什麼是這樣 | `USD 3,450.00` → 金額 `3450`，幣別另一欄 |
| `card-source` | 兩張表並排，找配對的答案 | 找不到配對，想自己翻原始表 | 左邊發票、右邊報關單，橘色「沒用到」就是候選 |
| `card-bulk` | 一次確認很多筆 | 同一類要判斷的警示很多 | 所有警示勾選 → 確認無誤 |
| `card-reset` | 清掉重來，按錯可以復原 | 想從頭檢查一次 | 重新檢查 → 清掉 n 項 → 復原 |
| `card-popout` | 表格太寬，搬到另一個螢幕 | 欄位多、想兩個螢幕分工 | 結果 Pop out ↗，配對留在主視窗 |
| `lab-gate` | 排除不用處理的列 | 有作廢、小計這類不該處理的列 | 狀態 `作廢` → 放進「排除」 |
| `lab-mapping` | 各種寫法統一成同一個代碼 | 同一件事有好幾種寫法 | `快遞`、`Courier` → `EXPRESS` |
| `lab-match` | 號碼寫法不同也配得到 | 兩邊的單號格式不一樣 | `1004` 對 `INV-1004` |
| `lab-extract` | 一格有好幾行，只取需要的那行 | 品名後面接規格、保固 | `電源供應器 500W↵附電源線…` → `電源供應器 500W` |
| `lab-validate` | 數字對不上時提醒我 | 兩張表的金額要一致 | 金額 `2,000`、報關 `2,100` → 需檢查 |
| `card-transform` | 用公式算出新欄位 | 換匯、加總、組合欄位 | 金額 × 匯率 → 台幣金額 |

`card-transform` 不做練習：計算的 SQL 通常由 AI 寫，使用者不會自己改，只做說明卡加手冊，動作列用「複製給 AI 的提問」。

### 6.4 複製給 AI 的提問

工具不內建 AI、不連網。「複製給 AI 的提問」把下列內容組成文字放進剪貼簿，不送出任何資料：

1. 目標（卡片標題與「什麼時候用」）。
2. recipe 規格中對應的一節（從 `app/recipe-spec.md` 依標題擷取，加上「給 AI 的寫作規則」）。
3. 練習時：練習 recipe 全文、要寫的位置、練習資料的欄位與前 3 列。不在練習時：只放規格與目標，加一句「把我的欄位名稱和規則補在下面」。
4. 輸出要求：「只輸出要放進這個位置的 YAML，縮排從第 0 欄開始，不要加說明」。

---

### 6.5 練習中心與 mission（v0.2.1）

- 說明卡的主要動作一律是「開始練習」，不再有「試試看」「帶我去」。檢查類 6 張卡各有一條 mission（`mission-trace`、`mission-source`、`mission-bulk`、`mission-reset`、`mission-popout`、`mission-transform`），用範例資料一步一步做到完成；寫 recipe 的 5 個練習沿用 `labs.json`。
- mission 與練習共用 Spotlight 引擎、`leaveDemo` 與 `savedWork`，進度存在 `prefs.practiceDone`（舊的 `labsDone` 載入時自動遷移）。
- 練習中心是 `<dialog id="practiceHub">`，共 11 項，標出已練與建議的下一項。入口四個：說明選單、歡迎畫面、關卡 A 完成畫面、首次自己的資料執行完後的一次性提示。
- 對話框內的導覽元件依 5.6：指令條與浮標畫在對話框內。第一次開啟且尚未練過任何一項時，浮標指「從這裡開始」。
- 浮標只寫要做什麼，不寫方向箭頭；目標在畫面外時寫「往上捲」「往下捲」。指令條（`.guide-dock`）sticky，捲動時仍看得到。
- mission-reset 的 2 筆人工決定用既有 API 寫在範例暫存空間，不寫進 `workspace/reviews`。mission-popout 若瀏覽器擋掉新視窗，可按「跳過這條練習」，不計入完成。

## 7. 範例資料、練習與後端

### 7.1 資料放在程式資料夾

新增 `app/dataprocessor/demo/`（隨版本更新、使用者刪不掉）：

```
demo/
  demo.json                    範例與練習的白名單：id → 檔案
  範例_發票與報關單.xlsx         由 scripts/make_example.py 一起產生，和 examples 那份相同
  invoice-declaration.yaml     關卡 A 的範例 recipe（和 examples 那份相同）
  recipe-draft.yaml            關卡 B：有 2 個問題的練習回覆
  recipe-fixed.yaml            關卡 B：修正版
  labs.json                    練習定義與預期值（7.4）
  labs/<lab-id>.yaml           每個練習的前置 recipe，含插入位置
```

- 不依賴 `workspace/samples` 與 `workspace/recipes` 裡的範例（使用者可能刪掉）。第一次啟動複製 `examples/workspace` 的行為維持不變。
- `scripts/make_example.py` 一次產生兩處；測試檢查兩份 recipe 與 workbook 內容相同。

### 7.2 範例端點

| 端點 | 用途 |
|---|---|
| `POST /api/demo/start` `{ "journey": "review" }` | 註冊範例 workbook，回傳 `{ workbook, recipe: {id, name, demo: true} }` |
| `GET /api/demo/recipe/<name>` | 回傳 `recipe-draft`、`recipe-fixed` 的文字（白名單） |
| `GET /api/labs` | 練習清單（id、標題、步驟數），不含預期值 |
| `POST /api/labs/<id>/start` | 用練習 recipe 與練習 workbook 執行，回傳執行結果與片段的起始內容 |
| `POST /api/labs/<id>/try` `{ "snippet": "…" }` | 插入片段、檢查、執行、比對預期值（7.4） |
| `POST /api/demo/clear` | 清掉範例與練習的暫存結果、決定、對照、練習 recipe |

- 只接受白名單 id，不接受路徑或檔名；未知 id 回 400。沿用既有 Host、`Sec-Fetch-Site`、Origin 檢查。
- 日誌只記 journey 或 lab id、通過與否、數量。
- 範例 recipe 在 `/api/runs` 用保留 id `demo:<name>` 指定，由伺服器從 `demo/` 讀取；不出現在 `/api/recipes`。

### 7.3 不汙染正式資料

| 項目 | 做法 |
|---|---|
| 人工決定 | `ReviewStore` 改用 `paths.SCRATCH / "demo" / "reviews"`，程式結束或 `/api/demo/clear` 時刪除 |
| 補的對照 | `MappingStore` 改用 `paths.SCRATCH / "demo" / "mappings"`，同上 |
| 執行結果 | 標 `demo: true`；介面 `#runStatus` 顯示「範例」小標籤 |
| 匯出 | 檔名加「示範_」前綴（0.2.2 起下載只在記憶體產生，不再另存到 `workspace/output`） |
| 練習 recipe（關卡 B） | 存在暫存空間 `paths.SCRATCH / "demo" / "recipes" / "invoice.yaml"`，對外 id 為 `practice:invoice`，清單帶 `practice: true` 並顯示「練習」標籤。任何範例或練習程式都不碰 `workspace/recipes`。開始關卡 B、完成畫面的「刪除練習 recipe」與 `/api/demo/clear` 都只刪暫存檔 |
| 練習（labs） | 不寫入 `workspace/recipes`；結果、決定、對照都在暫存 |

### 7.4 練習定義（`labs.json`）

```json
{
  "id": "lab-match",
  "title": "號碼寫法不同也配得到",
  "recipe": "labs/lab-match.yaml",
  "workbook": "範例_發票與報關單.xlsx",
  "slot": { "marker": "# {{slot}}", "label": "再找：另一種比對方式" },
  "start": "",
  "answer": "- label: 只比數字部分\n  when: \"dp_digits(l.invoice_no) <> ''\"\n  on: \"dp_digits(l.invoice_no) = dp_digits(r.ref_no)\"",
  "checks": [
    { "type": "match", "match": "inv_decl", "left": "1004", "right": "AA15A0004",
      "how": "報關單寫 INV-1004，只比數字才對得上" },
    { "type": "match", "match": "inv_decl", "left": "INV-1001", "right": "AA15A0001",
      "how": "原本配得到的不能被改掉" }
  ]
}
```

- **插入片段**：練習 recipe 在要寫的位置放一行 `# {{slot}}`。伺服器把使用者的片段依那一行的縮排逐行縮排後取代，再用既有 recipe 載入與檢查（SafeLoader、單一 SELECT、120 秒等全部照舊）。錯誤的行號換算回片段裡的行號。
- **checks 類型**：`match`（左表 title → 右表 title，或 `none`）、`excluded`（被排除的 title 清單，完全相等）、`field`（某列某欄的值）、`issue`（某列有或沒有某類警示）、`count`（需檢查列數）。列一律用 `title` 指定。
- **`/try` 回傳**：`{ ok, problems: [...], checks: [{ label, pass, expected, actual, hint }], result }`。`result` 是這次執行的完整結果，前端用 `setResult()` 更新畫面，使用者直接在結果表看到效果。recipe 有問題時回 200 與 `problems`，在練習面板顯示，不跳錯誤頁。
- **提示**寫三件事：「發票 1004：配到（沒有），應該是 AA15A0004。報關單寫 INV-1004，只比數字才對得上。」
- `answer` 只給「幫我帶入」用，`/api/labs` 不回傳預期值與答案；`/try` 失敗 2 次後前端才顯示「幫我帶入」。

### 7.5 五個練習

每個練習 4 步，沿用指令條、浮標、虛線框與推關規則；練習的編輯介面放在右側 `#drawer`（練習期間取代單列細節，稱「練習面板」），結果表照常在中間。

共同步驟：

| 步 | 行動句 | 強調 | 完成條件 |
|---|---|---|---|
| 1 看問題 | 依練習（見下表） | 外框指問題所在的卡片或列 | 看了指定的卡片或列 |
| 2 找到要寫的位置 | 練習面板裡是 recipe，看虛線那段 | 外框指片段編輯框 | 片段編輯框取得焦點 |
| 3 寫規則 | 照目標寫，或複製提問給 AI | 浮標指「複製給 AI 的提問」 | 片段不為空，且按 Enter（Ctrl+Enter）或離開編輯框 |
| 4 試算驗證 | 按「試算」，全部打勾才算完成 | 浮標指「試算」 | `/try` 回傳全部 `pass`；**不能跳過** |

| id | 第 1 步行動句 | 起始片段位置 | checks |
|---|---|---|---|
| `lab-gate` | 「排除」是空的，作廢的也被處理了 | `gate:` 底下 | `excluded` = [INV-1007] |
| `lab-mapping` | 「快遞」「Courier」不在對照表 | `entries:` 底下（已有 AIR、SEA） | INV-1004 運送方式 = EXPRESS；INV-1004 沒有「不在對照表」警示 |
| `lab-match` | 1004 找不到報關單 | 第 1 個比對方式之後 | 見 7.4 |
| `lab-extract` | INV-1003 的品名有三行 | `item` 欄位設定底下 | INV-1003 品名 = 「電源供應器 500W」；INV-1001 品名不變 |
| `lab-validate` | INV-1003 金額不同卻沒有被標出來 | `validate:` 底下 | INV-1003 有驗證警示；INV-1001 沒有；警示帶 `highlight` 的金額欄 |

練習面板內容（由上到下）：目標一句；recipe 全文唯讀（`pre`，monospace，插入位置以深色虛線框標出並自動捲到這裡，其他段落可收起）；片段編輯框（textarea，自動長高）；「試算」（primary）、「複製給 AI 的提問」（ghost）、失敗 2 次後出現的「幫我帶入」（文字連結）；結果清單（每個 check 一行，✓ 用 `--success-text`，未通過用 `--warning-text` 加 ⚠ 與提示）。

**完成畫面**（練習面板）：一句學到什麼（例如「比對方式可以排好幾種，前面配不到才換下一種」）、`看手冊`、`再練一次`、`回到我的工作`（primary）。

#### 離開範例與練習

- 所有離開範例或練習的出口（「關閉導覽」「結束練習」「回到我的工作」「用自己的資料開始」）統一呼叫 `leaveDemo({ dismiss })`。
- 畫面上是範例或練習時：有 `savedWork` 就還原原本的工作（先 `setResult()` 再套回分頁、篩選、搜尋、選到的列、配對設定與細節寬度，最後 `renderTabs()`）；沒有 `savedWork` 就清回歡迎畫面。原本的 workbook 已被伺服器關閉時，回到歡迎畫面並 toast「原本的檔案已關閉，請重新放入」。
- 畫面上是使用者自己的結果時（例如開說明卡再關閉），只收起導覽元件，不動畫面。只有 `dismiss: true`（「關閉導覽」）才設 `prefs.dismissed = true`。
- `savedWork` 同步存在 `sessionStorage`（鍵 `dp:savedWork`，只存 id 與畫面狀態，不存資料內容），進入範例或練習前若已有 `savedWork` 不覆蓋；還原成功或使用者明確開始自己的工作（放檔、執行）時清掉。
- 續玩關卡 A 第 2 步以後若畫面沒有範例結果，指令條顯示「正在準備範例資料…」，自動準備並執行範例資料後推到第一個未完成步驟（不超過存的步驟）；準備失敗或關卡 B 對話框沒開時退回第 1 步。看懂類布林旗標存在 `prefs.journeys.<id>.flags`。

---

## 8. 第 3 層：新功能

### 8.1 資料

新增 `app/dataprocessor/web/whatsnew.json`：

```json
{
  "versions": [
    {
      "version": "0.2.0",
      "date": "2026-12-xx",
      "items": [
        { "id": "0.2.0-help", "title": "說明選單", "body": "導覽、進階功能、練習與手冊都在右上角。", "spotlight": "help-menu" },
        { "id": "0.2.0-labs", "title": "寫 recipe 的實地練習", "body": "改一小段 recipe，試算確認做對。", "spotlight": "help-labs" },
        { "id": "0.2.0-source", "title": "兩張表並排找配對", "body": "原始表標出沒用到的列，答案一眼就看到。", "spotlight": "card-source", "needsResult": true },
        { "id": "0.2.0-why", "title": "警示怎麼判斷的", "body": "展開規則與這一列用到的每個值。", "spotlight": "card-trace", "needsResult": true }
      ]
    }
  ]
}
```

- `title` ≤ 16 字、`body` ≤ 40 字；只寫使用者看得到的改變。沒有可見改變的版本寫 `"items": []`。
- `spotlight` 指向 Spotlight 步驟 id，和進階說明卡共用資料。
- `needsResult: true` 但目前沒有結果時，卡片附「用範例資料看」。

### 8.2 觸發

- **第一次使用的人**：不顯示，直接把 `whatsnewSeen` 設為目前版本。
- **升級的人**：目前版本 > `whatsnewSeen`，或 `whatsnewSeen` 不存在但 `/api/status` 回傳 `returning: true`（`workspace/reviews` 或 `workspace/mappings` 有內容，或有範例以外的 recipe）。從 0.1.0 升上來的人沒有 `whatsnewSeen`，靠這個判斷。
- 觸發時：「說明」右上 6px 小點；啟動 1.2 秒後頂列下方滑出小卡一次（列前 2 項標題，「看看」／「之後再說」）。新手導覽進行中只亮小點、不跳卡。popout 不顯示。
- 跨多版合併，新的在前，最多 5 項，其餘在「看全部」。
- 看完最後一項或按「結束」：`whatsnewSeen` 設為目前版本，小點消失。「之後再說」只收小卡，小點保留。

### 8.3 歷史與 CI

- 「說明 ▾ → 新功能」列出所有版本（新到舊），每項可單獨打開導覽。
- `scripts/check_whatsnew.py`：`whatsnew.json` 必須有 `pyproject.toml` 目前版本的條目、每個 `spotlight` id 存在於 `spotlights.js`、字數符合上限。加進 `tests/test_release.py` 與 `.gitlab-ci.yml`（不需要瀏覽器，CI 可以跑）。

---

## 9. 視覺規格（Stageshow token）

| 元素 | 樣式 |
|---|---|
| `#guideBar` | 高 38、`--surface` 底、下緣 1px `--line`；左右內距 12；一行不換行 |
| 進度點 | 8×8 圓；未做 `--ink-4` 空心、目前與完成 `--accent` 實心（目前外加 3px `--accent-soft` 光環）、跳過為空心加斜線；連線 1px `--ink-3`，上限 20px；可點回頭，`aria-label="第 3 步：看懂再確認，進行中"` |
| 「3/8 名稱」 | 12.5px `--accent-text`；窄螢幕先藏進度點，再截斷名稱（`text-overflow: ellipsis`），按鈕 `white-space: nowrap` |
| `#missionStrip` | `--accent-soft` 底、1px accent 細框（約 35%，缺 token 就補 `--accent-line`）、`--radius-md`、外距 8 12、內距 10 12；`aria-live="polite"`、`aria-atomic="true"` |
| 步驟號 | 20×20 圓，`--accent` 底白字 12.5px；子步驟顯示「3　1/2」 |
| 行動句 | 14px 600 `--text-strong` |
| 提醒 | 12.5px `--text-strong`（不要用灰色 `--text`） |
| 選錯提示 | 12.5px `--warning-text` 加 ⚠（不用紅色，紅色代表找不到） |
| 一鍵輔助 | 行動句後的 ghost 小按鈕，高 24 |
| 上一步／下一步 | ghost 按鈕，高 `--button` |
| 浮標 `#guidePointer` | `--accent` 底白字、`--radius-md`、高 26、12.5px 500、左右 10 內距、6px 三角；`pointer-events: none`、`aria-hidden`；依序試右、左、下、上，選不和 `#guideBar`、`#missionStrip`、頂列矩形重疊的方向；目標在畫面外時顯示 ↑／↓ 指捲動方向 |
| 按鈕外框 `.guide-target` | 2px `--accent` outline、`outline-offset: 3px` |
| 疊在內容上的虛線 `.guide-outline` | 1.5px 虛線 `--text-strong`（60%），用在結果表的列或格子、原始表的列、練習面板的插入位置；`pointer-events: none` |
| 浮動卡 `.float-card` | `--surface`、`--radius-lg`、`--shadow-float`、內距 12、寬 300～320；開啟 250ms `--ui`（opacity 與 translateY 4→0），關閉 150ms；`role="dialog"`，開啟時焦點到第一個按鈕，關閉回到觸發元素 |
| 新功能小點 | 6px `--accent`，外圈 2px `--surface` 描邊；第一次出現 scale 0→1 一次 |
| 換步驟提醒 | 指令條 accent 外圈脈衝 1 次（700ms）；`prefers-reduced-motion: reduce` 時關閉所有導覽動畫 |
| 練習面板 | 沿用 `#drawer` 的寬度與 splitter；recipe 全文 `--mono` 12.5px、`--well` 底 |

**同時只有一個強調點**：`syncEmphasis()` 依序判斷：有內容虛線就只畫虛線；否則目標可見就顯示浮標加外框；目標在畫面外只顯示浮標。浮標和內容虛線同時成立時，先用浮標指按鈕，進入操作後才換虛線（pdf-mapper 坑 #20）。

**導覽進行中收起重複的提示**：結果表頂列操作提示在導覽進行中不顯示，避免兩條藍色說明疊在一起。

---

## 10. 使用手冊改版

### 10.1 架構（`docs/user-guide.md`）

定位：參考手冊。操作步驟由工具內導覽教，手冊放規則細節、例外、出錯怎麼辦。

```
1. 快速上手（一頁）          指向工具內「用範例資料邊做邊學」與「練習放入 recipe」
2. 安裝、更新與退回           沿用現有第 1 節
3. 功能參考
   3.1 處理一份資料（流程卡片、八個步驟各做什麼）
   3.2 檢查與修正：看這一格是怎麼來的／兩張表並排，找配對的答案／一次確認很多筆／
       清掉重來，按錯可以復原／表格太寬，搬到另一個螢幕／只看需要的欄位
   3.3 寫 recipe：排除不用處理的列／各種寫法統一成同一個代碼／號碼寫法不同也配得到／
       一格有好幾行，只取需要的那行／數字對不上時提醒我／用公式算出新欄位／多個檔案一起處理
4. 看懂輸出（狀態顏色、警示類別與哪些一定要處理、下載的 Excel 每張工作表）
5. 讓 AI 幫你寫 recipe
6. 常見問題（依症狀分組：執行前、執行後看不懂、配對、對照表、下載、更新）
7. 管理與維護（資料夾、備份、搬電腦、紀錄檔）
附錄：速查（顏色、鍵盤 J／K／Esc、警示代碼、recipe 設定一覽）
```

- 每個功能一節，固定小節：什麼時候用、怎麼設（或怎麼操作）、例子（原始內容 → 結果）、常見錯誤、在工具裡練習（寫「說明 ▾ → 標題 → 實地練習」）。
- 章節標題和說明卡、選單一字不差。
- 每節有固定錨點，用 `{#help-trace}` 這類明確 id（啟用 markdown `attr_list` 擴充），不依賴中文自動 slug。說明卡的「看手冊」用 `/manual#<錨點>` 深連結。

### 10.2 「讓 AI 幫你寫 recipe」一章

不需要資料安全段落（公司有內建 AI）。內容：

- 適合交給 AI 的事：整份 recipe、一條比對方式、一個 `extract`、一條驗證的 SQL。
- 要告訴 AI 的工具規則（照程式實際行為，從 `app/recipe-spec.md` 與 `engine/recipe.py`、`engine/sandbox.py` 核對後寫）：只用 YAML；不能用錨點、別名、`!` 標籤；`on`／`yes`／`no` 不當布林；SQL 只能是單一 SELECT 或運算式、不能有分號、超過 120 秒中止、讀不到檔案也不能連網；名稱規則（英文開頭、不用 `dp_` 與 `_` 開頭）；可用 `dp_key`、`dp_digits`、`jaro_winkler_similarity`、`levenshtein`、正規表達式、視窗函數；判斷不了要讓它被標記。
- 可直接複製的提問範本：整份 recipe、改一段、修正問題清單。
- 貼回驗證的流程：貼上 → 問題清單 → 複製問題給 AI → 邏輯說明逐句確認 → 用一份資料執行，看流程卡片與處理過程。
- 什麼時候不該用規則：判斷要靠人看原始文件、例外只有一兩筆時，直接在工具裡修改或指定配對比較快。

### 10.3 HTML 版改用 Stageshow

`scripts/build_manual.py` 的樣式改為 Stageshow（和工具一致，取代現在的黑白綠樣式）：左側固定目錄、離線搜尋（純 JS 比對標題與段落，不載外部資源；注意 CSP：搜尋 JS 以內嵌檔案方式產生時要確認 `/manual` 的 CSP 允許，否則改成同源 `<script src>`）、三線表、列印版面（隱藏目錄與搜尋）、圖片內嵌。

### 10.4 截圖

新增 `scripts/make_manual_screens.py`（Playwright，本機執行，不在 CI）：1440×900、關閉所有導覽元件、只截相關面板、避開固定按鈕、拍成功的例子（範例資料處理到對應狀態）。輸出到 `docs/images/`。產生後要**逐張看過**並在回報裡寫看過了。發版前重拍。

---

## 11. 測試

一般測試放 `tests/`（CI 會跑），介面測試放 `tests/ui/`（本機跑）。檔名不可和既有檔案同名（pytest 收集會衝突），練習的介面測試用 `test_labs_ui.py`。

| 檔案 | 測試 | 抓什麼 |
|---|---|---|
| `tests/test_demo.py` | 範例端點白名單、未知 id 回 400、跨站 Origin 被擋 | 安全 |
| | 範例執行後 `workspace/reviews`、`workspace/mappings` 沒有新檔；匯出檔名有「示範_」；`/api/demo/clear` 清乾淨 | 汙染 |
| | `demo/` 與 `examples/` 的 recipe、workbook 相同 | 資料漂移 |
| `tests/test_labs.py` | 每個練習的 `answer` 通過所有 checks；起始片段不通過；錯誤片段回 `problems` 且行號是片段行號 | 練習驗證邏輯 |
| `tests/test_whatsnew.py` | `check_whatsnew.py` 在缺版本、spotlight id 不存在、字數超過時失敗 | 發版檢查 |
| `tests/test_manual.py` | 說明卡的所有手冊錨點都存在於產生的 HTML；卡片標題和手冊章節標題一致 | 深連結 |
| `tests/test_release.py` | `build.json` 版本 = `pyproject.toml` | 版本不一致 |
| `tests/ui/test_onboarding.py` | 關卡 A、B 從頭走到完成（用真的點擊與鍵盤，不直接呼叫 JS 函式） | 流程走得完 |
| | **全關卡掃描**：逐步推進，每一步與每個子步驟都有可見的浮標、外框或虛線，且行動句不為空 | 某一步沒有提示 |
| | 逐字輸入（`press_sequentially`）「LAND」與「300」：中途提示仍在、步驟沒推進 | 打一個字就跳步 |
| | 選錯（AIR、AA15A0006、約300）會出現 ⚠ 提示，修正後推進 | 選錯提示 |
| | 第 4 步的修改不會讓第 3 步完成；第 3 步沒確認時停在第 3 步 | 共用完成條件 |
| | 非同步動作後不做其他點擊，指令條自動推進 | 漏觸發重繪 |
| | 浮標和 `#guideBar`、`#missionStrip`、頂列的矩形不重疊 | 浮標遮字 |
| | 同一時間 `.guide-outline`、`#guidePointer`、`.guide-target` 最多一種可見 | 單一強調點 |
| | 關卡 B 對話框開啟時，浮標與對話框內指令條可見，且浮標位於對話框內 | top layer 遮擋 |
| | 選單、對應值選單用鍵盤與滑鼠兩種方式操作 | 只用程式選取測不出的問題 |
| | 寬 1000、1100px：導覽列一行、按鈕不換行 | 窄螢幕跑版 |
| | 有自己的結果時開始導覽 → 詢問 → 走完按「回到我的工作」→ 結果、分頁、選到的列都恢復 | 資料遺失 |
| | 關掉導覽重整後，`#helpBtn` 仍在，可以開任一說明卡 | 進階入口消失 |
| | 在 pop out 視窗處理 INV-1008 的配對，主視窗推進 | 另開視窗 |
| | popout 視窗看不到任何導覽元件，但 J／K 與「確認無誤，下一筆」可用 | popout 隔離 |
| `tests/ui/test_labs_ui.py` | 每個練習：寫錯 → 看到「哪一列、抓到什麼、應該是什麼」→ 修到對 → 完成畫面 | 練習 |
| | 最後一步沒有「下一步」可跳過 | 驗證不可跳過 |
| | 練習前有結果 → 練習 → 回到我的工作完整恢復；練習 recipe 不出現在左欄清單 | 汙染與恢復 |
| `tests/ui/test_whatsnew_ui.py` | 全新使用者不跳；舊版本使用者跳一次；`returning: true` 且沒有 `whatsnewSeen` 時跳；看完小點消失；導覽進行中只亮小點 | 觸發規則 |

每個新介面測試要確認「把功能拿掉時會失敗」（CLAUDE.md 規定）。

---

## 12. 分批與交接

每批由新的 agent 執行，交接時只給本規格的對應章節與上一批的回報。

| 批 | 內容 | 涵蓋章節 | 完成時 |
|---|---|---|---|
| 1 | `demo/` 資料夾與產生腳本、範例端點、暫存的決定與對照、匯出前綴、`returning` 與版本偵測 | 5.7、7.1～7.3 | `test_demo.py`、`test_release.py` 通過 |
| 2 | Spotlight 引擎、`data-guide` 屬性、偏好鍵、「說明 ▾」選單、說明卡（先放檢查類 5 張）、情境 `?`、Esc 與 popout 隔離 | 5.1～5.6、6.1～6.3、9 | 選單與說明卡介面測試 |
| 3 | 歡迎畫面、關卡 A | 4.1、4.2、4.4、4.5 | 關卡 A 全部介面測試含全關卡掃描 |
| 4 | 關卡 B、對話框內導覽 | 4.3、5.6 | 關卡 B 介面測試 |
| 5 | 練習引擎、`/api/labs`、練習面板、5 個練習、複製給 AI 的提問 | 6.4、7.4、7.5 | `test_labs.py`、`test_labs_ui.py` |
| 6 | 新功能 | 8 | `test_whatsnew*.py`、CI 檢查 |
| 7 | 手冊改版、`build_manual.py` 改 Stageshow、截圖腳本、錨點測試 | 10 | `test_manual.py`；截圖逐張看過 |
| 8 | 全部測試、文件、版本 | 11 | 完整測試通過；`docs/design.md`、`CHANGELOG.md` 更新；版本升為 0.2.0 |

第 8 批之後由 Frederic 在 Windows Edge 上完整重啟（關掉所有視窗、重新執行 run.bat）實測兩條關卡與五個練習。合併前確認分支的所有 commit 都進了 main。

### 12.1 文件更新

- `docs/design.md` 新增「新手導覽、練習與新功能（日期）」一節，記下：範例資料放 `app/`、範例的決定與對照只放暫存、導覽介面用 accent 而疊在內容上用深色虛線、對話框內畫導覽、不提供「在目前資料上繼續導覽」的理由、`returning` 判斷。
- `CHANGELOG.md` 新增 0.2.0 段落，和 `whatsnew.json` 一起更新；`docs/maintain.md` 的發版檢查清單加一行「新功能導覽已更新」。

---

## 13. 已確認的決定（2026-11-24）

1. 版本升為 0.2.0；0.1.0 之後加進 CHANGELOG 的功能（原始資料配對欄、怎麼判斷的）列進 0.2.0 的新功能。
2. 關卡 A 第 5 步「陸運」新增的代碼用 `LAND`，範例不需要很嚴謹。
3. 練習 recipe 顯示在清單裡、每次示範重置，但存放在暫存空間，不和使用者的 recipe 混在一起（2026-11-24 實測後修正，見 7.3）。
4. 「用公式算出新欄位」這版只做說明卡，不做練習：計算的 SQL 通常由 AI 寫，使用者不會自己改。
