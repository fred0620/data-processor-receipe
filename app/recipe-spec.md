# Recipe 規格（第 1 版）

這份文件是寫給 AI 看的。使用者會把這份規格、資料的欄位說明（或幾列範例）和他的處理邏輯一起交給 AI，請 AI 寫出 recipe。AI 寫完後，使用者在資料處理器按「新增」貼上；檢查不通過時，畫面會列出所有問題，使用者會整段貼回來請 AI 修正。

## 給 AI 的寫作規則

1. 只輸出一份完整的 YAML，不要省略任何段落，不要加說明文字。
2. recipe 不能包含 Python 或任何程式碼。邏輯判斷用下面的設定和 SQL（DuckDB 語法）表達。
3. SQL 只能是一段 SELECT 或一個運算式，不能有分號。SQL 只看得到 recipe 裡定義的表，讀不到檔案也不能連網。
4. 表名稱、欄位名稱用英文字母開頭，只用英數與底線，不能以 `dp_` 或 `_` 開頭。輸出欄位的顯示名稱可以用中文。
5. 判斷不了的情況要讓它被標記出來，不要寫成會默默猜一個值的規則。例如對照表找不到時用 `missing: ask`，配對找不到時用 `unmatched: flag`。
6. 不確定使用者的規則時，在 YAML 開頭用 `#` 註解列出你做的假設，讓使用者確認。

## 流程

資料依序經過下列步驟，每一步的結果都會顯示在畫面上供人檢查：

| 步驟 | recipe 段落 | 做什麼 |
|---|---|---|
| Load | `inputs` | 依表頭別名找出工作表與欄位，讀進來 |
| Gate | `gate` | 排除不該處理的列（例如作廢），被排除的列會列出來 |
| Normalize | `inputs.*.columns` | 轉型別、清理文字、套對照表；解析失敗就留空並標記 |
| Match | `match` | 兩張表配對，可以列出多個比對方式依序嘗試 |
| Transform | `transform` | 用 SQL 計算新欄位、彙總 |
| Validate | `validate` | 用條件找出有問題的列並標記 |
| Mapping | `output.columns[].map` | 輸出前再套一次對照表 |
| Export | `output` | 決定輸出欄位與順序 |

每一列都有系統欄位 `_rid`（列代號）和 `_row`（Excel 列號）。人工修改、配對、警示都靠 `_rid` 對回原始資料，**transform 的 SELECT 請保留 `_rid`**（用 `SELECT *, ...` 最簡單），彙總成新表時才會沒有。

## 完整結構

```yaml
recipe: 1                     # 規格版本，固定寫 1
id: invoice-declaration       # 英數、底線、連字號，同時是存檔名稱
name: 發票對報關單             # 畫面顯示的名稱
description: 一兩句說明

inputs: {}                    # 必填，見下方
gate: []                      # 選填
mappings: {}                  # 選填
match: []                     # 選填
transform: []                 # 選填
validate: []                  # 選填
output: {}                    # 必填
```

## inputs：輸入表

```yaml
inputs:
  invoice:                          # 表名稱，SQL 裡用這個名字
    sheet: [發票明細, Invoice]       # 選填。候選工作表名稱；不寫就找所有工作表
    header_row: auto                # 選填。表頭在第幾列；不寫或 auto 會在前 30 列自動找
    columns:
      invoice_no:
        aliases: [發票號碼, Invoice No]   # 表頭可能的寫法，比對時不分全半形、大小寫、空白與標點
        required: true                   # 找不到這個表頭就停止；資料列空白會標記
        text: [trim, halfwidth, upper, no_space]
      amount: {aliases: [金額], type: number, strip: [KG]}
      inv_date: {aliases: [日期], type: date, roc: auto}
      ship_mode: {aliases: [運送方式], map: ship_mode}
      note: 備註                          # 簡寫：只寫表頭文字
```

欄位設定：

