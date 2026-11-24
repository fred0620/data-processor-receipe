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
      labsDone: [],
      tipsSeen: { jk: 0 },
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
      title: "看這一格是怎麼來的",
      when: "不懂某個值為什麼是這樣",
      example: { before: "USD 3,450.00", after: "金額 3450，幣別另一欄" },
      tryTarget: '[data-guide="issue-trace"]',
      tryTab: "rows",
    },
    {
      id: "card-source", group: "review", anchor: "help-source",
      title: "兩張表並排，找配對的答案",
      when: "找不到配對，想自己翻原始表",
      example: { text: "左邊發票、右邊報關單，橘色「沒用到」就是候選" },
      tryTarget: '[data-guide="match-sheet"]',
      tryTab: "match",
    },
    {
      id: "card-bulk", group: "review", anchor: "help-bulk",
      title: "一次確認很多筆",
      when: "同一類要判斷的警示很多",
      example: { text: "所有警示勾選 → 確認無誤" },
      tryTarget: '.tab[data-tab="issues"]',
      tryTab: "issues",
    },
    {
      id: "card-reset", group: "review", anchor: "help-reset",
      title: "清掉重來，按錯可以復原",
      when: "想從頭檢查一次",
      example: { text: "重新檢查 → 清掉 n 項 → 復原" },
      tryTarget: "#resetButton",
      tryTab: "rows",
    },
    {
      id: "card-popout", group: "review", anchor: "help-popout",
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
        wrong: (ctx) => (ctx.flags.exportedEarly ? unfinishedRowsWarning(ctx) : null),
        done: (ctx) => Boolean(ctx.state.result?.demo) && pendingMatches(ctx.state.result).length === 0,
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
        wrong: (ctx) => (ctx.flags.exportedEarly ? unfinishedRowsWarning(ctx) : null),
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

  /* 產生實地練習（Lab）的 4 個步驟（沿用同一個 Spotlight 引擎） */
  function buildLabJourney(card, labState) {
    return {
      id: card.id,
      title: card.title,
      isLab: true,
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
          labsDone: Array.isArray(saved.labsDone) ? saved.labsDone : [],
        };
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
    },

    /* Esc 依序關閉：說明選單 → 說明卡 → 新功能小卡 → 單一 spotlight 外框 */
    handleEscape(e) {
      if (this.bridge?.isPopout) return false;
      const active = document.activeElement;
      if (active && active.matches?.("input, textarea, select")) return false;
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
      put(empty,
        node("div", { class: "welcome" },
          node("h2", { class: "welcome-title", text: "選一個方式開始" }),
          node("button", {
            type: "button",
            class: `welcome-primary${dismissed ? " ghost-style" : ""}`,
            dataset: { guide: "welcome-review" },
            onclick: () => this.requestStartJourney("review"),
          },
          node("div", { class: "welcome-primary-head" },
            node("strong", { text: "用範例資料邊做邊學" }),
            node("span", { text: "約 5 分鐘" })),
          node("p", { text: "發票對報關單，練習檢查、修正與下載" })),
          node("div", { class: "welcome-secondary" },
            node("button", {
              type: "button", class: "ghost small", dataset: { guide: "welcome-recipe" },
              text: "練習放入 recipe",
              onclick: () => this.startJourney("recipe"),
            }),
            node("button", {
              type: "button", class: "ghost small", dataset: { guide: "welcome-own" },
              text: "用自己的資料開始",
              onclick: () => this.openSpotlight("own-data", {
                target: "#dropZone",
                pointer: "放進 Excel 檔",
                action: "把你的 Excel 拖到左邊，選好 recipe 再按「執行」",
              }),
            })),
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

    stopJourney(markDismissed = true) {
      this.journeyGen = (this.journeyGen || 0) + 1;
      this.activeJourney = null;
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

    evaluateAndRender() {
      const def = this.currentJourneyDef();
      if (!def) {
        this.syncEmphasis();
        return;
      }
      const ctx = this.ctx();
      const jp = def.isLab ? null : this.prefs.journeys[def.id];
      const alreadyDone = def.isLab ? Boolean(this.labState?.passed) : Boolean(jp?.done);

      if (!alreadyDone) {
        const cur = this.currentStep();
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
            if (def.isLab) {
              if (!this.prefs.labsDone.includes(def.id)) {
                this.prefs.labsDone.push(def.id);
                this.savePrefs();
              }
            } else if (jp) {
              jp.done = true;
              jp.step = null;
              this.savePrefs();
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
      const jp = def.isLab ? null : this.prefs.journeys[def.id];
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
        if (strip) strip.hidden = true;
        return;
      }

      const ctx = this.ctx();
      const jp = def.isLab ? null : this.prefs.journeys[def.id];
      const allDone = def.isLab ? Boolean(this.labState?.passed) : Boolean(jp?.done);
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
        node("div", { class: "guide-dots" }, dots),
        node("span", { class: "guide-step-name", text: stepLabel }),
        node("div", { class: "guide-bar-actions" },
          def.isLab ? node("button", {
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
      const assist = (activeSub && activeSub.assist) || step.assist || null;

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
        const primaryBtn = this.savedWork
          ? node("button", { type: "button", class: "primary small", text: "回到我的工作", onclick: () => this.leaveDemo({ dismiss: false }) })
          : node("button", {
            type: "button", class: "primary small", text: "用自己的資料開始",
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
            primaryBtn,
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
      } else if (def.isLab) {
        const card = CARDS.find((c) => c.id === def.id);
        put(strip,
          node("span", { class: "mission-badge done", text: "✓" }),
          node("div", { class: "mission-main" },
            node("div", { class: "mission-action", text: "練習完成" }),
            node("div", { class: "mission-tip", text: card?.learned || "" })),
          node("div", { class: "mission-actions" },
            node("button", { type: "button", class: "primary small", text: "回到我的工作", onclick: () => this.leaveDemo({ dismiss: false }) })));
      }
    },

    /* 關卡 B：對話框開啟（top layer）時，在對話框內頂端畫出精簡指令條 */
    syncDialogGuide(def, badgeText, actionText, tipNode, assist) {
      const dialog = document.getElementById("dialog");
      const inner = dialog?.querySelector(".dialog-inner");
      const existing = inner?.querySelector(".dialog-guide");
      if (!dialog?.open || !inner || def.id !== "recipe") {
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
      if (this.pointerEl) this.pointerEl.hidden = true;
      if (this.outlineEl) this.outlineEl.hidden = true;
    },

    restorePointerParent() {
      if (this.pointerEl && this.pointerEl.parentElement !== document.body) {
        document.body.append(this.pointerEl);
      }
    },

    ensurePointer(inDialog) {
      if (!this.pointerEl) {
        this.pointerEl = node("div", { id: "guidePointer", class: "guide-pointer", "aria-hidden": "true", hidden: true });
      }
      const host = inDialog ? document.getElementById("dialog") : document.body;
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

      // 浮動卡或原始資料小卡開啟時，浮標與外框退讓
      if (this.activeFloat || document.getElementById("peek")) return;

      let spec = null;
      const def = this.currentJourneyDef();
      if (def) {
        const jp = def.isLab ? null : this.prefs.journeys[def.id];
        const allDone = def.isLab ? Boolean(this.labState?.passed) : Boolean(jp?.done);
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
      const dialogOpen = Boolean(document.getElementById("dialog")?.open);

      // 1) 內容虛線框優先（只畫虛線，不畫浮標或外框）
      if (spec.outline) {
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
      const inDialog = dialogOpen && Boolean(targetEl.closest("#dialog"));
      if (dialogOpen && !inDialog) return;

      this.maybeScroll(targetEl);

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
      const ptr = this.ensurePointer(inDialog);
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

      const gap = 10;
      const barRect = actionBar ? actionBar.getBoundingClientRect() : rect;
      const candidates = [
        { side: "right", left: rect.right + gap, top: rect.top + (rect.height - ph) / 2 },
        { side: "left", left: rect.left - pw - gap, top: rect.top + (rect.height - ph) / 2 },
        { side: "bottom", left: rect.left + (rect.width - pw) / 2, top: rect.bottom + gap },
        { side: "top", left: rect.left + (rect.width - pw) / 2, top: rect.top - ph - gap },
        { side: "bottom", left: rect.left + (rect.width - pw) / 2, top: barRect.bottom + gap },
        { side: "top", left: rect.left + (rect.width - pw) / 2, top: barRect.top - ph - gap },
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
        }, node("span", { text: "核對一份資料 8 步" }),
        node("span", { class: "help-row-meta", text: progressText(reviewPref, 8) || (reviewPref.done ? "重看" : "") })),
        node("button", {
          type: "button", class: "help-row",
          onclick: () => this.startJourney("recipe", { restart: recipePref.done }),
        }, node("span", { text: "放入 recipe 5 步" }),
        node("span", { class: "help-row-meta", text: progressText(recipePref, 5) || (recipePref.done ? "重看" : "") })),
        node("div", { class: "help-sep" }),
        node("div", { class: "help-group-title", text: "檢查與修正" }),
        reviewCards.map((c) => node("button", {
          type: "button", class: "help-row",
          onclick: () => this.openCard(c.id, opener),
        }, node("span", { text: c.title }))),
        node("div", { class: "help-group-title" }, "寫 recipe", node("span", { text: "實地練習" })),
        recipeCards.map((c) => node("button", {
          type: "button", class: "help-row",
          onclick: () => this.openCard(c.id, opener),
        }, node("span", { text: c.title }),
        c.isLab && this.prefs.labsDone.includes(c.id) ? node("span", { class: "help-row-meta", text: "✓" }) : null)),
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
      if (c.group === "recipe") {
        if (c.isLab) {
          actions.push(node("button", {
            type: "button", class: "primary small", text: "實地練習",
            onclick: () => { this.closeFloat(); this.startLab(c.id); },
          }));
        }
        actions.push(node("button", {
          type: "button", class: c.isLab ? "ghost small" : "primary small",
          text: "複製給 AI 的提問",
          onclick: () => this.copyAiPrompt(c),
        }));
      } else if (c.group === "review") {
        actions.push(node("button", {
          type: "button", class: "primary small", text: "試試看",
          onclick: () => { this.closeFloat(); this.tryReviewCard(c); },
        }));
        if (this.bridge.state.result) {
          actions.push(node("button", {
            type: "button", class: "ghost small", text: "帶我去",
            onclick: () => { this.closeFloat(); this.goToCardSpot(c); },
          }));
        }
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

    /* ---------- 實地練習（Lab）引擎（7.4、7.5） ---------- */
    async startLab(labId) {
      if (this.bridge?.isPopout) return;
      const card = CARDS.find((c) => c.id === labId && c.isLab);
      if (!card) return;
      this.closeFloat();
      this.closeSpotlight();
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
      this.prefs.whatsnewSeen = this.statusInfo?.version || this.whatsnewData?.versions?.[0]?.version || "0.2.0";
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
