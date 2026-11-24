"use strict";
/* 新手導覽、進階說明卡、實地練習與新功能的統一 Spotlight 引擎。
   所有文字都用 textContent 放進畫面，不使用 innerHTML 或 inline event handler。 */
(function () {
  const PREF_KEY = "onboarding.v1";
  const SAVED_WORK_KEY = "dp:savedWork";

  function node(tag, props = {}, ...children) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (v === undefined || v === null || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (k === "dataset") Object.assign(el.dataset, v);
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const child of children.flat()) {
      if (child === null || child === undefined || child === false) continue;
      el.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return el;
  }

  function put(target, ...children) {
    target.replaceChildren(...children.flat().filter((c) => c !== null && c !== undefined && c !== false));
  }

  function defaultPrefs() {
    return {
      dismissed: false,
      journeys: {
        review: { step: null, done: false, skipped: [], flags: {} },
        recipe: { step: null, done: false, skipped: [], flags: {} },
      },
      cardsSeen: [],
      practiceDone: [],
      activeGuide: null,          // 進行中的關卡 A、mission 或 lab 的代號：重新整理後照它續玩
      tipsSeen: { jk: 0, practice: 0, hub: 0 },
      whatsnewSeen: null,
    };
  }

  function statusLegendRow() {
    const items = [
      ["ok", "沒問題"],
      ["review", "需檢查"],
      ["error", "找不到或無法執行"],
      ["manual", "你處理過的"],
    ];
    return node("div", { class: "status-legend" }, items.map(([cls, text]) =>
      node("span", { class: "status-legend-item" },
        node("span", { class: `status-swatch ${cls}`, "aria-hidden": "true" }),
        node("span", { text }))));
  }

  /* 11 張說明卡 + 總覽卡 + whatsnew 專用 spotlight */
  const CARDS = [
    {
      id: "card-trace", group: "review", anchor: "help-trace",
      mission: "mission-trace",
      where: "結果表選一列，在右邊欄位名稱旁按「怎麼來的」，「這一列的處理過程」在細節下方。",
      title: "看這一格是怎麼來的",
      when: "不懂某個值為什麼是這樣",
      example: { before: "USD 3,450.00", after: "金額 3450，幣別另一欄" },
      tryTarget: '[data-guide="issue-trace"]',
      tryTab: "rows",
    },
    {
      id: "card-source", group: "review", anchor: "help-source",
      mission: "mission-source",
      where: "配對卡片上的表格圖示看那一列，要並排比對就到「原始資料」分頁。",
      title: "兩張表並排，找配對的答案",
      when: "找不到配對，想自己翻原始表",
      example: { text: "左邊發票、右邊報關單，橘色「沒用到」就是候選" },
      tryTarget: '[data-guide="match-sheet"]',
      tryTab: "match",
    },
    {
      id: "card-bulk", group: "review", anchor: "help-bulk",
      mission: "mission-bulk",
      where: "「所有警示」分頁，只看同一類之後全選，按「確認無誤」。",
      title: "一次確認很多筆",
      when: "同一類要判斷的警示很多",
      example: { text: "所有警示勾選 → 確認無誤" },
      tryTarget: '.tab[data-tab="issues"]',
      tryTab: "issues",
    },
    {
      id: "card-reset", group: "review", anchor: "help-reset",
      mission: "mission-reset",
      where: "結果表右上的「重新檢查」，清完提示裡有「復原」。",
      title: "清掉重來，按錯可以復原",
      when: "想從頭檢查一次",
      example: { text: "重新檢查 → 清掉 n 項 → 復原" },
      tryTarget: "#resetButton",
      tryTab: "rows",
    },
    {
      id: "card-popout", group: "review", anchor: "help-popout",
      mission: "mission-popout",
      where: "結果表右上的「Pop out」，搬出去的分頁會標 ↗。",
      title: "表格太寬，搬到另一個螢幕",
      when: "欄位多、想兩個螢幕分工",
      example: { text: "結果 Pop out ↗，配對留在主視窗" },
      tryTarget: '[data-guide="popout-btn"]',
      tryTab: "rows",
    },
    {
      id: "lab-gate", group: "recipe", isLab: true, anchor: "help-gate",
      title: "排除不用處理的列",
      when: "有作廢、小計這類不該處理的列",
      example: { before: "狀態 作廢", after: "放進「排除」" },
      specHeading: "gate",
      learned: "在 gate 寫保留條件，不符合的列會放進「排除」分頁",
      step1Action: "「排除」是空的，作廢的也被處理了",
      step1Tip: "點橘色或灰色的 Gate 卡片，看目前排除的列數",
      step1Target: '[data-guide="stage-gate"]',
      step1Tab: "rows",
    },
    {
      id: "lab-mapping", group: "recipe", isLab: true, anchor: "help-mapping",
      title: "各種寫法統一成同一個代碼",
      when: "同一件事有好幾種寫法",
      example: { before: "快遞、Courier", after: "EXPRESS" },
      specHeading: "mappings",
      learned: "對照表把多種寫法統一成標準代碼，之後新檔案也直接套用",
      step1Action: "「快遞」「Courier」不在對照表",
      step1Tip: "切到「對照表」分頁看還沒對上的寫法",
      step1Target: '.tab[data-tab="mapping"]',
      step1Tab: "mapping",
    },
    {
      id: "lab-match", group: "recipe", isLab: true, anchor: "help-match",
      title: "號碼寫法不同也配得到",
      when: "兩邊的單號格式不一樣",
      example: { before: "1004", after: "對 INV-1004" },
      specHeading: "match",
      learned: "比對方式可以排好幾種，前面配不到才換下一種",
      step1Action: "1004 找不到報關單",
      step1Tip: "切到「配對」分頁看 1004 的狀態",
      step1Target: '.tab[data-tab="match"]',
      step1Tab: "match",
    },
    {
      id: "lab-extract", group: "recipe", isLab: true, anchor: "help-extract",
      title: "一格有好幾行，只取需要的那行",
      when: "品名後面接規格、保固",
      example: { before: "電源供應器 500W↵附電源線…", after: "電源供應器 500W" },
      specHeading: "extract",
      learned: "用 extract 先擷取需要的片段，再做後續比對與輸出",
      step1Action: "INV-1003 的品名有三行",
      step1Tip: "點結果表裡 INV-1003 那一列看品名內容",
      step1Row: "INV-1003",
      step1Tab: "rows",
    },
    {
      id: "lab-validate", group: "recipe", isLab: true, anchor: "help-validate",
      title: "數字對不上時提醒我",
      when: "兩張表的金額要一致",
      example: { before: "金額 2,000、報關 2,100", after: "需檢查" },
      specHeading: "validate",
      learned: "在 validate 寫條件與 highlight，對不上的列會自動標成需檢查",
      step1Action: "INV-1003 金額不同卻沒有被標出來",
      step1Tip: "點結果表裡 INV-1003，金額是 2,000、報關金額是 2,100",
      step1Row: "INV-1003",
      step1Tab: "rows",
    },
    {
      id: "card-transform", group: "recipe", isLab: false, anchor: "help-transform",
      mission: "mission-transform",
      where: "細節裡算出來的欄位旁按「怎麼來的」，左欄 recipe 的「查看」有 SQL 原文。",
      title: "用公式算出新欄位",
      when: "換匯、加總、組合欄位",
      example: { before: "金額 × 匯率", after: "台幣金額" },
      specHeading: "transform",
    },
  ];

  const EXTRA_SPOTLIGHTS = {
    "recipe-overview": {
      id: "recipe-overview",
      title: "寫 recipe",
      when: "不需要自己寫 YAML，把規格和欄位交給 AI 寫好再貼回來",
      example: { text: "複製規格給 AI → 貼回 → 看說明 → 儲存" },
      anchor: "help-ai-recipe",
      group: "overview",
    },
    "help-menu": {
      id: "help-menu",
      title: "說明選單",
      target: "#helpBtn",
      pointer: "說明選單",
      action: "導覽、進階功能、練習與手冊都在右上角",
      tip: "點「說明 ▾」隨時打開",
    },
    "practice-center": {
      id: "practice-center",
      title: "進階功能練習中心",
      target: "#helpBtn",
      pointer: "說明選單",
      action: "11 項進階功能，用範例資料一項項練",
      tip: "點「說明 ▾」的「練習中心」",
    },
    "help-labs": {
      id: "help-labs",
      title: "寫 recipe 的實地練習",
      target: "#helpBtn",
      pointer: "打開實地練習",
      action: "改一小段 recipe，試算確認做對",
      tip: "從「說明 ▾」的「寫 recipe」選任一項開始",
    },
  };

  /* 依標題欄位（發票號碼等）找列，不寫死 _rid */
  function findRowByTitle(result, title) {
    if (!result?.output?.rows) return null;
    const firstCol = result.output.columns?.[0]?.name;
    return result.output.rows.find((r) => {
      if (firstCol && String(r.values?.[firstCol] ?? "") === title) return true;
      return Object.values(r.values || {}).some((v) => String(v ?? "") === title);
    }) || null;
  }

  function findMatchRowByTitle(result, matchName, title) {
    const m = result?.matches?.find((x) => x.name === matchName);
    if (!m) return null;
    for (const row of m.rows) {
      const left = m.left_rows[row.left];
      const text = (m.left_title || []).map((k) => left?.values?.[k]).filter(Boolean).join("・");
      if (text === title) return { match: m, row };
    }
    return null;
  }

  function findRightRidByTitle(match, title) {
    if (!match) return null;
    for (const [rid, rec] of Object.entries(match.right_rows || {})) {
      const text = (match.right_title || []).map((k) => rec?.values?.[k]).filter(Boolean).join("・");
      if (text === title) return rid;
    }
    return null;
  }

  /* 還沒處理的配對（卡片上的「需處理」）：依卡片順序，附上左邊那一列的標題 */
  function pendingMatches(result) {
    const out = [];
    for (const match of result?.matches || []) {
      for (const row of match.rows) {
        if (!row.open) continue;
        const left = match.left_rows[row.left];
        const title = (match.left_title || []).map((k) => left?.values?.[k]).filter(Boolean).join("・");
        out.push({ match, row, title });
      }
    }
    return out;
  }

  /* 結果裡還需要檢查的列數（進度條上的「需檢查」） */
  function reviewRowsLeft(result) {
    return (result?.output?.rows || []).filter((r) => r.status === "review").length;
  }

  /* 第 8 步：現在要處理哪一張配對卡片，行動句、提醒、目標與浮標都跟著它走 */
  function matchStepInfo(ctx) {
    const mistake = matchMistakes(ctx.state.result)[0];
    if (mistake) {
      return {
        action: `${mistake.title} 處理錯了，按「交回自動」復原`,
        tip: mistake.message,
        target: `[data-guide="match-revert"][data-rid="${CSS.escape(mistake.row.left)}"]`,
        pointer: "交回自動",
      };
    }
    const first = pendingMatches(ctx.state.result)[0];
    if (!first) return { action: "配對都處理完了", tip: "", target: null, pointer: "" };
    const { match, row, title } = first;
    const left = CSS.escape(row.left);
    if (row.status === "review") {
      return {
        action: row.candidates?.length > 1 || row.rights.length !== 1
          ? `${title} 的配對要確認，按「確認正確」`
          : `${title} 只剩一筆候選，按「確認正確」`,
        tip: "人工指定後剩下的候選也要你確認",
        target: `[data-guide="match-confirm"][data-rid="${left}"]`,
        pointer: "確認正確",
      };
    }
    if (row.status === "ambiguous" && row.candidates?.length) {
      return {
        action: `${title} 有多筆候選，選一筆`,
        tip: "比對候選之間不一樣的欄位再選",
        target: `[data-guide="pick"][data-left="${left}"][data-rid="${CSS.escape(row.candidates[0].rid)}"]`,
        pointer: "選這筆",
      };
    }
    return {
      action: `${title} 沒有${match.right_label}，按「沒有配對」`,
      tip: `先確認對面沒有合適的列，原因例如「這張${match.left_label}沒有出口報關」`,
      target: `[data-guide="match-none"][data-rid="${left}"]`,
      pointer: "沒有配對",
    };
  }

  let matchRecovery = false;

  /* 第 8 步的標準答案（範例資料，見規格附錄 A）：INV-1005、INV-1006 沒有報關單；INV-1010 對得上 AA15A0006 */
  const MATCH_ANSWERS = [
    { title: "INV-1005", want: "none" },
    { title: "INV-1006", want: "none" },
    { title: "INV-1010", want: "confirm", right: "AA15A0006" },
  ];

  /* 已經處理過、但結果和答案不一致的配對：要先「交回自動」再做對 */
  function matchMistakes(result) {
    const out = [];
    for (const ans of MATCH_ANSWERS) {
      const found = findMatchRowByTitle(result, "inv_decl", ans.title);
      if (!found || found.row.open) continue;
      const { match, row } = found;
      const rightRid = ans.right ? findRightRidByTitle(match, ans.right) : null;
      const ok = ans.want === "none"
        ? row.status === "none"
        : row.status === "confirmed" && Boolean(rightRid) && (row.rights || []).includes(rightRid);
      if (ok) continue;
      const picked = (row.rights || []).map((rid) => (match.right_title || []).map((k) => match.right_rows?.[rid]?.values?.[k]).filter(Boolean).join("・")).filter(Boolean).join("、");
      let message;
      if (ans.want === "none") {
        message = `${ans.title} 被指定配對到 ${picked || "一筆報關單"} 了，它其實沒有對應的報關單。按「交回自動」復原，再按「沒有配對」`;
      } else if (row.status === "none") {
        message = `${ans.title} 標成沒有配對了，它其實對得上 ${ans.right}。按「交回自動」復原，再按「確認正確」`;
      } else {
        message = `${ans.title} 配到${picked ? ` ${picked}` : "別筆"}了，它其實對得上 ${ans.right}。按「交回自動」復原，再按「確認正確」`;
      }
      out.push({ match, row, title: ans.title, message });
    }
    return out;
  }

  /* 第 9 步：選到的列有一定要處理的警示時，浮標改指那個警示的動作 */
  function reviewBlocker(ctx) {
    const result = ctx.state.result;
    const row = result?.output?.rows?.find((r) => r.rid === ctx.state.selected);
    if (!row || ctx.state.tab !== "rows" || !ctx.bridge.openIssues) return null;
    const issue = ctx.bridge.openIssues(row).find((i) => ctx.bridge.mustHandle(i));
    if (!issue) return null;
    const col = issue.out_columns?.[0] || issue.column || "";
    const type = result.output.columns.find((c) => c.name === col)?.type;
    const field = col ? `#drawer [data-guide="field-${CSS.escape(col)}"][data-rid="${CSS.escape(row.rid)}"]` : null;
    if (issue.code === "parse" || issue.code === "extract") {
      const want = type === "number" || type === "integer" ? "數字" : type === "date" ? "日期" : "能讀的值";
      return { target: field, pointer: "改這一格", tip: `${col}讀不懂，改成${want}後按 Enter` };
    }
    if (issue.code === "required") return { target: field, pointer: "補這一格", tip: `${col}是必填，補上後按 Enter` };
    if (issue.code === "unmapped") {
      return { target: '#drawer [data-guide="map-select"]', pointer: "選對應值", tip: "這個寫法不在對照表，選一個對應值，或新增對應值再補上對照" };
    }
    if (String(issue.code).startsWith("match_")) {
      return { target: '#drawer [data-guide="issue-goto-match"]', pointer: "前往配對", tip: "配對還沒處理好，到配對分頁選候選或按「沒有配對」" };
    }
    return { target: '#drawer [data-guide="foot-todo"]', pointer: "先處理警示", tip: issue.message };
  }

  /* 還沒看完就按了下載：提醒還剩幾列 */
  function unfinishedRowsWarning(ctx) {
    const n = reviewRowsLeft(ctx.state.result);
    return n > 0 ? `還有 ${n} 列沒看，看完再下載` : null;
  }

  function rowValidateIssues(result, row) {
    if (!result || !row) return [];
    return (row.issues || []).map((i) => result.issues[i]).filter((i) => i && i.stage === "validate");
  }

  /* 關卡 A：核對一份資料（10 步） */
  const JOURNEY_REVIEW = {
    id: "review",
    title: "核對一份資料",
    steps: [
      {
        id: "review-1",
        journey: "review",
        title: "執行",
        action: "按「執行」處理範例資料",
        tip: "10 張發票要對 7 張報關單",
        target: "#runButton",
        pointer: "按這裡執行",
        done: (ctx) => ctx.state.result?.demo === true,
      },
      {
        id: "review-2",
        journey: "review",
        needs: "demoResult",
        title: "看流程卡片",
        action: "點橘色的「Match」卡片看摘要",
        tipLegend: true,
        target: '[data-guide="stage-match"]',
        frame: true,
        done: (ctx) => Boolean(ctx.flags.sawStage),
      },
      {
        id: "review-3",
        journey: "review",
        needs: "demoResult",
        title: "看懂再確認",
        setup: (ctx) => {
          const row = findRowByTitle(ctx.state.result, "INV-1003");
          if (row && (ctx.state.tab !== "rows" || ctx.state.selected !== row.rid)) {
            if (ctx.state.tab !== "rows") { ctx.state.tab = "rows"; ctx.state.filter = "review"; }
            ctx.bridge.selectRow(row.rid);
          }
        },
        sub: [
          {
            id: "review-3-1",
            action: "按警示上的「怎麼判斷的」",
            tip: "規則和這一列用到的值都會列出",
            target: (ctx) => {
              const row = findRowByTitle(ctx.state.result, "INV-1003");
              return row ? `[data-guide="issue-trace"][data-rid="${CSS.escape(row.rid)}"]` : '[data-guide="issue-trace"]';
            },
            pointer: "看怎麼判斷的",
            done: (ctx) => Boolean(ctx.flags.sawTrace) || (() => {
              const row = findRowByTitle(ctx.state.result, "INV-1003");
              const issues = rowValidateIssues(ctx.state.result, row);
              return issues.length > 0 && issues.every((i) => i.dismissed);
            })(),
          },
          {
            id: "review-3-2",
            action: "按「確認無誤，下一筆」",
            tip: "範例當作已向業務確認，差額沒問題",
            target: '[data-guide="confirm-next"]',
            pointer: "確認無誤，下一筆",
            done: (ctx) => {
              const row = findRowByTitle(ctx.state.result, "INV-1003");
              if (!row) return false;
              const issues = rowValidateIssues(ctx.state.result, row);
              return issues.length > 0 && issues.every((i) => i.dismissed);
            },
          },
        ],
        wrong: (ctx) => {
          const row = findRowByTitle(ctx.state.result, "INV-1003");
          if (row && "金額" in (row.edited || {})) return "改過也可以，這一步算完成";
          return null;
        },
        done: (ctx) => {
          const row = findRowByTitle(ctx.state.result, "INV-1003");
          if (!row) return false;
          if ("金額" in (row.edited || {})) return true;
          const issues = rowValidateIssues(ctx.state.result, row);
          return issues.length > 0 && issues.every((i) => i.dismissed && !i.resolved);
        },
      },
      {
        id: "review-4",
        journey: "review",
        needs: "demoResult",
        title: "修改讀不懂的值",
        setup: (ctx) => {
          const row = findRowByTitle(ctx.state.result, "INV-1006");
          if (!row) return;
          if (ctx.state.tab !== "rows" || ctx.state.selected !== row.rid) {
            ctx.state.tab = "rows";
            ctx.bridge.selectRow(row.rid);
          }
          requestAnimationFrame(() => {
            const el = document.querySelector(`[data-guide="field-金額"][data-rid="${CSS.escape(row.rid)}"]`);
            if (el && document.activeElement !== el) el.scrollIntoView({ block: "nearest" });
          });
        },
        action: "把「約 300」改成 300，按 Enter",
        tip: "原值會保留，按「還原」可以改回",
        outline: (ctx) => {
          const row = findRowByTitle(ctx.state.result, "INV-1006");
          if (!row) return null;
          return document.querySelector(`[data-guide="field-金額"][data-rid="${CSS.escape(row.rid)}"]`);
        },
        wrong: (ctx) => {
          const bad = ctx.flags.badEdit;
          if (bad && bad.column === "金額") {
            const shown = bad.value === "" ? "空白" : `「${bad.value}」`;
            return `現在是${shown}，金額只能是數字，改成 300`;
          }
          return null;
        },
        done: (ctx) => {
          const row = findRowByTitle(ctx.state.result, "INV-1006");
          return Boolean(row && Number(row.values?.["金額"]) === 300 && "金額" in (row.edited || {}));
        },
      },
      {
        id: "review-5",
        journey: "review",
        needs: "demoResult",
        title: "補對照",
        setup: (ctx) => {
          const row = findRowByTitle(ctx.state.result, "INV-1005");
          if (!row) return;
          if (ctx.state.tab !== "rows" || ctx.state.selected !== row.rid) {
            ctx.state.tab = "rows";
            ctx.bridge.selectRow(row.rid);
          }
        },
        sub: [
          {
            id: "review-5-1",
            action: "對應值選「新增對應值」",
            tip: "陸運不是空運、海運或快遞",
            target: '#drawer [data-guide="map-select"]',
            pointer: "選新增對應值",
            done: (ctx) => {
              const sel = document.querySelector('#drawer [data-guide="map-select"]');
              return Boolean(sel && sel.value === "__new");
            },
          },
          {
            id: "review-5-2",
            action: "輸入 LAND",
            tip: "代碼用英文大寫，和其他代碼一樣",
            target: '#drawer [data-guide="map-new"]',
            pointer: "輸入 LAND",
            done: (ctx) => {
              const val = (ctx.flags.mapNewCommitted || "").trim();
              if (!val) return false;
              const existing = new Set(["AIR", "SEA", "EXPRESS"]);
              return !existing.has(val.toUpperCase());
            },
          },
          {
            id: "review-5-3",
            action: "按「補上對照」",
            tip: "實際使用時，之後的檔案也會套用",
            target: '#drawer [data-guide="map-save"]',
            pointer: "補上對照",
            done: (ctx) => {
              const m = ctx.state.result?.mappings?.find((x) => x.name === "ship_mode");
              if (!m) return false;
              const added = (m.added || []).find((a) => a.raw === "陸運");
              return Boolean(added && (m.custom_values || []).includes(added.target));
            },
          },
        ],
        wrong: (ctx) => {
          const m = ctx.state.result?.mappings?.find((x) => x.name === "ship_mode");
          const added = (m?.added || []).find((a) => a.raw === "陸運");
          if (added && !(m.custom_values || []).includes(added.target)) {
            return `陸運存成 ${added.target} 了，到「對照表」分頁移除再補一次`;
          }
          const sel = document.querySelector('#drawer [data-guide="map-select"]');
          if (sel && sel.value && sel.value !== "__new") {
            return `選了 ${sel.value}，陸運不是這個方式，改選「新增對應值」`;
          }
          return null;
        },
        done: (ctx) => {
          const m = ctx.state.result?.mappings?.find((x) => x.name === "ship_mode");
          if (!m) return false;
          const added = (m.added || []).find((a) => a.raw === "陸運");
          return Boolean(added && (m.custom_values || []).includes(added.target));
        },
      },
      {
        id: "review-6",
        journey: "review",
        needs: "demoResult",
        title: "選配對候選",
        tabNeeded: "match",
        setup: (ctx) => {
          const found = findMatchRowByTitle(ctx.state.result, "inv_decl", "INV-1009");
          if (!found) return;
          if (ctx.state.tab !== "match" || ctx.state.matchName !== "inv_decl") {
            ctx.bridge.goTo({ tab: "match", matchName: "inv_decl", matchFilter: "all", matchFocus: null, matchSearch: "" });
          }
        },
        action: "選申報日期較近的 AA15A0005",
        tip: "兩筆品名金額都一樣，用日期判斷",
        target: (ctx) => {
          const found = findMatchRowByTitle(ctx.state.result, "inv_decl", "INV-1009");
          if (!found) return null;
          const rightRid = findRightRidByTitle(found.match, "AA15A0005");
          if (!rightRid) return null;
          return `[data-guide="pick"][data-left="${CSS.escape(found.row.left)}"][data-rid="${CSS.escape(rightRid)}"]`;
        },
        frame: true,
        wrong: (ctx) => {
          const found = findMatchRowByTitle(ctx.state.result, "inv_decl", "INV-1009");
          if (!found) return null;
          const wrongRid = findRightRidByTitle(found.match, "AA15A0006");
          if (wrongRid && (found.row.rights || []).includes(wrongRid)) {
            return "選到 AA15A0006（1/15），改選 1/14 的 AA15A0005；先按「交回自動」";
          }
          return null;
        },
        done: (ctx) => {
          const found = findMatchRowByTitle(ctx.state.result, "inv_decl", "INV-1009");
          if (!found) return false;
          const rightRid = findRightRidByTitle(found.match, "AA15A0005");
          return Boolean(rightRid && found.row.status === "manual" && (found.row.rights || []).includes(rightRid));
        },
      },
      {
        id: "review-7",
        journey: "review",
        needs: "demoResult",
        title: "回原始資料找答案",
        tabNeeded: "match",
        setup: (ctx) => {
          if (ctx.state.tab !== "match" || ctx.state.matchName !== "inv_decl") {
            ctx.bridge.goTo({ tab: "match", matchName: "inv_decl", matchFilter: "all", matchFocus: null, matchSearch: "" });
          }
        },
        sub: [
          {
            id: "review-7-1",
            action: "按配對卡片的表格圖示看原始表",
            tip: "右邊橘色「沒用到」的就是剩下的候選",
            target: (ctx) => {
              const found = findMatchRowByTitle(ctx.state.result, "inv_decl", "INV-1008");
              return found ? `[data-guide="match-sheet"][data-rid="${CSS.escape(found.row.left)}"]` : '[data-guide="match-sheet"]';
            },
            pointer: "看原始表",
            done: (ctx) => Boolean(ctx.flags.sawSource),
          },
          {
            id: "review-7-2",
            action: "沒有合適的，按「沒有配對」",
            tip: "沒用到的 AA15A0007 寫的是 INV-1099",
            target: (ctx) => {
              const found = findMatchRowByTitle(ctx.state.result, "inv_decl", "INV-1008");
              return found ? `[data-guide="match-none"][data-rid="${CSS.escape(found.row.left)}"]` : '[data-guide="match-none"]';
            },
            pointer: "沒有配對",
            done: (ctx) => {
              const found = findMatchRowByTitle(ctx.state.result, "inv_decl", "INV-1008");
              return Boolean(found && found.row.status === "none");
            },
          },
        ],
        done: (ctx) => {
          const found = findMatchRowByTitle(ctx.state.result, "inv_decl", "INV-1008");
          if (!found || found.row.status !== "none") return false;
          // 在 popout 視窗直接處理時也允許完成
          return Boolean(ctx.flags.sawSource || ctx.flags.remoteUpdated);
        },
      },
      {
        id: "review-8",
        journey: "review",
        needs: "demoResult",
        title: "把配對做完",
        tabNeeded: "match",
        setup: (ctx) => {
          const first = pendingMatches(ctx.state.result)[0];
          if (!first) return;
          // 只列「需處理」：處理完的卡片會離開清單，剩下的就是還要做的
          if (ctx.state.tab !== "match" || ctx.state.matchName !== first.match.name || ctx.state.matchFilter !== "todo") {
            ctx.bridge.goTo({ tab: "match", matchName: first.match.name, matchFilter: "todo", matchFocus: null, matchSearch: "" });
          }
        },
        action: (ctx) => matchStepInfo(ctx).action,
        tip: (ctx) => matchStepInfo(ctx).tip,
        target: (ctx) => matchStepInfo(ctx).target,
        pointer: (ctx) => matchStepInfo(ctx).pointer,
        // 處理錯的卡片會離開「需處理」清單：有錯時切到「全部」並只留那一張，浮標才指得到「交回自動」
        keepVisible: (ctx) => {
          const mistake = matchMistakes(ctx.state.result)[0];
          const st = ctx.state;
          if (mistake) {
            matchRecovery = true;
            if (st.tab !== "match" || st.matchName !== mistake.match.name || st.matchFilter !== "all" || st.matchFocus !== mistake.row.left) {
              ctx.bridge.goTo({ tab: "match", matchName: mistake.match.name, matchFilter: "all", matchFocus: mistake.row.left, matchSearch: "" });
            }
          } else if (matchRecovery) {
            matchRecovery = false;
            if (st.tab === "match" && st.matchFilter === "all") {
              ctx.bridge.goTo({ tab: "match", matchName: st.matchName, matchFilter: "todo", matchFocus: null, matchSearch: "" });
            }
          }
        },
        wrong: (ctx) => matchMistakes(ctx.state.result)[0]?.message || (ctx.flags.exportedEarly ? unfinishedRowsWarning(ctx) : null),
        done: (ctx) => Boolean(ctx.state.result?.demo) && pendingMatches(ctx.state.result).length === 0 && matchMistakes(ctx.state.result).length === 0,
      },
      {
        id: "review-9",
        journey: "review",
        needs: "demoResult",
        title: "把剩下的列看完",
        tabNeeded: "rows",
        setup: (ctx) => {
          const rows = ctx.state.result?.output?.rows || [];
          const cur = rows.find((r) => r.rid === ctx.state.selected);
          if (ctx.state.tab === "rows" && cur?.status === "review") return;
          const first = rows.find((r) => r.status === "review");
          if (!first) return;
          ctx.state.tab = "rows";
          ctx.state.filter = "review";
          ctx.bridge.selectRow(first.rid);
        },
        action: (ctx) => `按「確認無誤，下一筆」看完剩下 ${reviewRowsLeft(ctx.state.result)} 列`,
        tip: (ctx) => {
          const blocker = reviewBlocker(ctx);
          return blocker ? blocker.tip : `還有 ${reviewRowsLeft(ctx.state.result)} 列，進度條滿了就能下載`;
        },
        target: (ctx) => {
          const blocker = reviewBlocker(ctx);
          if (blocker) return blocker.target;
          if (document.querySelector('#drawer [data-guide="confirm-next"]')) return '[data-guide="confirm-next"]';
          const first = (ctx.state.result?.output?.rows || []).find((r) => r.status === "review");
          return first ? `table.grid tbody tr[data-rid="${CSS.escape(first.rid)}"]` : null;
        },
        pointer: (ctx) => {
          const blocker = reviewBlocker(ctx);
          if (blocker) return blocker.pointer;
          return document.querySelector('#drawer [data-guide="confirm-next"]') ? "確認無誤，下一筆" : "點這一列";
        },
        wrong: (ctx) => {
          const bad = ctx.flags.badEdit;
          if (bad && bad.column) {
            const type = ctx.state.result?.output?.columns?.find((c) => c.name === bad.column)?.type;
            const want = type === "number" ? "數字" : type === "integer" ? "整數" : type === "date" ? "日期" : "合法的值";
            const shown = bad.value === "" ? "空白" : bad.value;
            return `${bad.column}只能是${want}，${shown} 存不進去，改回${want}後按 Enter`;
          }
          return ctx.flags.exportedEarly ? unfinishedRowsWarning(ctx) : null;
        },
        done: (ctx) => Boolean(ctx.state.result?.demo) && reviewRowsLeft(ctx.state.result) === 0,
      },
      {
        id: "review-10",
        journey: "review",
        needs: "demoResult",
        title: "下載",
        action: "按右上角「下載 Excel」",
        tip: "檔名會加「示範_」，和正式檔案分開",
        target: "#exportButton",
        pointer: "下載 Excel",
        wrong: unfinishedRowsWarning,
        done: (ctx) => Boolean(ctx.flags.demoExported),
      },
    ],
  };

  /* 關卡 B：放入 recipe（5 步） */
  const JOURNEY_RECIPE = {
    id: "recipe",
    title: "放入 recipe",
    steps: [
      {
        id: "recipe-1",
        journey: "recipe",
        title: "打開新增",
        action: "按 Recipe 旁的「新增」",
        tip: "recipe 寫好資料怎麼讀、怎麼配對",
        target: "#newRecipe",
        pointer: "新增 recipe",
        done: (ctx) => Boolean(ctx.flags.openedRecipeDialog),
      },
      {
        id: "recipe-2",
        journey: "recipe",
        needs: "recipeDialog",
        title: "複製規格",
        action: "按「複製規格給 AI」",
        tip: "實際使用時連同欄位與規則貼給 AI",
        target: '[data-guide="spec-copy"]',
        pointer: "複製規格給 AI",
        done: (ctx) => Boolean(ctx.flags.copiedSpec),
      },
      {
        id: "recipe-3",
        journey: "recipe",
        needs: "recipeDialog",
        title: "貼上 AI 的回覆",
        action: "按「幫我貼上練習回覆」，再按下一步",
        tip: "這份回覆故意留了 2 個問題",
        assist: {
          label: "幫我貼上練習回覆",
          run: async (ctx) => {
            const data = await ctx.bridge.api("/api/demo/recipe/recipe-draft");
            const area = document.querySelector("#dialogBody textarea");
            if (area) {
              area.value = data.text;
              ctx.flags.pastedDraft = true;
              ctx.schedule();
            }
          },
        },
        target: (ctx) => (ctx.flags.pastedDraft ? '[data-guide="recipe-next"]' : '[data-guide="dialog-assist"]'),
        pointer: (ctx) => (ctx.flags.pastedDraft ? "下一步" : "貼上練習回覆"),
        done: (ctx) => Boolean(ctx.flags.sawProblems),
      },
      {
        id: "recipe-4",
        journey: "recipe",
        needs: "recipeDialog",
        title: "修正問題",
        sub: [
          {
            id: "recipe-4-1",
            action: "按「複製問題給 AI」",
            tip: "問題附行號，AI 看得懂",
            target: '[data-guide="problems-copy"]',
            pointer: "複製問題",
            done: (ctx) => Boolean(ctx.flags.copiedProblems),
          },
          {
            id: "recipe-4-2",
            action: "按「幫我貼上修正版」，再按下一步",
            tip: "實際使用時貼 AI 改好的版本",
            assist: {
              label: "幫我貼上修正版",
              run: async (ctx) => {
                const data = await ctx.bridge.api("/api/demo/recipe/recipe-fixed");
                const area = document.querySelector("#dialogBody textarea");
                if (area) {
                  area.value = data.text;
                  ctx.flags.pastedFixed = true;
                  ctx.schedule();
                }
              },
            },
            target: (ctx) => (ctx.flags.pastedFixed ? '[data-guide="recipe-next"]' : '[data-guide="dialog-assist"]'),
            pointer: (ctx) => (ctx.flags.pastedFixed ? "下一步" : "貼上修正版"),
            done: (ctx) => Boolean(ctx.flags.sawExplain),
          },
        ],
        done: (ctx) => Boolean(ctx.flags.sawExplain),
      },
      {
        id: "recipe-5",
        journey: "recipe",
        needs: "recipeDialog",
        title: "看說明再儲存",
        action: "讀完說明，按「確認並儲存」",
        tip: "每一列會經過哪些判斷都寫在這裡",
        target: '[data-guide="recipe-save"]',
        pointer: "確認並儲存",
        done: (ctx) => Boolean(ctx.flags.practiceSaved && ctx.state.recipes.some((r) => r.practice === true)),
      },
    ],
  };

  const JOURNEYS = { review: JOURNEY_REVIEW, recipe: JOURNEY_RECIPE };

  /* ---------- 進階功能的小關卡（mission，4.1）：同一個 Spotlight 引擎，用範例資料，最後一步綁真實狀態 ---------- */
  const NUL = "\u0000";

  /* 條件成立過一次就記住，之後使用者離開那個畫面也不退回前一步 */
  function sticky(ctx, key, cond) {
    if (cond) ctx.flags[key] = true;
    return Boolean(ctx.flags[key]);
  }

  const traceRow = (result) => findRowByTitle(result, "INV1002") || findRowByTitle(result, "INV-1002");
  const rowSelector = (row) => (row ? `table.grid tbody tr[data-rid="${CSS.escape(row.rid)}"]` : null);
  const selectedRow = (ctx) => ctx.state.result?.output?.rows?.find((r) => r.rid === ctx.state.selected) || null;
  const chipByText = (text) => [...document.querySelectorAll("#tabBody .chip")].find((b) => b.textContent.trim() === text) || null;
  const explainCodeSummary = () => {
    for (const body of document.querySelectorAll("#dialog .flow-body")) {
      if ((body.querySelector(".flow-text")?.textContent || "").startsWith("計算")) {
        const s = body.querySelector(":scope > details.explain-code > summary");
        if (s) return s;
      }
    }
    return null;
  };
  const goRowsAll = (ctx) => {
    if (ctx.state.tab !== "rows" || ctx.state.filter !== "all") ctx.bridge.goTo({ tab: "rows", filter: "all" });
  };
  const goMatchTodo = (ctx) => {
    ctx.bridge.goTo({ tab: "match", matchName: "inv_decl", matchFilter: "todo", matchFocus: null, matchSearch: "", pickerFor: null });
  };
  const bulkIssues = (ctx) => {
    const code = ctx.flags.bulkCode;
    return code ? (ctx.state.result?.issues || []).filter((i) => i.code === code && i.level !== "skip") : [];
  };

  const MISSION_TRACE = {
    id: "mission-trace", title: "看這一格是怎麼來的", isMission: true, ephemeral: true,
    learned: "「怎麼來的」從原始儲存格一路列到結果，不懂某個值時先看這裡",
    steps: [
      {
        id: "trace-1", journey: "mission-trace", title: "打開一列",
        setup: goRowsAll,
        action: "點結果表裡的 INV1002 這一列",
        tip: "原始 Excel 寫的是「inv 1002」，整理後變成 INV1002",
        target: (ctx) => rowSelector(traceRow(ctx.state.result)), frame: true,
        done: (ctx) => sticky(ctx, "t1", Boolean(traceRow(ctx.state.result)) && ctx.state.selected === traceRow(ctx.state.result).rid),
      },
      {
        id: "trace-2", journey: "mission-trace", title: "按「怎麼來的」",
        setup: (ctx) => {
          const row = traceRow(ctx.state.result);
          if (row && ctx.state.selected !== row.rid) { goRowsAll(ctx); ctx.bridge.selectRow(row.rid); }
        },
        action: "把滑鼠移到「金額」欄名，按「怎麼來的」",
        tip: "會列出這一格從原始儲存格到結果的每一步",
        target: '#drawer [data-guide="why-金額"]', pointer: "怎麼來的", reveal: true,
        done: (ctx) => {
          const row = traceRow(ctx.state.result);
          return sticky(ctx, "t2", Boolean(row) && ctx.state.openTrace.has(`${row.rid}${NUL}金額`));
        },
      },
      {
        id: "trace-3", journey: "mission-trace", title: "看原始寫法",
        setup: (ctx) => {
          if (ctx.flags.t3) return;
          // 來由顯示至少 600ms 才算看過（點了原始儲存格位置也算）
          setTimeout(() => {
            const row = traceRow(engine.bridge.state.result);
            if (engine.stepId === "trace-3" && row && engine.bridge.state.openTrace.has(`${row.rid}${NUL}金額`)) {
              engine.flags.t3 = true;
              engine.schedule();
            }
          }, 600);
        },
        action: "看原始寫法「USD 3,450.00」，和整理後的 3,450",
        tip: "讀完再往下，或點旁邊的儲存格位置看原始 Excel",
        outline: () => document.querySelector('#drawer [data-guide="why-金額"]')?.closest(".field")?.querySelector("ol.trace") || null,
        done: (ctx) => sticky(ctx, "t3", Boolean(ctx.flags.sawCell)),
      },
      {
        id: "trace-4", journey: "mission-trace", title: "看處理過程", noSkip: true,
        action: "展開「這一列的處理過程」，看配對試了哪些方式",
        tip: "從這一列的來源、篩選、配對到檢查，一步一步列出來",
        target: '#drawer [data-guide="row-trace"]', pointer: "展開",
        done: (ctx) => {
          const row = traceRow(ctx.state.result);
          const data = row && ctx.state.traces[row.rid];
          return Boolean(row && ctx.state.openTrace.has(`${row.rid}${NUL}*`) && data?.steps?.some((line) => /配|用「/.test(line)));
        },
      },
    ],
  };

  const MISSION_SOURCE = {
    id: "mission-source", title: "兩張表並排，找配對的答案", isMission: true, ephemeral: true,
    learned: "找不到配對時，把兩張原始表並排看，橘色是沒人用的候選，確定沒有就按「沒有配對」",
    steps: [
      {
        id: "source-1", journey: "mission-source", title: "到配對分頁",
        action: "切到「配對」分頁，找 INV-1008",
        tip: "INV-1008 每種方式都找不到報關單",
        target: '.tab[data-tab="match"]', pointer: "配對",
        done: (ctx) => sticky(ctx, "s1", ctx.state.tab === "match"),
      },
      {
        id: "source-2", journey: "mission-source", title: "並排看原始資料",
        setup: (ctx) => { if (ctx.state.tab !== "match") goMatchTodo(ctx); },
        sub: [
          {
            action: "按 INV-1008 卡片上的表格圖示",
            tip: "會在旁邊跳出原始 Excel 的那一列",
            target: (ctx) => {
              const found = findMatchRowByTitle(ctx.state.result, "inv_decl", "INV-1008");
              return found ? `.match-card[data-rid="${CSS.escape(found.row.left)}"] [data-guide="match-sheet"]` : null;
            },
            pointer: "看原始資料",
            done: (ctx) => Boolean(ctx.flags.sawSource) || ctx.state.tab === "source",
          },
          {
            action: "按小卡上的「完整工作表」",
            tip: "整張原始工作表會在「原始資料」分頁打開",
            target: '#peek [data-guide="peek-full"]', pointer: "完整工作表",
            done: (ctx) => ctx.state.tab === "source",
          },
          {
            action: "按「左右並排」，把兩張表放在一起",
            tip: "左邊發票、右邊報關單",
            target: '[data-guide="source-split"]', pointer: "左右並排",
            done: (ctx) => ctx.state.tab === "source" && Boolean(ctx.state.source2),
          },
        ],
        done: (ctx) => sticky(ctx, "s2", ctx.state.tab === "source" && Boolean(ctx.state.source2)),
      },
      {
        id: "source-3", journey: "mission-source", title: "看沒用到的列",
        setup: (ctx) => { if (ctx.state.tab !== "source") ctx.bridge.goTo({ tab: "source" }); },
        action: "點右邊橘色「沒用到」的其中一列",
        tip: "沒有任何發票配到它們，可能是答案，也可能都不對",
        target: '.source-pane tr[data-unused="1"] td.mark', pointer: "沒用到",
        done: (ctx) => Boolean(ctx.flags.unusedClick),
      },
      {
        id: "source-4", journey: "mission-source", title: "回到配對做決定", noSkip: true,
        setup: goMatchTodo,
        action: "沒有合適的，按 INV-1008 的「沒有配對」",
        tip: "確定沒有對應的報關單，就明確告訴工具",
        target: (ctx) => {
          const found = findMatchRowByTitle(ctx.state.result, "inv_decl", "INV-1008");
          return found ? `[data-guide="match-none"][data-rid="${CSS.escape(found.row.left)}"]` : null;
        },
        pointer: "沒有配對",
        done: (ctx) => findMatchRowByTitle(ctx.state.result, "inv_decl", "INV-1008")?.row?.status === "none",
      },
    ],
  };

  const MISSION_BULK = {
    id: "mission-bulk", title: "一次確認很多筆", isMission: true, ephemeral: true,
    learned: "同一類要人判斷的警示可以全選一次確認，到「已處理」看得到紀錄",
    steps: [
      {
        id: "bulk-1", journey: "mission-bulk", title: "打開所有警示",
        action: "切到「所有警示」分頁",
        tip: "所有列的警示都集中在這裡",
        target: '.tab[data-tab="issues"]', pointer: "所有警示",
        done: (ctx) => sticky(ctx, "b1", ctx.state.tab === "issues"),
      },
      {
        id: "bulk-2", journey: "mission-bulk", title: "挑一類警示",
        sub: [
          {
            action: "點「Validate」卡片",
            tip: "驗證裡有兩列金額和報關金額不同，這是要人判斷的一類",
            target: '[data-guide="stage-validate"]', frame: true,
            done: (ctx) => ctx.state.stageOpen === "validate" || Boolean(ctx.state.issueFocus?.code),
          },
          {
            action: "按「發票金額和報關金額不同」旁的「查看」",
            tip: "只看這一類，才能放心一次確認",
            target: '#stageDetail [data-guide="stage-link"][data-code]', pointer: "查看",
            done: (ctx) => ctx.state.tab === "issues" && Boolean(ctx.state.issueFocus?.code),
          },
        ],
        done: (ctx) => {
          if (ctx.state.tab === "issues" && ctx.state.issueFocus?.code) ctx.flags.bulkCode = ctx.state.issueFocus.code;
          return Boolean(ctx.flags.bulkCode);
        },
      },
      {
        id: "bulk-3", journey: "mission-bulk", title: "全選並確認",
        sub: [
          {
            action: "按「全選」，勾選這一類的全部警示",
            tip: "已經確認過的不會再勾",
            target: '[data-guide="issues-all"]', pointer: "全選",
            done: (ctx) => ctx.state.checked.size > 0,
          },
          {
            action: "按「確認無誤」，一次確認",
            tip: "確認後這一類就不會再列入需檢查",
            target: '[data-guide="issues-confirm"]', pointer: "確認無誤",
            done: () => false,
          },
        ],
        done: (ctx) => {
          const list = bulkIssues(ctx);
          return sticky(ctx, "b3", list.length >= 1 && list.every((i) => i.dismissed));
        },
      },
      {
        id: "bulk-4", journey: "mission-bulk", title: "看已處理的紀錄", noSkip: true,
        action: "切到「已處理」，看剛確認的紀錄",
        tip: "之後想反悔，在這裡也可以取消確認",
        target: () => chipByText("已處理"), pointer: "已處理",
        done: (ctx) => ctx.state.tab === "issues" && ctx.state.issueFilter === "dismissed"
          && bulkIssues(ctx).some((i) => i.dismissed),
      },
    ],
    // 切到「所有警示」之前不要預先篩好，讓使用者自己走一遍
  };

  const MISSION_RESET = {
    id: "mission-reset", title: "清掉重來，按錯可以復原", isMission: true, ephemeral: true,
    learned: "重新檢查會清掉人工決定，清完的提示裡有「復原」，按錯也找得回來",
    // 範例的暫存空間先替使用者做 2 個人工決定（和使用者自己點出來的一樣）
    async prepare(ctx, run) {
      const keys = (run.issues || []).filter((i) => i.code === "check0" && !i.dismissed).slice(0, 2).map((i) => i.key);
      if (!keys.length) return run;
      return ctx.bridge.post(`/api/runs/${encodeURIComponent(run.run_id)}/dismiss`, { keys, on: true });
    },
    steps: [
      {
        id: "reset-1", journey: "mission-reset", title: "看會清掉幾項",
        action: "按「重新檢查」，看它會清掉幾項",
        tip: (ctx) => `範例已經先做了 ${ctx.flags.resetStart ?? 2} 項人工決定，按鈕上會寫出數量`,
        target: "#resetButton", pointer: "重新檢查",
        done: (ctx) => sticky(ctx, "r1", Boolean(ctx.flags.resetArmed)),
      },
      {
        id: "reset-2", journey: "mission-reset", title: "確定清除",
        action: (ctx) => `再按一次，清掉這 ${ctx.flags.resetStart ?? 2} 項`,
        tip: "按鈕 4 秒內沒再按就會恢復，避免誤按",
        target: "#resetButton", pointer: "再按一次",
        done: (ctx) => sticky(ctx, "r2", Boolean(ctx.flags.resetArmed) && ctx.state.result?.decisions === 0 && Boolean(ctx.state.result?.can_restore)),
      },
      {
        id: "reset-3", journey: "mission-reset", title: "復原", noSkip: true,
        action: (ctx) => `按下方的「復原」，把 ${ctx.flags.resetStart ?? 2} 項找回來`,
        tip: "提示過一陣子會消失，來不及按可以再叫出來",
        target: '#toast:not([hidden]) [data-guide="toast-action"]', pointer: "復原",
        assist: (ctx) => (document.querySelector('#toast:not([hidden]) [data-guide="toast-action"]')
          ? null : { label: "再顯示復原", run: () => ctx.bridge.offerRestore("已清掉人工決定") }),
        done: (ctx) => sticky(ctx, "r3", Boolean(ctx.flags.r2) && (ctx.state.result?.decisions ?? 0) >= (ctx.flags.resetStart ?? 2)),
      },
    ],
  };

  const MISSION_POPOUT = {
    id: "mission-popout", title: "表格太寬，搬到另一個螢幕", isMission: true, ephemeral: true,
    learned: "Pop out 把表格搬到另一個螢幕，兩個視窗同步，Pop in 會帶著選到的列回來",
    steps: [
      {
        id: "pop-1", journey: "mission-popout", title: "Pop out",
        setup: (ctx) => { if (ctx.state.tab !== "rows" && !ctx.bridge.popped.size) ctx.bridge.goTo({ tab: "rows" }); },
        action: "按右上的「Pop out」，把結果搬到另一個視窗",
        tip: "可以把新視窗拖到另一個螢幕",
        wrong: (ctx) => (ctx.flags.popBlocked ? "瀏覽器擋下了新視窗，請允許這個網站開啟彈出式視窗後再按一次，或先跳過這條練習" : null),
        assist: (ctx) => (ctx.flags.popBlocked ? { label: "跳過這條練習", run: () => engine.leaveDemo({ dismiss: false }) } : null),
        target: '[data-guide="popout-btn"]', pointer: "Pop out",
        done: (ctx) => sticky(ctx, "p1", ctx.bridge.popped.size > 0),
      },
      {
        id: "pop-2", journey: "mission-popout", title: "在新視窗選一列",
        action: "到新視窗點任一列，這裡會跟著選到同一列",
        tip: "「結果」分頁標了 ↗，表示它現在在另一個視窗",
        target: '.tab[data-tab="rows"]', frame: true,
        done: (ctx) => sticky(ctx, "p2", Boolean(ctx.flags.popRid)),
      },
      {
        id: "pop-3", journey: "mission-popout", title: "Pop in 回來", noSkip: true,
        action: "在新視窗按「Pop in」，或在這裡按「全部 Pop in」",
        tip: "選到的那一列會一起帶回來",
        target: '[data-guide="popin-all"]', pointer: "全部 Pop in",
        done: (ctx) => Boolean(ctx.flags.p1) && ctx.bridge.popped.size === 0 && ctx.state.tab === "rows"
          && Boolean(ctx.flags.popRid) && ctx.state.selected === ctx.flags.popRid,
      },
    ],
  };

  const MISSION_TRANSFORM = {
    id: "mission-transform", title: "用公式算出新欄位", isMission: true, ephemeral: true,
    learned: "公式算出的欄位，在「怎麼來的」和 recipe 說明的 SQL 原文都看得到計算過程",
    steps: [
      {
        id: "tf-1", journey: "mission-transform", title: "打開一列",
        setup: goRowsAll,
        action: "點結果表裡的任何一列",
        tip: "細節會在右邊打開",
        target: (ctx) => rowSelector(traceRow(ctx.state.result)), frame: true,
        done: (ctx) => sticky(ctx, "f1", Boolean(selectedRow(ctx))),
      },
      {
        id: "tf-2", journey: "mission-transform", title: "看計算步驟",
        action: "在「台幣金額」按「怎麼來的」",
        tip: "會看到計算步驟「換算台幣」",
        wrong: (ctx) => {
          const row = selectedRow(ctx);
          const data = row && ctx.state.traces[row.rid];
          if (!row || !data || !ctx.state.openTrace.has(`${row.rid}${NUL}台幣金額`)) return null;
          return (data.columns?.["台幣金額"] || []).some((l) => l.includes("換算台幣")) ? null : "這一列沒有算出台幣金額，換一列看看";
        },
        target: '#drawer [data-guide="why-台幣金額"]', pointer: "怎麼來的", reveal: true,
        done: (ctx) => {
          const row = selectedRow(ctx);
          const data = row && ctx.state.traces[row.rid];
          return sticky(ctx, "f2", Boolean(row && data && ctx.state.openTrace.has(`${row.rid}${NUL}台幣金額`)
            && (data.columns?.["台幣金額"] || []).some((l) => l.includes("換算台幣"))));
        },
      },
      {
        id: "tf-3", journey: "mission-transform", title: "看 SQL 原文", noSkip: true,
        sub: [
          {
            action: "按 recipe 的「查看」",
            tip: "說明會把每個步驟翻成白話",
            target: '#recipeList [data-guide="recipe-view"]', pointer: "查看",
            done: () => Boolean(document.querySelector("#dialog[open] .explain")),
          },
          {
            action: "找到「計算：換算台幣」，展開「SQL 原文」",
            tip: "公式實際執行的 SQL 就在這裡",
            target: () => explainCodeSummary(), pointer: "SQL 原文",
            done: () => Boolean(explainCodeSummary()?.parentElement?.open),
          },
        ],
        done: (ctx) => sticky(ctx, "f3", Boolean(document.querySelector("#dialog[open] .explain")) && Boolean(explainCodeSummary()?.parentElement?.open)),
      },
    ],
  };

  const MISSIONS = {
    "mission-trace": MISSION_TRACE,
    "mission-source": MISSION_SOURCE,
    "mission-bulk": MISSION_BULK,
    "mission-reset": MISSION_RESET,
    "mission-popout": MISSION_POPOUT,
    "mission-transform": MISSION_TRANSFORM,
  };

  /* 練習清單（4.2 的推薦順序）：mission 與 lab 共用，進度記在 prefs.practiceDone */
  const PRACTICE = [
    { id: "mission-trace", card: "card-trace", group: "檢查與修正", minutes: 2 },
    { id: "mission-source", card: "card-source", group: "檢查與修正", minutes: 3 },
    { id: "mission-bulk", card: "card-bulk", group: "檢查與修正", minutes: 2 },
    { id: "mission-reset", card: "card-reset", group: "檢查與修正", minutes: 2 },
    { id: "mission-popout", card: "card-popout", group: "檢查與修正", minutes: 2 },
    { id: "lab-gate", card: "lab-gate", group: "寫 recipe", minutes: 3, lab: true },
    { id: "lab-mapping", card: "lab-mapping", group: "寫 recipe", minutes: 3, lab: true },
    { id: "lab-match", card: "lab-match", group: "寫 recipe", minutes: 4, lab: true },
    { id: "lab-extract", card: "lab-extract", group: "寫 recipe", minutes: 3, lab: true },
    { id: "lab-validate", card: "lab-validate", group: "寫 recipe", minutes: 3, lab: true },
    { id: "mission-transform", card: "card-transform", group: "寫 recipe", minutes: 3 },
  ];


  /* 產生實地練習（Lab）的 4 個步驟（沿用同一個 Spotlight 引擎） */
  function buildLabJourney(card, labState) {
    return {
      id: card.id,
      title: card.title,
      isLab: true,
      ephemeral: true,
      steps: [
        {
          id: `${card.id}-1`,
          journey: card.id,
          title: "看問題",
          action: card.step1Action,
          tip: card.step1Tip,
          setup: (ctx) => {
            if (card.step1Tab && ctx.state.tab !== card.step1Tab) {
              ctx.bridge.goTo({ tab: card.step1Tab });
            }
            if (card.step1Row) {
              const row = findRowByTitle(ctx.state.result, card.step1Row);
              if (row && ctx.state.selected !== row.rid) {
                ctx.state.selected = row.rid;
                ctx.bridge.renderTabs();
              }
            }
          },
          target: (ctx) => {
            if (card.step1Target) return card.step1Target;
            if (card.step1Row) {
              const row = findRowByTitle(ctx.state.result, card.step1Row);
              if (row) return `table.grid tbody tr[data-rid="${CSS.escape(row.rid)}"]`;
            }
            return null;
          },
          frame: true,
          done: () => Boolean(labState.sawProblem),
        },
        {
          id: `${card.id}-2`,
          journey: card.id,
          title: "找到要寫的位置",
          action: "練習面板裡是 recipe，看虛線那段",
          tip: "點一下片段編輯框開始寫",
          target: '[data-guide="lab-editor"]',
          frame: true,
          done: () => Boolean(labState.focusedEditor),
        },
        {
          id: `${card.id}-3`,
          journey: card.id,
          title: "寫規則",
          action: "照目標寫，或複製提問給 AI",
          tip: "寫完按 Ctrl+Enter 或點一下外面",
          target: '[data-guide="lab-copy-ai"]',
          pointer: "複製提問",
          done: () => Boolean(labState.snippetCommitted && labState.snippet.trim().length > 0),
        },
        {
          id: `${card.id}-4`,
          journey: card.id,
          title: "試算驗證",
          action: "按「試算」，全部打勾才算完成",
          tip: "不對會列出哪一列、抓到什麼、應該是什麼",
          target: '[data-guide="lab-try"]',
          pointer: "試算",
          noSkip: true,
          done: () => Boolean(labState.passed),
        },
      ],
    };
  }

  /* ---------- 引擎實例 ---------- */
  const engine = {
    bridge: null,
    prefs: defaultPrefs(),
    activeJourney: null,      // "review" | "recipe" | lab id | null
    labJourney: null,         // 動態產生的 lab journey 定義
    labState: null,           // 進行中的練習狀態
    missionState: null,       // 進行中的進階功能小關卡（{ done }）
    tip: null,                // 指令條位置的一次性提示（目前只有「練習進階功能」）
    savedWork: null,          // 進出範例／練習前保存的使用者工作狀態
    spotlight: null,          // 單一 spotlight 指示（非關卡，例如「用自己的資料開始」或新功能逐項）
    whatsnewData: null,
    whatsnewPending: [],      // 未讀的新功能條目
    whatsnewIdx: -1,
    activeFloat: null,        // { id, node, opener }
    flags: {},
    stepId: null,
    subId: null,
    lastStepId: null,
    lastStepDone: false,
    lastTargetEl: null,
    rafId: null,
    scrollRaf: null,
    pointerEl: null,
    outlineEl: null,
    resizeObs: null,
    statusInfo: null,

    init(bridge) {
      this.bridge = bridge;
      this.loadPrefs();
      this.loadSavedWork();
      if (bridge.isPopout) return;
      this.bindGlobal();
      this.renderWelcome();
    },

    loadPrefs() {
      const saved = this.bridge.prefs.get(PREF_KEY, null);
      const base = defaultPrefs();
      if (saved && typeof saved === "object") {
        this.prefs = {
          ...base,
          ...saved,
          journeys: {
            review: { ...base.journeys.review, ...(saved.journeys?.review || {}), flags: { ...(saved.journeys?.review?.flags || {}) } },
            recipe: { ...base.journeys.recipe, ...(saved.journeys?.recipe || {}), flags: { ...(saved.journeys?.recipe?.flags || {}) } },
          },
          tipsSeen: { ...base.tipsSeen, ...(saved.tipsSeen || {}) },
          cardsSeen: Array.isArray(saved.cardsSeen) ? saved.cardsSeen : [],
          practiceDone: Array.isArray(saved.practiceDone) ? saved.practiceDone
            : Array.isArray(saved.labsDone) ? saved.labsDone.filter((id) => typeof id === "string") : [],
        };
        delete this.prefs.labsDone;   // 舊版的 labsDone 改名 practiceDone，讀到舊鍵時遷移
        if (!Array.isArray(saved.practiceDone) && Array.isArray(saved.labsDone)) this.savePrefs();
      } else {
        this.prefs = base;
      }
    },

    savePrefs() {
      this.bridge.prefs.set(PREF_KEY, this.prefs);
    },

    loadSavedWork() {
      try {
        const raw = window.sessionStorage.getItem(SAVED_WORK_KEY);
        this.savedWork = raw ? JSON.parse(raw) : null;
      } catch (_e) {
        this.savedWork = null;
      }
    },

    persistSavedWork() {
      try {
        if (this.savedWork) window.sessionStorage.setItem(SAVED_WORK_KEY, JSON.stringify(this.savedWork));
        else window.sessionStorage.removeItem(SAVED_WORK_KEY);
      } catch (_e) { /* 略過 */ }
    },

    clearSavedWork() {
      this.savedWork = null;
      this.persistSavedWork();
    },

    isActive() {
      return Boolean(this.activeJourney);
    },

    /* 關卡 A、B 的完成記在 prefs，練習（lab、mission）的完成只存在這一次練習裡，完成後記進 practiceDone */
    defDone(def) {
      if (def.isLab) return Boolean(this.labState?.passed);
      if (def.isMission) return Boolean(this.missionState?.done);
      return Boolean(this.prefs.journeys[def.id]?.done);
    },

    markPractice(id) {
      if (!this.prefs.practiceDone.includes(id)) {
        this.prefs.practiceDone.push(id);
        this.savePrefs();
      }
      this.setActiveGuide(null);
    },

    /* 記著「正在做哪一關」，重新整理後才知道要不要續玩；做完或離開就清掉 */
    setActiveGuide(id) {
      if ((this.prefs.activeGuide || null) === id) return;
      this.prefs.activeGuide = id;
      this.savePrefs();
    },

    /* 頁面載入時：有進行中的關卡就自動準備範例資料並顯示導覽列；
       沒有導覽、畫面也不是範例，但 sessionStorage 還留著使用者的工作，就直接還原 */
    async resumeOnLoad() {
      if (this.bridge?.isPopout) return;
      const id = this.prefs.activeGuide;
      if (id === "review" && !this.prefs.journeys.review?.done) {
        await this.startJourney("review");
        return;
      }
      if (id && id !== "review" && PRACTICE.some((p) => p.id === id)) {
        await this.startPractice(id);
        return;
      }
      if (id) this.setActiveGuide(null);
      if (this.savedWork && !this.isShowingDemo()) await this.restoreWork();
    },

    practiceCount() {
      return PRACTICE.filter((p) => this.prefs.practiceDone.includes(p.id)).length;
    },

    /* 清單順序裡第一個沒練過的 */
    nextPractice() {
      return PRACTICE.find((p) => !this.prefs.practiceDone.includes(p.id)) || null;
    },

    practiceTitle(id) {
      const item = PRACTICE.find((p) => p.id === id);
      return CARDS.find((c) => c.id === item?.card)?.title || id;
    },

    isJourneyBActive() {
      return this.activeJourney === "recipe" && !this.prefs.journeys.recipe?.done;
    },

    isLabActive() {
      return Boolean(this.labState);
    },

    isShowingDemo() {
      const s = this.bridge?.state;
      if (!s) return false;
      return Boolean(
        this.activeJourney === "review" || s.result?.demo || this.labState || s.workbook?.demo
        || (s.recipeId && (s.recipeId.startsWith("demo:") || s.recipeId.startsWith("practice:")))
      );
    },

    shouldShowJkTip() {
      if (this.bridge?.isPopout) return false;
      if (this.activeJourney) return false;
      return (this.prefs.tipsSeen?.jk || 0) < 3;
    },

    bindGlobal() {
      const helpBtn = document.getElementById("helpBtn");
      if (helpBtn) {
        helpBtn.addEventListener("click", () => {
          if (this.activeFloat?.id === "helpPopover") this.closeFloat();
          else this.openHelpMenu(helpBtn);
        });
      }

      document.addEventListener("mousedown", (e) => {
        if (!this.activeFloat) return;
        if (this.activeFloat.node.contains(e.target)) return;
        if (this.activeFloat.opener && this.activeFloat.opener.contains(e.target)) return;
        this.closeFloat();
      });

      const onScroll = () => {
        if (this.scrollRaf) return;
        this.scrollRaf = requestAnimationFrame(() => {
          this.scrollRaf = null;
          if (this.activeFloat) this.placeFloat(this.activeFloat.node, this.activeFloat.opener);
          this.syncEmphasis();
        });
      };
      window.addEventListener("scroll", onScroll, { passive: true, capture: true });
      window.addEventListener("resize", onScroll, { passive: true });

      // 指令條的高度寫進 --guide-dock-h，.work 的 scroll-padding-top 才不會讓捲到的目標被它蓋住
      const dockEl = document.querySelector(".guide-dock");
      const workEl = document.querySelector(".work");
      const syncDockHeight = () => {
        if (dockEl && workEl) workEl.style.setProperty("--guide-dock-h", `${Math.round(dockEl.getBoundingClientRect().height)}px`);
      };
      syncDockHeight();
      if (window.ResizeObserver && dockEl) new ResizeObserver(() => { syncDockHeight(); onScroll(); }).observe(dockEl);

      if (window.ResizeObserver) {
        this.resizeObs = new ResizeObserver(onScroll);
        const work = document.querySelector(".work");
        const drawer = document.getElementById("drawer");
        if (work) this.resizeObs.observe(work);
        if (drawer) this.resizeObs.observe(drawer);
      }

      const dialog = document.getElementById("dialog");
      if (dialog) {
        dialog.addEventListener("close", () => {
          this.flags.recipeDialogOpen = false;
          this.restorePointerParent();
          this.schedule();
        });
      }
      const hub = document.getElementById("practiceHub");
      if (hub) {
        hub.addEventListener("click", (e) => { if (e.target === hub) hub.close(); });
        hub.addEventListener("close", () => {
          if (this.spotlight?.id === "hub-next") this.closeSpotlight();
          this.restorePointerParent();
          this.renderWelcome();
          this.schedule();
        });
      }
    },

    /* Esc 依序關閉：說明選單 → 說明卡 → 新功能小卡 → 單一 spotlight 外框 */
    handleEscape(e) {
      if (this.bridge?.isPopout) return false;
      const active = document.activeElement;
      if (active && active.matches?.("input, textarea, select")) return false;
      if (document.getElementById("practiceHub")?.open) return false;   // 練習中心是對話框，Esc 直接關掉它
      if (this.activeFloat) {
        this.closeFloat(true);
        e.preventDefault();
        return true;
      }
      if (this.spotlight) {
        this.closeSpotlight();
        e.preventDefault();
        return true;
      }
      return false;
    },

    /* ---------- 歡迎畫面（4.1） ---------- */
    renderWelcome() {
      if (this.bridge?.isPopout) return;
      const empty = document.getElementById("empty");
      if (!empty) return;
      const dismissed = Boolean(this.prefs.dismissed);
      const reviewDone = Boolean(this.prefs.journeys.review?.done);
      const ownData = node("button", {
        type: "button", class: "ghost small", dataset: { guide: "welcome-own" },
        text: "用自己的資料開始",
        onclick: () => this.openSpotlight("own-data", {
          target: "#dropZone",
          pointer: "放進 Excel 檔",
          action: "把你的 Excel 拖到左邊，選好 recipe 再按「執行」",
        }),
      });
      const recipeBtn = node("button", {
        type: "button", class: "ghost small", dataset: { guide: "welcome-recipe" },
        text: "練習放入 recipe",
        onclick: () => this.startJourney("recipe"),
      });
      // 新手導覽走完之後，主要入口換成練習進階功能，導覽改成次要的「重看」
      const primary = reviewDone
        ? node("button", {
          type: "button", class: "welcome-primary", dataset: { guide: "welcome-practice" },
          onclick: () => this.openPracticeHub(),
        },
        node("div", { class: "welcome-primary-head" },
          node("strong", { text: "練習進階功能" }),
          node("span", { text: `已練 ${this.practiceCount()} / ${PRACTICE.length}` })),
        node("p", { text: "怎麼來的、並排原始表、批次確認、Pop out 與寫 recipe" }))
        : node("button", {
          type: "button",
          class: `welcome-primary${dismissed ? " ghost-style" : ""}`,
          dataset: { guide: "welcome-review" },
          onclick: () => this.requestStartJourney("review"),
        },
        node("div", { class: "welcome-primary-head" },
          node("strong", { text: "用範例資料邊做邊學" }),
          node("span", { text: "約 5 分鐘" })),
        node("p", { text: "發票對報關單，練習檢查、修正與下載" }));
      put(empty,
        node("div", { class: "welcome" },
          node("h2", { class: "welcome-title", text: "選一個方式開始" }),
          primary,
          node("div", { class: "welcome-secondary" },
            reviewDone ? node("button", {
              type: "button", class: "ghost small", dataset: { guide: "welcome-review" },
              text: "重看新手導覽",
              onclick: () => this.requestStartJourney("review", { restart: true }),
            }) : null,
            recipeBtn,
            ownData),
          node("p", { class: "welcome-note", text: "左邊選好 recipe、放入 Excel，按「執行」。" })));
    },

    /* 保存／還原使用者的正式工作狀態（已有 savedWork 時不覆蓋） */
    captureWork() {
      if (this.savedWork) return;
      const s = this.bridge.state;
      if (this.isShowingDemo()) return;
      if (!s.result && !s.workbook) return;
      const layout = document.querySelector(".layout");
      const drawerW = layout ? parseInt(getComputedStyle(layout).getPropertyValue("--drawer-w"), 10) : null;
      this.savedWork = {
        recipeId: s.recipeId,
        workbook: s.workbook,
        runId: s.result?.run_id || null,
        tab: s.tab,
        filter: s.filter,
        search: s.search,
        selected: s.selected,
        matchName: s.matchName,
        matchFilter: s.matchFilter,
        matchSearch: s.matchSearch,
        drawerW,
      };
      this.persistSavedWork();
    },

    /* 離開範例或練習的統一出口 */
    async leaveDemo({ dismiss = false } = {}) {
      const wasDemo = this.isShowingDemo();
      this.stopJourney(dismiss);
      if (!wasDemo) return;
      if (this.savedWork) {
        await this.restoreWork();
      } else {
        this.clearDemoView();
      }
    },

    async restoreWork() {
      const saved = this.savedWork;
      this.clearSavedWork();
      this.stopJourney(false);
      this.labState = null;
      this.labJourney = null;
      if (!saved) {
        this.clearDemoView();
        return;
      }
      const s = this.bridge.state;
      s.recipeId = saved.recipeId;
      if (saved.drawerW) document.querySelector(".layout")?.style.setProperty("--drawer-w", `${saved.drawerW}px`);
      await this.bridge.loadRecipes(saved.recipeId);
      if (saved.runId) {
        try {
          const result = await this.bridge.api(`/api/runs/${encodeURIComponent(saved.runId)}`);
          if (saved.workbook) this.bridge.setWorkbook(saved.workbook);
          this.bridge.setResult(result, false, true);
          Object.assign(s, {
            tab: saved.tab, filter: saved.filter, search: saved.search,
            selected: saved.selected, matchName: saved.matchName,
            matchFilter: saved.matchFilter || "todo", matchSearch: saved.matchSearch || "",
          });
          this.bridge.renderTabs();
          return;
        } catch (_err) {
          this.clearDemoView();
          this.bridge.toast("原本的檔案已關閉，請重新放入");
          return;
        }
      }
      if (saved.workbook) {
        this.bridge.setWorkbook(saved.workbook);
      }
      this.clearDemoView();
    },

    clearDemoView() {
      const s = this.bridge.state;
      s.result = null;
      s.selected = null;
      if (s.workbook?.demo) {
        s.workbook = null;
        const label = document.getElementById("workbookLabel");
        const info = document.getElementById("workbookInfo");
        if (label) label.textContent = "選擇或拖曳 Excel 檔（.xlsx）";
        if (info) info.replaceChildren();
      }
      if (s.recipeId && (s.recipeId.startsWith("demo:") || s.recipeId.startsWith("practice:"))) {
        s.recipeId = (s.recipes.find((r) => !r.problems.length && !r.practice) || {}).id || null;
      }
      const resultEl = document.getElementById("result");
      const emptyEl = document.getElementById("empty");
      const statusEl = document.getElementById("runStatus");
      if (resultEl) resultEl.hidden = true;
      if (emptyEl) emptyEl.hidden = false;
      if (statusEl) statusEl.hidden = true;
      this.bridge.renderRecipes();
      this.bridge.renderDrawer();
      this.renderWelcome();
    },

    /* 已有工作時先詢問是否切換範例（4.1） */
    requestStartJourney(id, opts = {}) {
      if (id === "review" && !opts.force && !this.isShowingDemo() && (this.bridge.state.result || this.bridge.state.workbook)) {
        this.openConfirmDemoCard(() => this.startJourney(id, { ...opts, force: true }));
        return;
      }
      this.startJourney(id, opts);
    },

    openConfirmDemoCard(onConfirm) {
      const card = node("div", { id: "confirmDemoCard", class: "float-card", role: "dialog", "aria-label": "要用範例資料開始嗎" },
        node("div", { class: "float-card-head" },
          node("h3", { text: "要用範例資料開始嗎？" }),
          node("button", { type: "button", class: "ghost icon-btn", "aria-label": "關閉", onclick: () => this.closeFloat(true) }, "✕")),
        node("p", { class: "float-card-body", text: "目前的結果會先收起來，你做的修改都已自動保存，走完導覽按「回到我的工作」會原樣接回。" }),
        node("div", { class: "float-card-actions" },
          node("button", {
            type: "button", class: "primary small", text: "用範例資料開始",
            onclick: () => { this.closeFloat(); onConfirm(); },
          }),
          node("button", { type: "button", class: "ghost small", text: "取消", onclick: () => this.closeFloat(true) })));
      this.showFloat("confirmDemoCard", card, document.getElementById("helpBtn"));
    },

    needsSatisfied(step) {
      if (!step?.needs) return true;
      if (step.needs === "demoResult") return this.bridge.state.result?.demo === true;
      if (step.needs === "recipeDialog") return Boolean(document.getElementById("dialog")?.open);
      return true;
    },

    async startJourney(id, opts = {}) {
      if (this.bridge?.isPopout) return;
      const gen = (this.journeyGen = (this.journeyGen || 0) + 1);
      this.closeFloat();
      this.closeSpotlight();
      this.closePracticeHub();
      if (MISSIONS[this.activeJourney]) this.releasePopouts();
      this.tip = null;
      this.missionState = null;
      this.labState = null;
      this.labJourney = null;

      const jp = this.prefs.journeys[id] || { step: null, done: false, skipped: [], flags: {} };
      const isReset = Boolean(opts.restart || jp.done);
      if (isReset) {
        jp.step = null;
        jp.done = false;
        jp.skipped = [];
        jp.flags = {};
      }
      this.prefs.journeys[id] = jp;
      this.prefs.dismissed = false;
      this.savePrefs();

      const def = JOURNEYS[id];
      const resuming = !isReset && Boolean(jp.step && jp.step !== def.steps[0].id && def.steps.some((s) => s.id === jp.step));
      this.flags = resuming ? { ...(jp.flags || {}) } : {};

      if (id === "review") {
        this.captureWork();
        this.activeJourney = id;
        this.setActiveGuide("review");
        const targetStepId = resuming ? jp.step : def.steps[0].id;
        const targetStep = def.steps.find((s) => s.id === targetStepId) || def.steps[0];

        if (resuming && targetStep.needs === "demoResult" && !this.bridge.state.result?.demo) {
          // 續玩第 2 步以後且畫面沒有範例結果：自動準備並執行範例資料
          const strip = document.getElementById("missionStrip");
          const bar = document.getElementById("guideBar");
          if (bar) bar.hidden = false;
          if (strip) {
            strip.hidden = false;
            put(strip, node("span", { class: "mission-badge", text: "…" }),
              node("div", { class: "mission-main" }, node("div", { class: "mission-action", text: "正在準備範例資料…" })));
          }
          try {
            const body = opts.recipe ? { journey: "review", recipe: opts.recipe } : { journey: "review" };
            const data = await this.bridge.post("/api/demo/start", body);
            if (this.journeyGen !== gen) return;
            this.bridge.state.recipeId = data.recipe.id;
            this.bridge.state.demoRecipe = data.recipe;
            this.bridge.setWorkbook(data.workbook);
            const run = await this.bridge.post("/api/runs", { recipe: data.recipe.id, workbook: data.workbook.id });
            if (this.journeyGen !== gen) return;
            this.bridge.setResult(run, true);
            this.bridge.renderRecipes();
            // 推到第一個未完成的步驟（不超過存的步驟）
            const savedIdx = def.steps.findIndex((s) => s.id === jp.step);
            const ctx = this.ctx();
            let pick = def.steps[savedIdx];
            for (let i = 0; i <= savedIdx; i++) {
              if (!def.steps[i].done(ctx)) { pick = def.steps[i]; break; }
            }
            this.stepId = pick.id;
            jp.step = pick.id;
            this.savePrefs();
          } catch (_err) {
            if (this.journeyGen !== gen) return;
            // 準備失敗：回到第 1 步並更新 prefs
            this.stepId = def.steps[0].id;
            jp.step = def.steps[0].id;
            this.savePrefs();
            this.bridge.toast("無法自動準備範例資料，請從第 1 步開始");
          }
        } else {
          const runBtn = document.getElementById("runButton");
          if (runBtn) runBtn.disabled = true;
          try {
            const body = opts.recipe ? { journey: "review", recipe: opts.recipe } : { journey: "review" };
            const data = await this.bridge.post("/api/demo/start", body);
            if (this.journeyGen !== gen) return;
            this.bridge.state.recipeId = data.recipe.id;
            this.bridge.state.demoRecipe = data.recipe;
            this.bridge.setWorkbook(data.workbook);
            if (!opts.keepResult && !resuming) {
              this.bridge.state.result = null;
              this.bridge.state.selected = null;
              document.getElementById("result").hidden = true;
              document.getElementById("empty").hidden = false;
              this.bridge.renderDrawer();
            }
            this.bridge.renderRecipes();
          } catch (err) {
            if (this.journeyGen !== gen) return;
            this.stepId = def.steps[0].id;
            jp.step = def.steps[0].id;
            this.savePrefs();
            this.bridge.toast(err.message || "無法載入範例資料", true);
          }
          this.stepId = resuming && this.needsSatisfied(targetStep) ? targetStep.id : def.steps[0].id;
          jp.step = this.stepId;
          this.savePrefs();
        }
      } else if (id === "recipe") {
        // 每次開始關卡 B 只刪暫存空間裡的 practice:invoice，絕不碰 workspace/recipes
        if (!resuming) {
          await this.bridge.api("/api/recipes/practice%3Ainvoice", { method: "DELETE" }).catch(() => {});
          if (this.journeyGen !== gen) return;
          await this.bridge.loadRecipes();
          if (this.journeyGen !== gen) return;
        }
        this.activeJourney = id;
        const targetStep = resuming ? (def.steps.find((s) => s.id === jp.step) || def.steps[0]) : def.steps[0];
        if (targetStep.needs === "recipeDialog" && !document.getElementById("dialog")?.open) {
          this.stepId = def.steps[0].id;
          this.flags.openedRecipeDialog = false;
          jp.step = def.steps[0].id;
          this.savePrefs();
        } else {
          this.stepId = targetStep.id;
        }
      }

      if (this.journeyGen !== gen) return;
      this.subId = null;
      this.lastStepId = null;
      this.lastStepDone = false;
      this.setupTriedStep = null;
      this.renderGuide();
      this.runStepSetup(this.currentStep());
      this.schedule();
    },

    /* 搬出去的視窗收回來：離開練習時不留下孤兒視窗 */
    releasePopouts() {
      if (this.bridge?.popped?.size) this.bridge.popInAll();
    },

    stopJourney(markDismissed = true) {
      this.journeyGen = (this.journeyGen || 0) + 1;
      if (MISSIONS[this.activeJourney]) this.releasePopouts();
      this.missionState = null;
      this.activeJourney = null;
      this.setActiveGuide(null);
      this.stepId = null;
      this.subId = null;
      this.lastStepId = null;
      this.lastStepDone = false;
      this.labJourney = null;
      if (this.labState) {
        this.labState = null;
        this.bridge.renderDrawer();
      }
      if (markDismissed) {
        this.prefs.dismissed = true;
        this.savePrefs();
      }
      this.clearEmphasis();
      this.restorePointerParent();
      const bar = document.getElementById("guideBar");
      const strip = document.getElementById("missionStrip");
      if (bar) bar.hidden = true;
      if (strip) strip.hidden = true;
      const dg = document.querySelector(".dialog-guide");
      if (dg) dg.remove();
      this.renderWelcome();
      if (this.bridge.state.result && this.bridge.state.tab === "rows") this.bridge.renderRows();
    },

    currentJourneyDef() {
      if (this.labJourney && this.activeJourney === this.labJourney.id) return this.labJourney;
      if (this.activeJourney && MISSIONS[this.activeJourney]) return MISSIONS[this.activeJourney];
      return this.activeJourney ? JOURNEYS[this.activeJourney] || null : null;
    },

    currentStep() {
      const def = this.currentJourneyDef();
      if (!def) return null;
      return def.steps.find((s) => s.id === this.stepId) || def.steps[0];
    },

    ctx() {
      return {
        state: this.bridge.state,
        flags: this.flags,
        bridge: this.bridge,
        schedule: () => this.schedule(),
      };
    },

    currentSub(step) {
      if (!step?.sub?.length) return null;
      const ctx = this.ctx();
      const firstUndone = step.sub.find((s) => !s.done(ctx));
      return firstUndone || step.sub[step.sub.length - 1];
    },

    runStepSetup(step) {
      if (!step?.setup) return;
      try { step.setup(this.ctx()); } catch (_e) { /* 略過 */ }
    },

    schedule() {
      if (this.bridge?.isPopout) return;
      if (this.rafId) return;
      this.rafId = requestAnimationFrame(() => {
        this.rafId = null;
        this.evaluateAndRender();
      });
    },

    /* 立刻重畫（不等下一個影格）：原始資料小卡這類「關掉後目標才露出來」的情況，強調要同時出現 */
    flush() {
      if (this.rafId) { cancelAnimationFrame(this.rafId); this.rafId = null; }
      this.evaluateAndRender();
    },

    evaluateAndRender() {
      const def = this.currentJourneyDef();
      if (!def) {
        this.syncEmphasis();
        return;
      }
      const ctx = this.ctx();
      const jp = def.ephemeral ? null : this.prefs.journeys[def.id];
      const alreadyDone = this.defDone(def);

      if (!alreadyDone) {
        const cur = this.currentStep();
        if (cur?.keepVisible) { try { cur.keepVisible(ctx); } catch (_e) { /* 略過 */ } }
        const curDone = cur ? Boolean(cur.done(ctx)) : false;
        const sameStep = this.lastStepId === cur?.id;
        // 只有「停在未完成的步驟，且它剛轉為完成」時自動推進到第一個未完成的步驟
        if (curDone && (!sameStep ? !this.flags.manualJump : !this.lastStepDone)) {
          const next = def.steps.find((s) => !s.done(ctx));
          if (next) {
            this.stepId = next.id;
            this.lastStepId = next.id;
            this.lastStepDone = false;
            this.flags.manualJump = false;
            if (jp) { jp.step = next.id; this.savePrefs(); }
            this.runStepSetup(next);
            this.pulseStrip();
          } else {
            // 關卡全部完成
            this.lastStepId = cur?.id || null;
            this.lastStepDone = true;
            if (def.ephemeral) {
              if (def.isMission && this.missionState) this.missionState.done = true;
              this.markPractice(def.id);
            } else if (jp) {
              jp.done = true;
              jp.step = null;
              this.savePrefs();
              this.setActiveGuide(null);
            }
          }
        } else {
          this.lastStepId = cur?.id || null;
          this.lastStepDone = curDone;
        }
      }
      this.renderGuide();
      this.syncEmphasis();
    },

    pulseStrip() {
      const strip = document.getElementById("missionStrip");
      if (!strip) return;
      strip.classList.remove("pulse");
      void strip.offsetWidth;
      strip.classList.add("pulse");
    },

    goStep(stepId, skippedFromId = null) {
      const def = this.currentJourneyDef();
      if (!def) return;
      const target = def.steps.find((s) => s.id === stepId);
      if (!target) return;
      const jp = def.ephemeral ? null : this.prefs.journeys[def.id];
      if (skippedFromId && jp && !jp.skipped.includes(skippedFromId)) {
        jp.skipped.push(skippedFromId);
      }
      this.stepId = target.id;
      this.flags.manualJump = true;
      this.lastStepId = target.id;
      this.lastStepDone = Boolean(target.done(this.ctx()));
      if (jp) { jp.step = target.id; this.savePrefs(); }
      this.runStepSetup(target);
      this.renderGuide();
      this.syncEmphasis();
    },

    renderGuide() {
      const bar = document.getElementById("guideBar");
      const strip = document.getElementById("missionStrip");
      const def = this.currentJourneyDef();
      if (!bar || !strip || !def) {
        if (bar) bar.hidden = true;
        if (strip) {
          strip.hidden = true;
          if (this.tip && !def) this.renderTip(strip);
        }
        return;
      }

      const ctx = this.ctx();
      const jp = def.ephemeral ? null : this.prefs.journeys[def.id];
      const allDone = this.defDone(def);
      const step = this.currentStep();
      const idx = def.steps.indexOf(step);
      const skipped = new Set(jp?.skipped || []);

      bar.hidden = false;
      const dots = [];
      def.steps.forEach((s, i) => {
        if (i > 0) dots.push(node("span", { class: "guide-conn", "aria-hidden": "true" }));
        const done = Boolean(s.done(ctx));
        const current = !allDone && s.id === step.id;
        const isSkip = !done && skipped.has(s.id);
        const stateLabel = done ? "已完成" : current ? "進行中" : isSkip ? "已跳過" : "未開始";
        dots.push(node("button", {
          type: "button", class: "guide-dot-btn",
          "aria-label": `第 ${i + 1} 步：${s.title}，${stateLabel}`,
          title: `第 ${i + 1} 步：${s.title}`,
          onclick: () => this.goStep(s.id),
        }, node("span", { class: `guide-dot${current ? " current" : done ? " done" : isSkip ? " skipped" : ""}` })));
      });

      const stepLabel = allDone
        ? `${def.title}・已完成`
        : `${idx + 1}/${def.steps.length} ${step.title}`;

      put(bar,
        def.isMission ? node("span", { class: "guide-journey", text: `進階：${def.title}` }) : null,
        node("div", { class: "guide-dots" }, dots),
        node("span", { class: "guide-step-name", text: stepLabel }),
        node("div", { class: "guide-bar-actions" },
          def.ephemeral ? node("button", {
            type: "button", class: "ghost small", text: "結束練習",
            onclick: () => this.leaveDemo({ dismiss: false }),
          }) : null,
          node("button", {
            type: "button", class: "ghost small", text: "關閉導覽",
            onclick: () => this.leaveDemo({ dismiss: true }),
          })));

      strip.hidden = false;
      if (allDone) {
        this.renderCompleteStrip(strip, def);
        const dg = document.querySelector(".dialog-guide");
        if (dg) dg.remove();
        return;
      }

      const activeSub = this.currentSub(step);
      const subIdx = activeSub ? step.sub.indexOf(activeSub) : -1;
      const badgeText = activeSub ? `${idx + 1}　${subIdx + 1}/${step.sub.length}` : String(idx + 1);

      // 步驟目標所在分頁被 pop out 時
      const poppedAway = step.tabNeeded && this.bridge.popped.has(step.tabNeeded);
      const resolveText = (v) => (typeof v === "function" ? v(ctx) : v);
      const actionText = resolveText(activeSub ? activeSub.action : step.action);
      const wrongMsg = step.wrong ? step.wrong(ctx) : null;
      const assistRaw = (activeSub && activeSub.assist) || step.assist || null;
      const assist = typeof assistRaw === "function" ? assistRaw(ctx) : assistRaw;

      let tipNode;
      if (poppedAway) {
        tipNode = node("div", { class: "mission-tip warn", text: "這一步在另一個視窗，按「全部 Pop in」回來" });
      } else if (wrongMsg) {
        tipNode = node("div", { class: "mission-tip warn", text: `⚠ ${wrongMsg}` });
      } else if (step.tipLegend) {
        tipNode = node("div", { class: "mission-tip" }, statusLegendRow());
      } else {
        const tipText = resolveText(activeSub ? activeSub.tip : step.tip);
        tipNode = tipText ? node("div", { class: "mission-tip", text: tipText }) : null;
      }

      const prevStep = idx > 0 ? def.steps[idx - 1] : null;
      const nextStep = idx < def.steps.length - 1 ? def.steps[idx + 1] : null;
      const canSkipNext = Boolean(nextStep) && !step.noSkip;

      const assistBtn = assist ? node("button", {
        type: "button", class: "ghost small mission-assist",
        dataset: { guide: "mission-assist" },
        text: assist.label,
        onclick: () => assist.run(ctx),
      }) : null;

      put(strip,
        node("span", { class: "mission-badge", text: badgeText }),
        node("div", { class: "mission-main" },
          node("div", { class: "mission-action-row" },
            node("span", { class: "mission-action", text: actionText }),
            assistBtn),
          tipNode),
        node("div", { class: "mission-actions" },
          prevStep ? node("button", {
            type: "button", class: "ghost small", text: "上一步",
            onclick: () => this.goStep(prevStep.id),
          }) : null,
          canSkipNext ? node("button", {
            type: "button", class: "ghost small", text: "下一步",
            onclick: () => this.goStep(nextStep.id, step.done(ctx) ? null : step.id),
          }) : null));

      this.syncDialogGuide(def, badgeText, actionText, tipNode, assist);
    },

    renderCompleteStrip(strip, def) {
      if (def.id === "review") {
        const backBtn = this.savedWork
          ? node("button", { type: "button", class: "ghost small", text: "回到我的工作", onclick: () => this.leaveDemo({ dismiss: false }) })
          : node("button", {
            type: "button", class: "ghost small", text: "用自己的資料開始",
            onclick: async () => {
              await this.leaveDemo({ dismiss: false });
              this.openSpotlight("own-data", { target: "#dropZone", pointer: "放進 Excel 檔", action: "把你的 Excel 拖到左邊，選好 recipe 再按「執行」" });
            },
          });
        put(strip,
          node("span", { class: "mission-badge done", text: "✓" }),
          node("div", { class: "mission-main" },
            node("div", { class: "mission-action", text: "核對流程走完了" }),
            node("div", { class: "mission-tip", text: "每一列都處理過才下載，正式資料也一樣" })),
          node("div", { class: "mission-actions" },
            node("button", {
              type: "button", class: "primary small", text: "練習進階功能", dataset: { guide: "complete-practice" },
              onclick: () => this.openPracticeHub(),
            }),
            backBtn,
            node("button", { type: "button", class: "ghost small", text: "練習放入 recipe", onclick: () => this.startJourney("recipe") }),
            node("button", {
              type: "button", class: "link", text: "清掉範例資料",
              onclick: async () => {
                await this.bridge.post("/api/demo/clear", {});
                await this.leaveDemo({ dismiss: false });
                await this.bridge.loadRecipes();
                this.bridge.toast("已清掉範例資料");
              },
            })));
      } else if (def.id === "recipe") {
        put(strip,
          node("span", { class: "mission-badge done", text: "✓" }),
          node("div", { class: "mission-main" },
            node("div", { class: "mission-action", text: "recipe 放好了" }),
            node("div", { class: "mission-tip", text: "現在可以用它處理範例資料，或刪掉練習 recipe" })),
          node("div", { class: "mission-actions" },
            node("button", {
              type: "button", class: "primary small", text: "用它處理範例資料",
              onclick: () => this.startJourney("review", { recipe: "practice:invoice", restart: true }),
            }),
            node("button", {
              type: "button", class: "link", text: "刪除練習 recipe",
              onclick: async () => {
                await this.bridge.api("/api/recipes/practice%3Ainvoice", { method: "DELETE" }).catch(() => {});
                await this.bridge.loadRecipes();
                await this.leaveDemo({ dismiss: false });
                this.bridge.toast("已刪除練習 recipe");
              },
            })));
      } else if (def.ephemeral) {
        this.renderPracticeComplete(strip, def);
      }
    },

    /* 練習（mission 與 lab）共用的完成畫面：學到什麼、下一個、回練習清單、回到我的工作 */
    renderPracticeComplete(strip, def) {
      const learned = def.isLab ? CARDS.find((c) => c.id === def.id)?.learned : def.learned;
      const next = this.nextPractice();
      const aiCard = def.id === "mission-transform" ? CARDS.find((c) => c.id === "card-transform") : null;
      put(strip,
        node("span", { class: "mission-badge done", text: "✓" }),
        node("div", { class: "mission-main" },
          node("div", { class: "mission-action", text: "練習完成" }),
          node("div", { class: "mission-tip", text: next ? (learned || "") : `${learned || ""}　${PRACTICE.length} 項都練過了`.trim() })),
        node("div", { class: "mission-actions" },
          next ? node("button", {
            type: "button", class: "primary small", dataset: { guide: "practice-next" },
            text: `下一個：${this.practiceTitle(next.id)}`,
            onclick: () => this.startPractice(next.id),
          }) : null,
          node("button", { type: "button", class: "ghost small", dataset: { guide: "practice-list" }, text: "回練習清單", onclick: () => this.openPracticeHub() }),
          aiCard ? node("button", { type: "button", class: "ghost small", text: "複製給 AI 的提問", onclick: () => this.copyAiPrompt(aiCard) }) : null,
          this.savedWork ? node("button", { type: "button", class: "ghost small", text: "回到我的工作", onclick: () => this.leaveDemo({ dismiss: false }) }) : null));
    },

    /* 關卡 B：對話框開啟（top layer）時，在對話框內頂端畫出精簡指令條 */
    syncDialogGuide(def, badgeText, actionText, tipNode, assist) {
      const dialog = document.getElementById("dialog");
      const inner = dialog?.querySelector(".dialog-inner");
      const existing = inner?.querySelector(".dialog-guide");
      if (!dialog?.open || !inner || (def.id !== "recipe" && !def.isMission)) {
        if (existing) existing.remove();
        return;
      }
      const dg = existing || node("div", { class: "dialog-guide" });
      const ctx = this.ctx();
      const assistBtn = assist ? node("button", {
        type: "button", class: "ghost small mission-assist",
        dataset: { guide: "dialog-assist" },
        text: assist.label,
        onclick: () => assist.run(ctx),
      }) : null;
      put(dg,
        node("span", { class: "mission-badge", text: badgeText }),
        node("div", { class: "mission-main" },
          node("div", { class: "mission-action-row" },
            node("span", { class: "mission-action", text: actionText }),
            assistBtn),
          tipNode ? tipNode.cloneNode(true) : null));
      if (!existing) {
        const body = document.getElementById("dialogBody");
        inner.insertBefore(dg, body);
      }
    },

    /* ---------- 強調引擎：浮標、外框、虛線框三者擇一 ---------- */
    clearEmphasis() {
      document.querySelectorAll(".guide-target").forEach((el) => el.classList.remove("guide-target"));
      document.querySelectorAll(".guide-reveal").forEach((el) => el.classList.remove("guide-reveal"));
      if (this.pointerEl) this.pointerEl.hidden = true;
      if (this.outlineEl) this.outlineEl.hidden = true;
    },

    restorePointerParent() {
      if (this.pointerEl && this.pointerEl.parentElement !== document.body) {
        document.body.append(this.pointerEl);
      }
    },

    /* host：目標所在的對話框（top layer），沒有就放在 body；對話框開著時浮標一定要畫進對話框裡（5.6） */
    ensurePointer(hostEl) {
      if (!this.pointerEl) {
        this.pointerEl = node("div", { id: "guidePointer", class: "guide-pointer", "aria-hidden": "true", hidden: true });
      }
      const host = hostEl || document.body;
      if (this.pointerEl.parentElement !== host) host.append(this.pointerEl);
      return this.pointerEl;
    },

    ensureOutline() {
      if (!this.outlineEl) {
        this.outlineEl = node("div", { class: "guide-outline", "aria-hidden": "true", hidden: true });
        document.body.append(this.outlineEl);
      }
      return this.outlineEl;
    },

    resolveEl(spec) {
      if (!spec) return null;
      const val = typeof spec === "function" ? spec(this.ctx()) : spec;
      if (!val) return null;
      if (val instanceof Element) return val.isConnected ? val : null;
      return document.querySelector(val);
    },

    syncEmphasis() {
      if (this.bridge?.isPopout) return;
      this.clearEmphasis();

      // 浮動卡開啟時，浮標與外框退讓；原始資料小卡開啟時，只有目標在小卡裡的步驟才畫
      if (this.activeFloat) return;
      const peekEl = document.getElementById("peek");

      let spec = null;
      const def = this.currentJourneyDef();
      const hubOpen = Boolean(document.getElementById("practiceHub")?.open);
      if (hubOpen) {
        spec = this.spotlight && this.spotlight.id === "hub-next" ? this.spotlight : null;
      } else if (def) {
        const allDone = this.defDone(def);
        if (!allDone) {
          const step = this.currentStep();
          if (step) {
            if (step.tabNeeded && this.bridge.popped.has(step.tabNeeded)) {
              spec = { target: '[data-guide="popin-all"]', pointer: "全部 Pop in" };
            } else {
              spec = this.currentSub(step) || step;
            }
          }
        }
      } else if (this.spotlight) {
        spec = this.spotlight;
      }
      if (!spec) return;

      const ctx = this.ctx();
      const dialogOpen = Boolean(document.querySelector("dialog[open]"));

      // 1) 內容虛線框優先（只畫虛線，不畫浮標或外框）
      if (spec.outline && !peekEl) {
        const el = this.resolveEl(spec.outline);
        if (el) {
          this.maybeScroll(el);
          const rect = el.getBoundingClientRect();
          if (rect.width > 0 && rect.height > 0) {
            const box = this.ensureOutline();
            box.style.left = `${rect.left - 3}px`;
            box.style.top = `${rect.top - 3}px`;
            box.style.width = `${rect.width + 6}px`;
            box.style.height = `${rect.height + 6}px`;
            box.hidden = false;
            return;
          }
        }
      }

      const targetEl = this.resolveEl(spec.target);
      if (!targetEl) {
        // 目標元素不存在：先呼叫一次 setup()，仍不存在則退回上一個 needs 滿足的步驟
        if (def && !def.isLab) {
          const step = this.currentStep();
          if (step && this.setupTriedStep !== step.id) {
            this.setupTriedStep = step.id;
            this.runStepSetup(step);
            if (this.resolveEl(spec.target)) { this.syncEmphasis(); return; }
          }
          if (step && !this.needsSatisfied(step)) {
            const idx = def.steps.indexOf(step);
            const fallback = def.steps.slice(0, idx).reverse().find((s) => this.needsSatisfied(s)) || def.steps[0];
            if (fallback && fallback.id !== step.id) {
              this.stepId = fallback.id;
              const jp = this.prefs.journeys[def.id];
              if (jp) { jp.step = fallback.id; this.savePrefs(); }
              this.renderGuide();
              this.syncEmphasis();
            }
          }
        }
        return;
      }
      if (peekEl && !peekEl.contains(targetEl)) return;
      const inDialog = dialogOpen && Boolean(targetEl.closest("dialog[open]"));
      if (dialogOpen && !inDialog) return;

      this.maybeScroll(targetEl);
      if (spec.reveal) targetEl.classList.add("guide-reveal");

      // 2) 外框模式（只畫 .guide-target，不畫浮標）
      if (spec.frame) {
        targetEl.classList.add("guide-target");
        return;
      }

      // 3) 浮標模式（只畫 #guidePointer，不畫 .guide-target）
      const label = typeof spec.pointer === "function" ? spec.pointer(ctx) : (spec.pointer || "這裡");
      this.positionPointer(targetEl, label, inDialog);
    },

    maybeScroll(el) {
      if (this.lastTargetEl === el) return;
      this.lastTargetEl = el;
      const active = document.activeElement;
      if (active && active.matches?.("input, textarea, select")) return;
      try { el.scrollIntoView({ block: "nearest" }); } catch (_e) { /* 略過 */ }
    },

    /* 浮標只寫動作，不寫方向：方向由三角形（data-dir，一定指向目標）表示。
       目標在畫面外或被指令條（.guide-dock）蓋住時，浮標貼在捲動區的上緣或下緣，寫「往上捲」「往下捲」。 */
    positionPointer(el, label, inDialog = false) {
      const ptr = this.ensurePointer(inDialog ? (el.closest("dialog") || document.getElementById("dialog")) : null);
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) { ptr.hidden = true; return; }
      const text = String(label ?? "").replace(/^[\s←→↑↓]+|[\s←→↑↓]+$/g, "");

      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const dock = inDialog ? null : document.querySelector(".guide-dock");
      const dockRect = dock && dock.getClientRects().length ? dock.getBoundingClientRect() : null;
      const underDock = Boolean(dockRect) && rect.right > dockRect.left && rect.left < dockRect.right
        && rect.bottom <= dockRect.bottom + 4;
      const offTop = rect.bottom < 48 || underDock;
      const offBottom = rect.top > vh - 8;

      ptr.textContent = offTop ? "往上捲" : offBottom ? "往下捲" : text;
      ptr.hidden = false;
      const pw = ptr.offsetWidth || 80;
      const ph = ptr.offsetHeight || 26;
      ptr.style.removeProperty("--tip");

      if (offTop || offBottom) {
        const left = Math.max(12, Math.min(rect.left, vw - pw - 12));
        ptr.dataset.side = "offscreen";
        ptr.dataset.dir = offTop ? "up" : "down";
        ptr.style.left = `${left}px`;
        ptr.style.top = `${offTop ? Math.max(56, dockRect && underDock ? dockRect.bottom + 8 : 56) : vh - ph - 16}px`;
        ptr.style.setProperty("--tip", `${Math.max(10, Math.min(rect.left + rect.width / 2 - left, pw - 10))}px`);
        return;
      }

      // 目前這個浮標會擋住 elementFromPoint：量障礙物的時候先藏起來（visibility 不改版面）
      const prevVisibility = ptr.style.visibility;
      ptr.style.visibility = "hidden";
      const obstacles = inDialog ? [] : [
        document.querySelector("header.bar"),
        dock,
      ].filter((n) => n && n.getClientRects().length).map((n) => n.getBoundingClientRect());

      // 加入同操作列（或父容器）裡除了目標以外的可點元素作為障礙物
      const actionBar = el.closest(".lab-actions, .dialog-actions, .drawer-foot, .actions, .toolbar, .inline-fix, .mission-actions") || el.parentElement;
      if (actionBar) {
        for (const sib of actionBar.querySelectorAll("button, a, input, select, textarea")) {
          if (sib === el || sib.contains(el) || el.contains(sib) || sib.hidden) continue;
          const sr = sib.getBoundingClientRect();
          if (sr.width > 0 && sr.height > 0) obstacles.push(sr);
        }
      }
      // 目標附近、看得到的其他可點元素（例如細節裡「怎麼來的」下面的輸入框）也不能蓋住
      const root = inDialog ? (el.closest("dialog") || document) : document;
      for (const c of root.querySelectorAll("button, a[href], input, select, textarea, summary, [role=switch]")) {
        if (c === el || c.contains(el) || el.contains(c) || c.hidden || !c.getClientRects().length) continue;
        const sr = c.getBoundingClientRect();
        if (sr.width <= 0 || sr.height <= 0) continue;
        if (sr.right < rect.left - 260 || sr.left > rect.right + 260 || sr.bottom < rect.top - 90 || sr.top > rect.bottom + 90) continue;
        if (getComputedStyle(c).opacity === "0") continue;
        const at = document.elementFromPoint(sr.left + sr.width / 2, sr.top + sr.height / 2);
        if (at && (at === c || c.contains(at))) obstacles.push(sr);
      }

      // 目標周圍看得到的文字（同一行、同一卡片或同一列）也不能蓋住，例如「沒用到」旁儲存格的報單號碼
      {
        const scope = el.closest("tr, li, .practice-card, .help-row, .field, .card") || el.parentElement;
        const sr = scope ? scope.getBoundingClientRect() : null;
        const inScope = (r) => Boolean(sr) && r.top >= sr.top - 1 && r.bottom <= sr.bottom + 1 && r.left >= sr.left - 1 && r.right <= sr.right + 1;
        const nearBand = (r) => r.top < rect.bottom + 4 && r.bottom > rect.top - 4 && r.right > rect.left - 300 && r.left < rect.right + 300;
        const walker = document.createTreeWalker(root === document ? document.body : root, NodeFilter.SHOW_TEXT);
        const range = document.createRange();
        const dockNode = document.querySelector(".guide-dock");
        let visited = 0;
        for (let n = walker.nextNode(); n && visited < 4000; n = walker.nextNode()) {
          visited += 1;
          if (!n.nodeValue.trim()) continue;
          const parent = n.parentElement;
          if (!parent || el.contains(parent) || ptr.contains(parent) || (dockNode && dockNode.contains(parent))) continue;
          if (["SCRIPT", "STYLE", "OPTION", "TEXTAREA"].includes(parent.tagName) || parent.closest("[hidden]")) continue;
          range.selectNodeContents(n);
          for (const tr of range.getClientRects()) {
            if (tr.width < 2 || tr.height < 2) continue;
            if (!nearBand(tr) && !inScope(tr)) continue;
            if (tr.bottom < 0 || tr.top > vh) continue;
            const at = document.elementFromPoint(Math.min(Math.max(tr.left + tr.width / 2, 0), vw - 1), Math.min(Math.max(tr.top + tr.height / 2, 0), vh - 1));
            if (at && (at === parent || parent.contains(at) || at.contains(parent)) && !ptr.contains(at)) obstacles.push(tr);
          }
        }
      }

      ptr.style.visibility = prevVisibility;

      const gap = 10;
      const barRect = actionBar ? actionBar.getBoundingClientRect() : rect;
      const candidates = [
        { side: "right", left: rect.right + gap, top: rect.top + (rect.height - ph) / 2 },
        { side: "left", left: rect.left - pw - gap, top: rect.top + (rect.height - ph) / 2 },
        { side: "bottom", left: rect.left + (rect.width - pw) / 2, top: rect.bottom + gap },
        { side: "top", left: rect.left + (rect.width - pw) / 2, top: rect.top - ph - gap },
        { side: "bottom", left: rect.left + (rect.width - pw) / 2, top: barRect.bottom + gap },
        { side: "top", left: rect.left + (rect.width - pw) / 2, top: barRect.top - ph - gap },
        { side: "left", left: barRect.left - pw - gap, top: rect.top + (rect.height - ph) / 2 },
        { side: "right", left: rect.right + gap, top: rect.bottom + gap },
        { side: "left", left: rect.left - pw - gap, top: rect.bottom + gap },
        { side: "right", left: rect.right + gap, top: rect.top - ph - gap },
        { side: "left", left: rect.left - pw - gap, top: rect.top - ph - gap },
        { side: "right", left: barRect.right + gap, top: rect.top + (rect.height - ph) / 2 },
        // 目標在視窗邊緣、左右都擠滿時，改貼在目標上方或下方，靠左或靠右對齊
        { side: "top", left: rect.right - pw, top: rect.top - ph - gap },
        { side: "top", left: rect.left, top: rect.top - ph - gap },
        { side: "bottom", left: rect.right - pw, top: rect.bottom + gap },
        { side: "bottom", left: rect.left, top: rect.bottom + gap },
        { side: "top", left: rect.left + (rect.width - pw) / 2, top: rect.top - ph * 2 - gap * 2 },
      ];

      const clamp = (c) => ({
        side: c.side,
        left: Math.max(8, Math.min(c.left, vw - pw - 8)),
        top: Math.max(8, Math.min(c.top, vh - ph - 8)),
      });

      const overlapWith = (c, o) => {
        const ox = Math.max(0, Math.min(c.left + pw, o.right) - Math.max(c.left, o.left));
        const oy = Math.max(0, Math.min(c.top + ph, o.bottom) - Math.max(c.top, o.top));
        return ox * oy;
      };
      // 蓋到目標本身最糟（三角形就沒有指向目標了），權重放大
      const overlapArea = (c) => obstacles.reduce((sum, o) => sum + overlapWith(c, o), 0) + overlapWith(c, rect) * 50;

      const inBounds = (c) => c.left >= 6 && c.left + pw <= vw - 6 && c.top >= 6 && c.top + ph <= vh - 6;

      let chosen = candidates.find((c) => inBounds(c) && overlapArea(c) === 0);
      if (!chosen) {
        chosen = candidates.map(clamp).sort((a, b) => overlapArea(a) - overlapArea(b))[0];
      } else {
        chosen = clamp(chosen);
      }

      // 三角形指向目標：依浮標最後實際放的位置決定（擠進視窗邊緣被位移時也要對）
      const right = chosen.left + pw;
      const bottom = chosen.top + ph;
      let dir = { right: "left", left: "right", bottom: "up", top: "down" }[chosen.side];
      if (right <= rect.left + 1) dir = "right";
      else if (chosen.left >= rect.right - 1) dir = "left";
      else if (bottom <= rect.top + 1) dir = "down";
      else if (chosen.top >= rect.bottom - 1) dir = "up";
      const tip = dir === "left" || dir === "right"
        ? Math.max(8, Math.min(rect.top + rect.height / 2 - chosen.top, ph - 8))
        : Math.max(10, Math.min(rect.left + rect.width / 2 - chosen.left, pw - 10));

      ptr.dataset.side = chosen.side;
      ptr.dataset.dir = dir;
      ptr.style.setProperty("--tip", `${tip}px`);
      ptr.style.left = `${chosen.left}px`;
      ptr.style.top = `${chosen.top}px`;
    },

    openSpotlight(id, opts = {}) {
      if (this.bridge?.isPopout) return;
      this.spotlight = { id, ...opts };
      this.lastTargetEl = null;
      this.syncEmphasis();
    },

    closeSpotlight() {
      this.spotlight = null;
      this.clearEmphasis();
    },

    /* ---------- 浮動卡管理（說明選單、說明卡、新功能小卡） ---------- */
    showFloat(id, cardNode, opener = null) {
      this.closeFloat();
      document.body.append(cardNode);
      this.placeFloat(cardNode, opener);
      this.activeFloat = { id, node: cardNode, opener };
      if (opener && opener.id === "helpBtn") opener.setAttribute("aria-expanded", "true");
      this.clearEmphasis();
      const firstBtn = cardNode.querySelector("button, a[href]");
      if (firstBtn) firstBtn.focus();
    },

    placeFloat(card, opener) {
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      card.style.maxHeight = "calc(100vh - 66px)";
      const w = card.offsetWidth || 320;
      const h = card.offsetHeight || 200;
      let rawLeft = vw - w - 16;
      let rawTop = 56;
      if (opener && opener.isConnected) {
        const r = opener.getBoundingClientRect();
        rawLeft = r.right - w;
        rawTop = r.bottom + 8;
      }
      const left = Math.max(12, Math.min(rawLeft, Math.max(12, vw - w - 12)));
      const top = Math.max(54, Math.min(rawTop, Math.max(54, vh - h - 12)));
      card.style.left = `${left}px`;
      card.style.top = `${top}px`;
    },

    closeFloat(restoreFocus = false) {
      if (!this.activeFloat) return;
      const { node: card, opener } = this.activeFloat;
      card.remove();
      this.activeFloat = null;
      if (opener && opener.id === "helpBtn") opener.setAttribute("aria-expanded", "false");
      if (restoreFocus && opener && opener.isConnected) opener.focus();
      this.schedule();
    },

    /* ---------- 常駐「說明 ▾」選單（6.1） ---------- */
    openHelpMenu(opener) {
      const reviewPref = this.prefs.journeys.review;
      const recipePref = this.prefs.journeys.recipe;
      const progressText = (pref, total) => {
        if (pref.done) return "已完成 ✓";
        if (pref.step) {
          const steps = JOURNEYS[pref === reviewPref ? "review" : "recipe"].steps;
          const idx = steps.findIndex((s) => s.id === pref.step);
          if (idx >= 0) return `進行到 ${idx + 1}/${total}`;
        }
        return "";
      };

      const reviewCards = CARDS.filter((c) => c.group === "review");
      const recipeCards = CARDS.filter((c) => c.group === "recipe");
      const latestVer = this.whatsnewData?.versions?.[0];
      const hasUnread = this.whatsnewPending.length > 0;

      const card = node("div", { id: "helpPopover", class: "float-card", role: "dialog", "aria-label": "說明選單" },
        node("div", { class: "help-group-title", text: "新手導覽" }),
        node("button", {
          type: "button", class: "help-row",
          onclick: () => this.requestStartJourney("review", { restart: reviewPref.done }),
        }, node("span", { text: "核對一份資料 10 步" }),
        node("span", { class: "help-row-meta", text: progressText(reviewPref, 10) || (reviewPref.done ? "重看" : "") })),
        node("button", {
          type: "button", class: "help-row",
          onclick: () => this.startJourney("recipe", { restart: recipePref.done }),
        }, node("span", { text: "放入 recipe 5 步" }),
        node("span", { class: "help-row-meta", text: progressText(recipePref, 5) || (recipePref.done ? "重看" : "") })),
        node("div", { class: "help-sep" }),
        node("button", {
          type: "button", class: "help-row", dataset: { guide: "help-practice" },
          onclick: () => this.openPracticeHub(),
        }, node("span", { text: "練習中心" }),
        node("span", { class: "help-row-meta", text: `已練 ${this.practiceCount()} / ${PRACTICE.length}` })),
        node("div", { class: "help-group-title", text: "檢查與修正" }),
        reviewCards.map((c) => node("button", {
          type: "button", class: "help-row",
          onclick: () => this.openCard(c.id, opener),
        }, node("span", { text: c.title }),
        this.prefs.practiceDone.includes(c.mission) ? node("span", { class: "help-row-meta", text: "✓" }) : null)),
        node("div", { class: "help-group-title" }, "寫 recipe", node("span", { text: "實地練習" })),
        recipeCards.map((c) => node("button", {
          type: "button", class: "help-row",
          onclick: () => this.openCard(c.id, opener),
        }, node("span", { text: c.title }),
        this.prefs.practiceDone.includes(c.isLab ? c.id : c.mission) ? node("span", { class: "help-row-meta", text: "✓" }) : null)),
        node("div", { class: "help-sep" }),
        latestVer ? node("button", {
          type: "button", class: "help-row",
          onclick: () => this.openWhatsNewHistory(opener),
        }, node("span", { text: `新功能　${latestVer.version} 新增 ${latestVer.items.length} 項` }),
        hasUnread ? node("span", { class: "help-row-dot", "aria-label": "有新功能" }) : null) : null,
        node("a", {
          class: "help-row", href: "/manual", target: "_blank", rel: "noopener",
          style: "text-decoration:none",
          onclick: () => this.closeFloat(),
        }, node("span", { text: "使用手冊" }), node("span", { class: "help-row-meta", text: "↗" })));

      this.showFloat("helpPopover", card, opener);
    },

    /* ---------- 說明卡（6.3） ---------- */
    openCard(id, opener = null) {
      const c = CARDS.find((x) => x.id === id) || EXTRA_SPOTLIGHTS[id];
      if (!c) return;
      if (!this.prefs.cardsSeen.includes(id)) {
        this.prefs.cardsSeen.push(id);
        this.savePrefs();
      }

      const exampleEl = c.example ? node("div", { class: "float-card-example" },
        c.example.text ? c.example.text : [
          node("code", { text: c.example.before }),
          " → ",
          node("code", { text: c.example.after }),
        ]) : null;

      const actions = [];
      const practiceId = c.isLab ? c.id : c.mission;
      if (practiceId) {
        actions.push(node("button", {
          type: "button", class: "primary small", text: "開始練習", dataset: { guide: "card-practice" },
          onclick: () => { this.closeFloat(); this.startPractice(practiceId); },
        }));
      }
      if (c.group === "recipe") {
        actions.push(node("button", {
          type: "button", class: practiceId ? "ghost small" : "primary small",
          text: "複製給 AI 的提問",
          onclick: () => this.copyAiPrompt(c),
        }));
      }
      if (c.anchor) {
        actions.push(node("a", {
          class: "link", href: `/manual#${c.anchor}`, target: "_blank", rel: "noopener",
          text: "看手冊 ↗", onclick: () => this.closeFloat(),
        }));
      }

      const card = node("div", { id: "helpCard", class: "float-card", role: "dialog", "aria-label": c.title },
        node("div", { class: "float-card-head" },
          node("h3", { text: c.title }),
          node("button", { type: "button", class: "ghost icon-btn", "aria-label": "關閉", onclick: () => this.closeFloat(true) }, "✕")),
        node("div", { class: "float-card-body", text: c.when }),
        exampleEl,
        c.where ? node("div", { class: "float-card-where", text: c.where }) : null,
        node("div", { class: "float-card-actions" }, actions));

      this.showFloat("helpCard", card, opener || document.getElementById("helpBtn"));
    },

    async tryReviewCard(c) {
      if (!this.bridge.state.result) {
        try {
          const started = await this.bridge.post("/api/demo/start", { journey: "review" });
          const run = await this.bridge.post("/api/runs", { recipe: started.recipe.id, workbook: started.workbook.id });
          this.bridge.setWorkbook(started.workbook);
          this.bridge.setResult(run, true);
        } catch (err) {
          this.bridge.toast(err.message || "無法載入範例", true);
          return;
        }
      }
      this.goToCardSpot(c);
    },

    goToCardSpot(c) {
      if (c.tryTab && this.bridge.state.result) {
        this.bridge.goTo({ tab: c.tryTab });
      }
      if (c.tryTarget) {
        requestAnimationFrame(() => {
          this.openSpotlight(c.id, { target: c.tryTarget, pointer: `${c.title.slice(0, 10)}` });
        });
      }
    },

    /* 情境 ? 按鈕 */
    hintButton(cardId, label) {
      if (this.bridge?.isPopout) return null;
      return node("button", {
        type: "button", class: "help-hint",
        "aria-label": `說明：${label}`, title: `說明：${label}`,
        onclick: (e) => { e.stopPropagation(); this.openCard(cardId, e.currentTarget); },
      }, "?");
    },

    /* ---------- 複製給 AI 的提問（6.4） ---------- */
    async copyAiPrompt(card, lab = null) {
      try {
        const specData = await this.bridge.api("/api/spec");
        const fullSpec = specData.text || "";
        const section = this.extractSpecSection(fullSpec, card.specHeading);
        const rules = this.extractSpecSection(fullSpec, "給 AI");
        const parts = [
          `目標：${card.title}（${card.when}）`,
          "",
          "請依照以下 recipe 規格撰寫：",
          rules,
          section,
        ];
        if (lab) {
          parts.push(
            "",
            `要插入的位置：${lab.slot?.label || "# {{slot}}"}`,
            "目前練習 recipe 全文：",
            "```yaml",
            lab.recipe_text || "",
            "```",
          );
          if (lab.sample_preview) {
            parts.push("", "練習資料前 3 列：", lab.sample_preview);
          }
        } else {
          parts.push("", "把我的欄位名稱和規則補在下面：");
        }
        parts.push("", "只輸出要放進這個位置的 YAML，縮排從第 0 欄開始，不要加說明。");
        this.bridge.copyText(parts.filter((x) => x !== null && x !== undefined).join("\n"));
      } catch (err) {
        this.bridge.toast(err.message || "無法取得規格", true);
      }
    },

    extractSpecSection(text, keyword) {
      if (!keyword || !text) return "";
      const lines = text.split("\n");
      const start = lines.findIndex((l) => /^#{2,3}\s/.test(l) && l.toLowerCase().includes(keyword.toLowerCase()));
      if (start < 0) return "";
      let end = lines.length;
      const level = (lines[start].match(/^#+/) || ["##"])[0].length;
      for (let i = start + 1; i < lines.length; i++) {
        const m = lines[i].match(/^(#+)\s/);
        if (m && m[1].length <= level) { end = i; break; }
      }
      return lines.slice(start, end).join("\n");
    },

    /* ---------- 進階功能小關卡（mission）與練習中心（4.1、4.3） ---------- */
    /* 開始一項練習：已經在導覽或練習裡就先收掉它（不離開範例），再開 mission 或 lab。
       進來之前照 leaveDemo 的規則保存使用者的工作（captureWork），走完按「回到我的工作」接回。 */
    async startPractice(id) {
      if (this.bridge?.isPopout) return;
      const item = PRACTICE.find((p) => p.id === id);
      if (!item) return;
      this.closeFloat();
      this.closePracticeHub();
      if (this.activeJourney) this.stopJourney(false);
      if (item.lab) await this.startLab(id);
      else await this.startMission(id);
    },

    async startMission(id) {
      if (this.bridge?.isPopout) return;
      const def = MISSIONS[id];
      if (!def) return;
      const gen = (this.journeyGen = (this.journeyGen || 0) + 1);
      this.closeFloat();
      this.closeSpotlight();
      this.closePracticeHub();
      this.tip = null;
      this.releasePopouts();
      this.captureWork();
      this.labState = null;
      this.labJourney = null;
      this.missionState = null;
      this.activeJourney = null;
      this.stepId = null;

      const bar = document.getElementById("guideBar");
      const strip = document.getElementById("missionStrip");
      if (bar) bar.hidden = true;
      if (strip) {
        strip.hidden = false;
        put(strip, node("span", { class: "mission-badge", text: "…" }),
          node("div", { class: "mission-main" }, node("div", { class: "mission-action", text: "正在準備範例資料…" })));
      }

      const b = this.bridge;
      const s = b.state;
      try {
        const data = await b.post("/api/demo/start", { journey: "review" });
        if (this.journeyGen !== gen) return;
        s.recipeId = data.recipe.id;
        s.demoRecipe = data.recipe;
        b.setWorkbook(data.workbook);
        let run = await b.post("/api/runs", { recipe: data.recipe.id, workbook: data.workbook.id });
        // 範例的人工決定存在暫存空間，會留到下一次練習：每條都從乾淨的狀態開始
        if (run.decisions > 0) run = await b.post(`/api/runs/${encodeURIComponent(run.run_id)}/reset`, {});
        if (def.prepare) run = (await def.prepare(this.ctx(), run)) || run;
        if (this.journeyGen !== gen) return;
        s.openTrace.clear();
        s.checked.clear();
        s.matchOpen?.clear?.();
        s.pickerFor = null;
        s.issueFocus = null;
        b.setResult(run, true);
        s.selected = null;
        b.renderRecipes();
        b.renderTabs();
        this.flags = { resetStart: run.decisions };
      } catch (err) {
        if (this.journeyGen !== gen) return;
        b.toast(err.message || "無法載入範例資料", true);
        await this.leaveDemo({ dismiss: false });
        return;
      }

      this.missionState = { done: false };
      this.activeJourney = id;
      this.setActiveGuide(id);
      this.stepId = def.steps[0].id;
      this.subId = null;
      this.lastStepId = null;
      this.lastStepDone = false;
      this.setupTriedStep = null;
      this.renderGuide();
      this.runStepSetup(this.currentStep());
      this.schedule();
    },

    closePracticeHub() {
      const hub = document.getElementById("practiceHub");
      if (hub?.open) hub.close();
    },

    openPracticeHub() {
      if (this.bridge?.isPopout) return;
      const hub = document.getElementById("practiceHub");
      if (!hub) return;
      this.closeFloat();
      if (this.tip) this.dismissTip();
      if (!this.prefs.tipsSeen.hub) {
        this.prefs.tipsSeen.hub = 1;
        this.savePrefs();
      }
      this.renderPracticeHub();
      if (!hub.open) hub.showModal();
      // 一次都沒練過：浮標指向推薦的第一項（對話框內畫，照 5.6）
      if (!this.prefs.practiceDone.length) {
        this.openSpotlight("hub-next", { target: '#practiceHub [data-guide="practice-next"]', pointer: "從這裡開始" });
      }
    },

    renderPracticeHub() {
      const hub = document.getElementById("practiceHub");
      if (!hub) return;
      const next = this.nextPractice();
      const card = (p) => {
        const info = CARDS.find((c) => c.id === p.card);
        const done = this.prefs.practiceDone.includes(p.id);
        const isNext = next?.id === p.id;
        return node("article", { class: `practice-card${isNext ? " next" : ""}${done ? " done" : ""}`, dataset: { practice: p.id } },
          node("div", { class: "practice-card-head" },
            node("strong", { text: info?.title || p.id }),
            done ? node("span", { class: "practice-check", "aria-label": "練過了", text: "✓" }) : null),
          node("p", { class: "practice-when", text: info?.when || "" }),
          node("div", { class: "practice-card-foot" },
            node("span", { class: "practice-time", text: `約 ${p.minutes} 分鐘` }),
            node("button", {
              type: "button", class: isNext ? "primary small" : "ghost small",
              dataset: isNext ? { guide: "practice-next" } : undefined,
              "aria-label": `${done ? "再練一次" : "開始"}：${info?.title || p.id}`,
              text: done ? "再練一次" : "開始",
              onclick: () => this.startPractice(p.id),
            })));
      };
      const groups = ["檢查與修正", "寫 recipe"];
      put(hub, node("div", { class: "dialog-inner practice-hub-inner" },
        node("div", { class: "dialog-head" },
          node("div", { class: "practice-title" },
            node("h3", { text: "進階功能練習" }),
            node("span", { class: "practice-count", text: `已練 ${this.practiceCount()} / ${PRACTICE.length}` })),
          node("button", { type: "button", class: "ghost icon-btn dialog-close", "aria-label": "關閉", title: "關閉", onclick: () => this.closePracticeHub() }, "✕")),
        node("p", { class: "practice-sub", text: "每項 2～4 分鐘，用範例資料操作，做完會接回你的工作。" }),
        groups.map((g) => node("section", { class: "practice-group" },
          node("h4", { class: "practice-group-title", text: g }),
          node("div", { class: "practice-grid" }, PRACTICE.filter((p) => p.group === g).map(card))))));
    },

    /* 第一次用自己的資料執行完，且新手導覽走完、練習中心沒開過：指令條位置靜默提示一次 */
    afterRun(result) {
      if (this.bridge?.isPopout) return;
      if (this.tip) this.dismissTip();
      if (this.activeJourney || result?.demo) return;
      if (!this.prefs.journeys.review?.done) return;
      const seen = this.prefs.tipsSeen;
      if (seen.practice || seen.hub) return;
      seen.practice = 1;
      this.savePrefs();
      this.tip = "practice";
      this.renderGuide();
    },

    dismissTip() {
      this.tip = null;
      const strip = document.getElementById("missionStrip");
      if (strip && !this.currentJourneyDef()) strip.hidden = true;
      this.renderGuide();
    },

    renderTip(strip) {
      strip.hidden = false;
      put(strip,
        node("div", { class: "mission-main" },
          node("div", { class: "mission-action", text: "看完這份資料後，可以到說明 ▾ 練習進階功能" })),
        node("div", { class: "mission-actions" },
          node("button", { type: "button", class: "primary small", dataset: { guide: "tip-open-practice" }, text: "開練習中心", onclick: () => this.openPracticeHub() }),
          node("button", { type: "button", class: "ghost small", dataset: { guide: "tip-dismiss" }, text: "不用了", onclick: () => this.dismissTip() })));
    },

    /* ---------- 實地練習（Lab）引擎（7.4、7.5） ---------- */
    async startLab(labId) {
      if (this.bridge?.isPopout) return;
      const card = CARDS.find((c) => c.id === labId && c.isLab);
      if (!card) return;
      this.closeFloat();
      this.closeSpotlight();
      this.closePracticeHub();
      this.tip = null;
      this.missionState = null;
      this.captureWork();
      try {
        const data = await this.bridge.post(`/api/labs/${encodeURIComponent(labId)}/start`, {});
        this.labState = {
          id: labId,
          card,
          title: data.title || card.title,
          goal: data.goal || card.when,
          recipe_text: data.recipe_text || "",
          slot: data.slot || { marker: "# {{slot}}", label: "" },
          sample_preview: data.sample_preview || "",
          snippet: data.start || "",
          attempts: 0,
          problems: [],
          checks: [],
          passed: false,
          sawProblem: false,
          focusedEditor: false,
          snippetCommitted: false,
        };
        this.labJourney = buildLabJourney(card, this.labState);
        this.activeJourney = labId;
        this.setActiveGuide(labId);
        this.stepId = this.labJourney.steps[0].id;
        this.lastStepId = null;
        this.lastStepDone = false;
        this.flags = {};
        if (data.result) this.bridge.setResult(data.result, true, true);
        this.renderLabDrawer();
        this.renderGuide();
        this.runStepSetup(this.currentStep());
        this.schedule();
      } catch (err) {
        this.bridge.toast(err.message || "無法開始練習", true);
      }
    },

    renderLabDrawer() {
      const lab = this.labState;
      const drawer = document.getElementById("drawer");
      if (!lab || !drawer) return false;
      drawer.hidden = false;
      document.querySelector(".layout")?.classList.add("with-drawer");
      document.getElementById("drawerTitle").textContent = `練習：${lab.title}`;

      const body = document.getElementById("drawerBody");
      const foot = document.getElementById("drawerFoot");

      if (lab.passed) {
        put(body,
          node("div", { class: "lab-done-box" },
            node("p", { text: lab.card.learned }),
            node("div", { class: "lab-actions" },
              node("button", { type: "button", class: "primary small", text: "回到我的工作", onclick: () => this.leaveDemo({ dismiss: false }) }),
              node("button", { type: "button", class: "ghost small", text: "再練一次", onclick: () => this.startLab(lab.id) }),
              node("a", { class: "link", href: `/manual#${lab.card.anchor}`, target: "_blank", rel: "noopener", text: "看手冊 ↗" }))));
        put(foot);
        return true;
      }

      const yamlLines = lab.recipe_text.split("\n");
      const marker = lab.slot?.marker || "# {{slot}}";
      const yamlPre = node("pre", { class: "lab-yaml" }, yamlLines.map((line, i) => {
        if (line.includes(marker)) {
          return node("span", { class: "lab-slot-line", dataset: { guide: "lab-slot" }, text: `${line}  ← 在這裡寫` });
        }
        return document.createTextNode(line + (i < yamlLines.length - 1 ? "\n" : ""));
      }));

      const editor = node("textarea", {
        class: "lab-editor",
        dataset: { guide: "lab-editor" },
        placeholder: "在這裡輸入 YAML 片段（Ctrl+Enter 試算）",
      });
      editor.value = lab.snippet;
      const grow = () => { editor.style.height = "auto"; editor.style.height = `${Math.min(editor.scrollHeight, 220)}px`; };
      editor.addEventListener("focus", () => {
        lab.sawProblem = true;
        lab.focusedEditor = true;
        this.schedule();
      });
      editor.addEventListener("input", () => {
        lab.snippet = editor.value;
        grow();
      });
      editor.addEventListener("blur", () => {
        if (editor.value.trim()) {
          lab.snippetCommitted = true;
          this.schedule();
        }
      });
      editor.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
          e.preventDefault();
          lab.snippet = editor.value;
          lab.snippetCommitted = true;
          this.runLabTry();
        }
      });
      requestAnimationFrame(() => {
        grow();
        yamlPre.querySelector(".lab-slot-line")?.scrollIntoView({ block: "center" });
      });

      const problemsEl = lab.problems.length ? node("ul", { class: "problems" },
        lab.problems.map((p) => node("li", { text: p }))) : null;

      const checksEl = lab.checks.length ? node("ul", { class: "lab-checks" },
        lab.checks.map((ck) => node("li", {
          class: `lab-check ${ck.pass ? "pass" : "fail"}`,
          text: ck.pass ? `✓ ${ck.label}` : `⚠ ${ck.hint || ck.label}`,
        }))) : null;

      put(body,
        node("p", { class: "lab-goal", text: `目標：${lab.goal}` }),
        yamlPre,
        editor,
        node("div", { class: "lab-actions" },
          node("button", {
            type: "button", class: "primary small", dataset: { guide: "lab-try" }, text: "試算",
            onclick: () => this.runLabTry(),
          }),
          node("button", {
            type: "button", class: "ghost small", dataset: { guide: "lab-copy-ai" }, text: "複製給 AI 的提問",
            onclick: () => this.copyAiPrompt(lab.card, lab),
          }),
          lab.attempts >= 2 ? node("button", {
            type: "button", class: "link", dataset: { guide: "lab-fill-answer" }, text: "幫我帶入",
            onclick: () => this.fillLabAnswer(),
          }) : null),
        problemsEl,
        checksEl);
      put(foot);
      return true;
    },

    async runLabTry() {
      const lab = this.labState;
      if (!lab) return;
      try {
        const res = await this.bridge.post(`/api/labs/${encodeURIComponent(lab.id)}/try`, { snippet: lab.snippet });
        lab.problems = res.problems || [];
        lab.checks = res.checks || [];
        lab.sawProblem = true;
        lab.focusedEditor = true;
        lab.snippetCommitted = true;
        if (res.result) this.bridge.setResult(res.result, false, true);
        if (res.ok) {
          lab.passed = true;
        } else {
          lab.attempts += 1;
        }
        this.renderLabDrawer();
        this.schedule();
      } catch (err) {
        this.bridge.toast(err.message || "試算失敗", true);
      }
    },

    async fillLabAnswer() {
      const lab = this.labState;
      if (!lab) return;
      try {
        const res = await this.bridge.api(`/api/labs/${encodeURIComponent(lab.id)}/answer`);
        lab.snippet = res.answer || "";
        lab.snippetCommitted = true;
        this.renderLabDrawer();
        this.schedule();
      } catch (err) {
        this.bridge.toast(err.message || "無法帶入解答", true);
      }
    },

    /* ---------- 第 3 層：新功能（8.2、8.3） ---------- */
    async initWhatsNew(status) {
      if (this.bridge?.isPopout) return;
      this.statusInfo = status;
      try {
        this.whatsnewData = await this.bridge.api("/web/whatsnew.json");
      } catch (_e) {
        return;
      }
      const currentVer = status?.version || "0.0.0";
      const seen = this.prefs.whatsnewSeen;

      // 全新使用者：不顯示，直接記錄目前版本
      if (!seen && !status?.returning) {
        this.prefs.whatsnewSeen = currentVer;
        this.savePrefs();
        return;
      }

      const versions = this.whatsnewData?.versions || [];
      const unread = [];
      for (const v of versions) {
        if (seen && this.cmpVer(v.version, seen) <= 0) continue;
        for (const item of v.items || []) unread.push({ ...item, version: v.version });
      }
      this.whatsnewPending = unread;
      this.updateHelpDot();

      if (unread.length && !this.activeJourney) {
        setTimeout(() => {
          if (!this.activeJourney && this.whatsnewPending.length && !this.activeFloat) {
            this.showWhatsNewPopup();
          }
        }, 1200);
      }
    },

    cmpVer(a, b) {
      const pa = String(a).split(".").map((n) => parseInt(n, 10) || 0);
      const pb = String(b).split(".").map((n) => parseInt(n, 10) || 0);
      for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
        const diff = (pa[i] || 0) - (pb[i] || 0);
        if (diff !== 0) return diff;
      }
      return 0;
    },

    updateHelpDot() {
      const dot = document.querySelector("#helpBtn .help-dot");
      if (dot) dot.hidden = this.whatsnewPending.length === 0;
    },

    markWhatsNewSeen() {
      this.prefs.whatsnewSeen = this.statusInfo?.version || this.whatsnewData?.versions?.[0]?.version || "0.2.1";
      this.whatsnewPending = [];
      this.savePrefs();
      this.updateHelpDot();
    },

    showWhatsNewPopup() {
      const items = this.whatsnewPending.slice(0, 5);
      const preview = items.slice(0, 2);
      const ver = items[0]?.version || "";
      const card = node("div", { id: "whatsNewCard", class: "float-card", role: "dialog", "aria-label": "新功能" },
        node("div", { class: "float-card-head" },
          node("h3", { text: `${ver} 新增了 ${this.whatsnewPending.length} 項功能` }),
          node("button", { type: "button", class: "ghost icon-btn", "aria-label": "關閉", onclick: () => this.closeFloat() }, "✕")),
        node("ul", { class: "whatsnew-list" }, preview.map((it) => node("li", { text: `• ${it.title}` }))),
        node("div", { class: "float-card-actions" },
          node("button", {
            type: "button", class: "primary small", text: "看看",
            onclick: () => { this.closeFloat(); this.startWhatsNewTour(items); },
          }),
          node("button", { type: "button", class: "ghost small", text: "之後再說", onclick: () => this.closeFloat() })));
      this.showFloat("whatsNewCard", card, document.getElementById("helpBtn"));
    },

    startWhatsNewTour(items, index = 0) {
      const item = items[index];
      if (!item) {
        this.markWhatsNewSeen();
        this.closeSpotlight();
        return;
      }
      const isLast = index >= items.length - 1;
      const needsSample = Boolean(item.needsResult && !this.bridge.state.result);
      const actions = [];
      if (needsSample) {
        actions.push(node("button", {
          type: "button", class: "ghost small", text: "用範例資料看",
          onclick: async () => {
            this.closeFloat();
            const card = CARDS.find((c) => c.id === item.spotlight);
            if (card) await this.tryReviewCard(card);
            this.startWhatsNewTour(items, index);
          },
        }));
      }
      actions.push(node("button", {
        type: "button", class: "primary small", text: isLast ? "結束" : "下一項",
        onclick: () => {
          this.closeFloat();
          if (isLast) { this.markWhatsNewSeen(); this.closeSpotlight(); }
          else this.startWhatsNewTour(items, index + 1);
        },
      }));
      if (!isLast) {
        actions.push(node("button", {
          type: "button", class: "ghost small", text: "結束",
          onclick: () => { this.closeFloat(); this.markWhatsNewSeen(); this.closeSpotlight(); },
        }));
      }

      const card = node("div", { id: "whatsNewTourCard", class: "float-card", role: "dialog", "aria-label": item.title },
        node("div", { class: "float-card-head" },
          node("h3", { text: `${index + 1}/${items.length} ${item.title}` }),
          node("button", { type: "button", class: "ghost icon-btn", "aria-label": "結束", onclick: () => { this.closeFloat(); this.markWhatsNewSeen(); } }, "✕")),
        node("div", { class: "float-card-body", text: item.body }),
        node("div", { class: "float-card-actions" }, actions));

      const targetDef = CARDS.find((c) => c.id === item.spotlight) || EXTRA_SPOTLIGHTS[item.spotlight];
      const anchor = targetDef?.target ? document.querySelector(targetDef.target) : document.getElementById("helpBtn");
      this.showFloat("whatsNewTourCard", card, anchor || document.getElementById("helpBtn"));
    },

    openWhatsNewHistory(opener) {
      const versions = this.whatsnewData?.versions || [];
      const card = node("div", { id: "whatsNewHistory", class: "float-card", role: "dialog", "aria-label": "新功能一覽" },
        node("div", { class: "float-card-head" },
          node("h3", { text: "新功能" }),
          node("button", { type: "button", class: "ghost icon-btn", "aria-label": "關閉", onclick: () => this.closeFloat(true) }, "✕")),
        versions.map((v) => node("div", {},
          node("div", { class: "help-group-title" }, v.version, node("span", { text: v.date || "" })),
          (v.items || []).map((it) => node("button", {
            type: "button", class: "whatsnew-item-btn",
            onclick: () => { this.closeFloat(); this.startWhatsNewTour([it], 0); },
          }, node("strong", { text: it.title }), node("span", { text: it.body }))))));
      this.showFloat("whatsNewHistory", card, opener);
    },

    persistFlag(name, value = true) {
      this.flags[name] = value;
      const jp = this.activeJourney && this.prefs.journeys[this.activeJourney];
      if (jp) {
        jp.flags = jp.flags || {};
        jp.flags[name] = Boolean(value);
        this.savePrefs();
      }
    },

    /* ---------- 事件通知 ---------- */
    notify(event, payload = {}) {
      if (this.bridge?.isPopout) return;
      if (event === "stage-open") {
        if (payload.status === "review" || payload.id === "match") this.persistFlag("sawStage", true);
        if (this.labState && payload.id === "gate") this.labState.sawProblem = true;
      } else if (event === "trace-open") {
        const row = findRowByTitle(this.bridge.state.result, "INV-1003");
        if (row && payload.rid === row.rid) this.persistFlag("sawTrace", true);
      } else if (event === "source-open") {
        this.persistFlag("sawSource", true);
        if (payload.place?.cell) this.flags.sawCell = true;
      } else if (event === "reset-armed") {
        this.persistFlag("resetArmed", true);
      } else if (event === "popout-blocked") {
        this.persistFlag("popBlocked", true);
      } else if (event === "popout-select") {
        this.flags.popRid = payload.rid;
      } else if (event === "unused-click") {
        this.persistFlag("unusedClick", true);
      } else if (event === "demo-export") {
        // 還有列沒看就下載：不算完成，只提醒（步驟停在原地）
        const result = this.bridge.state.result;
        if (result?.demo) this.persistFlag(reviewRowsLeft(result) === 0 ? "demoExported" : "exportedEarly", true);
      } else if (event === "recipe-dialog") {
        this.flags.recipeDialogOpen = true;
        this.persistFlag("openedRecipeDialog", true);
      } else if (event === "spec-copied") {
        this.persistFlag("copiedSpec", true);
      } else if (event === "problems-shown") {
        this.persistFlag("sawProblems", true);
      } else if (event === "problems-copied") {
        this.persistFlag("copiedProblems", true);
      } else if (event === "explain-shown") {
        this.persistFlag("sawExplain", true);
      } else if (event === "practice-saved") {
        this.persistFlag("practiceSaved", true);
      } else if (event === "bad-edit") {
        this.flags.badEdit = payload;
      } else if (event === "good-edit") {
        this.flags.badEdit = null;
      } else if (event === "map-new-typing") {
        this.flags.mapNewCommitted = "";
      } else if (event === "map-new-commit") {
        this.flags.mapNewCommitted = payload.value || "";
      } else if (event === "remote-result") {
        this.flags.remoteUpdated = true;
      } else if (event === "jk-used") {
        this.prefs.tipsSeen.jk = (this.prefs.tipsSeen.jk || 0) + 1;
        this.savePrefs();
      } else if (event === "lab-problem-seen") {
        if (this.labState) this.labState.sawProblem = true;
      } else if (event === "tab-change") {
        if (this.labState && this.labState.card.step1Tab === payload.tab) {
          this.labState.sawProblem = true;
        }
      } else if (event === "row-select") {
        this.flags.badEdit = null;
        if (this.labState && this.labState.card.step1Row) {
          const row = findRowByTitle(this.bridge.state.result, this.labState.card.step1Row);
          if (row && payload.rid === row.rid) this.labState.sawProblem = true;
        }
      }
      this.schedule();
    },
  };

  window.Spotlights = {
    CARDS,
    EXTRA_SPOTLIGHTS,
    JOURNEYS,
    MISSIONS,
    PRACTICE,
    statusLegendRow,
    engine,
    startJourney: (id, opts) => engine.startJourney(id, opts),
    openSpotlight: (id, opts) => engine.openSpotlight(id, opts),
    closeSpotlight: () => engine.closeSpotlight(),
    scheduleGuide: () => engine.schedule(),
    renderGuide: () => engine.renderGuide(),
    syncEmphasis: () => engine.syncEmphasis(),
    positionPointer: (el, label, inDialog) => engine.positionPointer(el, label, inDialog),
  };
})();