| 設定 | 說明 |
|---|---|
| `aliases` | 表頭文字，可以多個。必須整格相同（寬鬆比對），不做模糊比對 |
| `type` | `text`（預設）、`number`、`integer`、`date` |
| `required` | `true` 時：表頭找不到就無法執行；資料空白會標「需檢查」 |
| `text` | 文字清理，依序套用：`trim`、`upper`、`lower`、`halfwidth`（全形轉半形）、`collapse_space`、`no_space`、`digits_only`、`alnum_only`。預設 `[trim, collapse_space]` |
| `replace` | 正規表達式取代，`[[pattern, 取代文字], ...]`，在轉型或清理前套用 |
| `strip` | number／integer 用，解析前去掉的單位文字，例如 `[KG, 箱]` |
| `formats` | date 用，額外的 strftime 格式，例如 `["%d/%m/%Y"]` |
| `roc` | date 用。`auto`（預設，年份小於 1000 視為民國）、`always`、`never` |
| `map` | text 用，套用 `mappings` 裡的對照表 |

內建解析規則：

- **數字**：接受千分位、全形數字、貨幣符號與代碼（`$`、`NT$`、`USD` 等）、括號負數 `(150)`、尾端負號、百分比（`12%` 變成 0.12）。其他文字（例如「約 300」、「12KG」沒寫 strip）一律解析失敗、留空並標記。
- **日期**：接受 `2026-01-05`、`2026/1/5`、`2026.1.5`、`20260105`、`2026年1月5日`、民國 `115/01/05`，以及 Excel 的日期格式。
- 解析失敗時值留空，原始內容會顯示在畫面和 Excel，不會被塞進欄位。

## gate：篩選

```yaml
gate:
  - input: invoice
    keep: "status IS NULL OR status <> '作廢'"   # SQL 條件，成立的列留下
    label: 排除作廢發票                           # 畫面上的原因
```

條件看的是 Normalize 之後的值（型別已轉好）。被排除的列不會產生後續警示，但會列在「排除」分頁和 Excel。

## mappings：對照表

```yaml
mappings:
  ship_mode:
    values: [AIR, SEA, EXPRESS]       # 選填。允許的對應值；寫了之後介面會用下拉選單補對照
    entries:
      AIR: [空運, 航空, Air freight]   # 對應值: [原始寫法, ...]
      SEA: [海運, Ocean]
    missing: ask                       # 找不到時：ask（留空並標記待補）、keep（保留原值並提示）、blank（留空並提示）
```

- 比對不分全半形、大小寫、空白與標點，所以「空 運」、「AIr」不用另外列。
- 對應值本身也算一種寫法（資料寫 `AIR` 會對到 `AIR`）。
- **什麼時候用在 inputs、什麼時候用在 output**：值要拿來配對、篩選或計算時，在 `inputs` 的欄位用 `map`；只是輸出時要換成代碼，在 `output.columns` 用 `map`。
- 嚴格欄位（找不到就不能交出去的）用 `missing: ask`。使用者在「對照表」分頁補上後，對照會存在本機，下次處理其他檔案也會自動套用，不需要改 recipe。
- `values` 清單裡沒有合適的值時，使用者可以在介面「新增對應值」。新增的值只存在本機，要讓其他人也用到，請把它加進 recipe 的 `values` 和 `entries`。

## match：配對

```yaml
match:
  - name: inv_decl                  # 配對結果的表名稱，後面的步驟可以使用
    left: invoice                   # 左表：每一列都會保留
    right: declaration              # 右表：配對成功時把欄位帶過來
    mode: one_to_one                # 見下方「配對方式」，預設 many_to_one
    strategies:                     # 依序嘗試，前面配到的列不會再進入後面的方式
      - label: 發票號碼相同
        on: [[invoice_no, ref_no]]                   # 欄位配對清單：等值比對
      - label: 只比數字部分
        when: "dp_digits(l.invoice_no) <> ''"         # 選填：左表符合條件才用這個方式
        on: "dp_digits(l.invoice_no) = dp_digits(r.ref_no)"   # SQL 條件：l. 是左表、r. 是右表
      - label: 金額相同且品名相似
        on: "l.amount = r.amount AND jaro_winkler_similarity(dp_key(l.item), dp_key(r.item)) >= 0.85"
        best: "jaro_winkler_similarity(dp_key(l.item), dp_key(r.item))"   # 選填：多筆候選時挑分數最高的
        review: true                # 選填：用這個方式配到的列要人確認
    bring: {decl_no: decl_no, decl_amount: amount}   # 新欄位名稱: 右表欄位；不寫就帶全部，名稱是「右表_欄位」
    unmatched: flag                 # 都找不到時：flag（標記，預設）、keep（不標記）、drop（移除這列）
    show: {left: [invoice_no, amount, item], right: [ref_no, amount, item]}   # 選填：配對畫面先顯示的欄位
```

`show` 不寫時，配對畫面先顯示比對條件裡用到的欄位，其他欄位收起來，使用者可以按「顯示全部欄位」。

配對方式（`mode`）：

| mode | 左表一列 | 右表一列 | 例子 |
|---|---|---|---|
| `one_to_one` | 最多對一列 | 只能給一個左表列 | 發票對報關單，一張對一張 |
| `many_to_one`（預設） | 最多對一列 | 可以給多個左表列 | 明細對匯率表、對客戶主檔 |
| `one_to_many` | 可以對多列 | 只能給一個左表列 | 一張發票拆成多張報關單 |
| `many_to_many` | 可以對多列 | 可以給多個左表列 | 多張發票合併申報、互相對沖 |

左表一列可以對多列時（`one_to_many`、`many_to_many`），用 `rows` 決定結果長什麼樣子：

- `rows: expand`（預設）：每一組配對一列。左表一列對到三列，結果就有三列，左表的欄位重複出現。
- `rows: combine`：彙總成一列。`bring` 改寫成彙總運算式：

```yaml
    mode: one_to_many
    rows: combine
    bring:
      decl_nos: "string_agg(r.decl_no, '、' ORDER BY r.decl_no)"
      decl_total: sum(r.amount)
      decl_last_date: max(r.decl_date)
```

彙總結果另外有 `_count_<name>`（對到幾列）。之後可以用 validate 檢查，例如 `abs(amount - decl_total) > 0.01`。

配對規則：

- 左表一列只對一列時：一個方式只找到一筆就配對成功；找到多筆時，有 `best` 且最高分只有一筆才選它，否則標記「待選擇」，由人在介面選擇，不會自動挑。
- 左表一列可以對多列時：同一個方式找到的全部都算（每列最多 200 列，超過會標記，通常代表條件太寬）。
- 右表一列只能給一個左表列時（`one_to_one`、`one_to_many`），同一個右表列同時對到多個左表列，不會替人決定歸屬：那一列會先拿掉並標記，全部被拿掉時標記「待選擇」。
- 人在介面指定的配對（可以加入、移除多列）、或確認「沒有配對」，會優先於所有自動方式，重新執行也保留。
- 寬鬆條件（相似度、只比數字）放在後面，嚴格的放前面。寬鬆的方式建議加 `review: true`。
- 條件盡量包含至少一個等值條件，只有相似度的條件會讓兩張表每一列互相比較，資料多時會很慢（超過 120 秒會中止）。

配對結果表包含左表所有欄位、`bring` 的欄位，以及系統欄位 `_rid_<name>`（右表列代號；combine 時是逗號分隔的多個代號）、`_how_<name>`（用哪個方式配到）、`_status_<name>`（auto、review、manual、none、ambiguous、unmatched）。

## transform：計算

```yaml
transform:
  - name: result
    note: 換算台幣
    sql: |
      SELECT *, round(amount * rate, 0) AS amount_twd,
             CASE WHEN currency = 'TWD' THEN amount ELSE amount * rate END AS amount_base
      FROM with_fx
```

每一步建立一張新表，可以使用前面所有的表。保留 `_rid` 才能標記與修改。

## validate：驗證

```yaml
validate:
  - table: result                   # 選填，預設是 output.from
    where: "decl_amount IS NOT NULL AND abs(amount - decl_amount) > 0.01"   # 成立的列是有問題的列
    message: 發票金額和報關金額不同
    level: review                   # review（需檢查，預設）或 notice（提示，不影響狀態）
    highlight: [金額, 報關金額]      # 標在哪些輸出欄位（用輸出的顯示名稱）
```

## output：輸出

```yaml
output:
  from: result                      # 來源表
  sheet: 整理結果                    # Excel 工作表名稱
  order_by: "inv_date, invoice_no"  # 選填，SQL 排序
  columns:
    - {name: 發票號碼, from: invoice_no}
    - {name: 金額, from: amount, type: number}
    - {name: 運送方式代碼, from: ship_mode, map: ship_mode, required: true}
    - {name: 差額, sql: "amount - decl_amount", type: number}
    - {name: 來源, sql: "'發票'", editable: false}
    - note                          # 簡寫：顯示名稱和來源欄位相同（只限英數欄位名稱）
```

| 設定 | 說明 |
|---|---|
| `from` 或 `sql` | 二擇一。`from` 是來源欄位；`sql` 是運算式 |
| `type` | `text`、`number`、`integer`、`date`，決定 Excel 格式與修改時的檢查 |
| `map` | 輸出前套用對照表 |
| `required` | 空白時標記「需檢查」 |
| `editable` | 預設 `true`；`false` 時介面不能修改 |

用 `from` 直接取自輸入表的欄位，人工修改會在讀進來時就套用，後面的配對、計算、驗證都會用修改後的值重算。用 `sql` 算出來的欄位，修改只改輸出的值。

## 可以用的 SQL

DuckDB 的一般函式都可以用，常用的有：

| 函式 | 用途 |
|---|---|
| `dp_key(x)` | 寬鬆比對鍵：全半形相同、不分大小寫、去掉空白與標點 |
| `dp_digits(x)` | 只留數字，比對單號常用 |
| `jaro_winkler_similarity(a, b)`、`levenshtein(a, b)` | 文字相似度 |
| `regexp_replace(x, 'pattern', '取代', 'g')`、`regexp_matches(x, 'pattern')` | 正規表達式 |
| `coalesce(a, b)`、`CASE WHEN ... THEN ... ELSE ... END` | 條件判斷 |
| `lag(x) OVER (PARTITION BY ... ORDER BY ...)`、`sum(x) OVER (...)` | 前一列、累計 |
| `round(x, 2)`、`abs(x)`、`date_diff('day', a, b)` | 計算 |

不能用：讀寫檔案（`read_csv`、`COPY`、`ATTACH`）、安裝或載入擴充套件、修改設定。這些在沙箱裡都會被擋下。

## 完整範例

見 `examples/workspace/recipes/invoice-declaration.yaml`（工具第一次啟動時會放到 `workspace/recipes`），搭配範例資料 `workspace/samples/範例_發票與報關單.xlsx` 可以直接執行。

## 請 AI 寫 recipe 的提示範例

> 請依照附上的「Recipe 規格」寫一份 recipe。我的 Excel 有兩個工作表：「發票明細」（欄位：發票號碼、日期、品名、金額、幣別、運送方式、狀態）和「報關單」（欄位：報單號碼、發票參考、貨名、申報金額）。規則：作廢的發票不處理；先用發票號碼對報關單的發票參考，對不到時只比數字；運送方式要轉成 AIR、SEA、EXPRESS，看不懂的要讓我補；最後輸出發票號碼、日期、金額、報單號碼，金額不同要標出來。
