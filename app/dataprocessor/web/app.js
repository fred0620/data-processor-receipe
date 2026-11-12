"use strict";
/* 資料處理器前端。所有內容都用 textContent 放進畫面，不用 innerHTML，資料裡的文字不會被當成 HTML。 */
const $ = (id) => document.getElementById(id);

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (key === "dataset") Object.assign(node.dataset, value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

/* replaceChildren 會把 null 印成文字，這裡先濾掉 */
function put(node, ...children) {
  node.replaceChildren(...children.flat().filter((c) => c !== null && c !== undefined && c !== false));
}

function summary(values, limit = 6) {
  return Object.values(values).filter((v) => v !== null && v !== "").slice(0, limit).join("・");
}

/* action：{ text, run }，在訊息旁放一個按鈕（例如「復原」），給多一點時間按 */
function toast(message, bad = false, action = null) {
  const node = $("toast");
  node.replaceChildren(el("span", { text: message }));
  if (action) {
    node.append(el("button", { type: "button", class: "small ghost toast-action", text: action.text,
      onclick: () => { node.hidden = true; action.run(); } }));
  }
  node.classList.toggle("bad", bad);
  node.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { node.hidden = true; }, action ? 12000 : 5000);
}

/* 重新檢查：按第一次顯示會清掉多少，再按一次才清，避免誤按；清完可以復原 */
function resetButton(result) {
  const button = $("resetButton");
  clearTimeout(resetButton.timer);
  button.classList.remove("confirming");
  button.hidden = result.status === "error";
  button.disabled = !result.decisions;
  button.replaceChildren(icon("reset"), el("span", { text: "重新檢查" }));
  button.title = result.decisions ? "清掉這個檔案的修改、指定的配對和確認，從頭再檢查一次" : "還沒有人工修改、指定或確認";
  button.onclick = async () => {
    if (!button.classList.contains("confirming")) {
      button.classList.add("confirming");
      button.replaceChildren(icon("reset"), el("span", { text: `清掉 ${result.decisions} 項人工決定？再按一次` }));
      resetButton.timer = setTimeout(() => resetButton(state.result), 4000);
      return;
    }
    if (await act("reset")) {
      toast("已清掉人工決定，可以從頭檢查。補上的對照表沒有清除。", false,
        { text: "復原", run: async () => { if (await act("restore")) toast("已復原重設前的檢查"); } });
    }
  };
}

class ApiError extends Error {
  constructor(message, problems) { super(message); this.problems = problems || []; }
}

async function api(path, options = {}) {
  const init = { ...options };
  if (!(options.body instanceof FormData)) init.headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  document.body.classList.add("busy");
  try {
    const response = await fetch(path, init);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new ApiError(data.error || "請求失敗", data.problems);
    return data;
  } finally {
    document.body.classList.remove("busy");
  }
}

const post = (path, body) => api(path, { method: "POST", body: JSON.stringify(body || {}) });

function showError(error, title = "無法完成") {
  if (error.problems && error.problems.length) showProblems(title, error.problems);
  else toast(error.message, true);
}

/* ---------- 對話框 ---------- */
/* ---------- 圖示 ---------- */
/* Stageshow 的圖示規則：一套線條、同樣粗細（1.5）、用文字顏色。這裡自己畫，不從網路下載圖示套件。 */
const ICONS = {
  x: "M4 4l8 8M12 4l-8 8",
  external: "M5.5 10.5l5-5M6.75 5.5h3.75v3.75M3.25 4.75v8h8",
  popin: "M10.5 5.5l-5 5M9.25 10.5H5.5V6.75M4.75 3.25h8v8",
  download: "M8 2.75v7.5M5 7.5l3 3 3-3M3 13h10",
  reset: "M2.75 8a5.25 5.25 0 1 0 1.55-3.72M2.75 2.75v2.5h2.5",
  undo: "M5.75 4.25L3.25 6.75l2.5 2.5M3.25 6.75h6.5a3 3 0 0 1 0 6H7.5",
  check: "M3.5 8.5l3 3 6-7",
  left: "M10 3.5L5.5 8l4.5 4.5",
  up: "M3.5 10L8 5.5l4.5 4.5",
  down: "M3.5 6L8 10.5 12.5 6",
  right: "M6 3.5L10.5 8 6 12.5",
  arrow: "M3 8h10M9 4l4 4-4 4",
  columns: "M2.75 3.25h10.5v9.5H2.75zM6.25 3.25v9.5M9.75 3.25v9.5",
  wrap: "M2.75 4h10.5M2.75 8h8.25a2 2 0 0 1 0 4H8.75M10.25 10.5l-1.5 1.5 1.5 1.5M2.75 12h3.5",
  dense: "M2.75 3.5h10.5M2.75 6.5h10.5M2.75 9.5h10.5M2.75 12.5h10.5",
  sheet: "M2.75 2.75h10.5v10.5H2.75zM2.75 6.25h10.5M2.75 9.75h10.5M6.25 2.75v10.5",
  eye: "M1.75 8s2.25-4.5 6.25-4.5S14.25 8 14.25 8 12 12.5 8 12.5 1.75 8 1.75 8zM8 10a2 2 0 1 0 0-4 2 2 0 0 0 0 4z",
  trash: "M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.5 8.5h6l.5-8.5",
  plus: "M8 3v10M3 8h10",
  help: "M8 14.25a6.25 6.25 0 1 0 0-12.5 6.25 6.25 0 0 0 0 12.5zM6.25 6.25a1.75 1.75 0 1 1 2.4 1.62c-.42.18-.65.57-.65 1.03v.35M8 11.25v.01",
  panel: "M2.75 2.75h10.5v10.5H2.75zM6.25 2.75v10.5",
  copy: "M5.5 5.5h7v7h-7zM3.5 10.5v-7h7",
  edit: "M10.5 2.75l2.75 2.75L6 12.75H3.25V10z",
};

function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 16 16");
  svg.setAttribute("aria-hidden", "true");
  svg.classList.add("icon");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", ICONS[name]);
  svg.append(path);
  return svg;
}

/* 按鈕依 Stageshow：primary（強調色，一個區塊只留給最主要的動作）、default（白底細框）、
   ghost（透明，滑過才有底色，次要動作的預設）、quiet（文字按鈕，給清單、卡片裡的小動作）。
   只有圖示的按鈕一定要有 label：滑過會顯示，螢幕閱讀器也讀得到。 */
function btn({ text = "", icon: name = null, variant = "ghost", size = "small", label = null, pressed, danger = false, extra = "", ...rest }) {
  const classes = [variant === "default" ? "" : variant, size === "small" ? "small" : "", text ? "" : "icon-btn", danger ? "danger" : "", extra];
  return el("button", {
    type: "button", class: classes.filter(Boolean).join(" ") || null,
    "aria-label": label, title: rest.title || label,
    "aria-pressed": pressed === undefined ? null : String(Boolean(pressed)), ...rest,
  }, name ? icon(name) : null, text ? el("span", { text }) : null);
}

function openDialog(title, body, actions) {
  $("dialogTitle").textContent = title;
  put($("dialogBody"), body);
  put($("dialogActions"), actions);
  if (!$("dialog").open) $("dialog").showModal();
}
const closeDialog = () => $("dialog").close();

function copyText(text) {
  navigator.clipboard?.writeText(text).then(() => toast("已複製"), () => toast("無法複製，請手動選取", true));
}

function problemsText(problems) {
  return "這份 recipe 檢查不通過，請依照規格（docs/recipe-spec.md）修正以下問題，並回傳完整的 recipe：\n"
    + problems.map((p) => `- ${p}`).join("\n");
}

function showProblems(title, problems) {
  openDialog(title, [
    el("p", { class: "muted", text: "可以把下面的問題整段複製給 AI，請它修正 recipe。" }),
    el("ul", { class: "problems" }, problems.map((p) => el("li", { text: p }))),
  ], [
    btn({ text: "複製給 AI", icon: "copy", variant: "default", size: "normal", onclick: () => copyText(problemsText(problems)) }),
    el("button", { type: "button", class: "primary", text: "關閉", onclick: closeDialog }),
  ]);
}

/* ---------- 狀態 ---------- */
const state = {
  recipes: [], recipeId: null, workbook: null, result: null,
  tab: "rows", filter: "review", search: "", selected: null, stageOpen: null,
  matchName: null, matchFilter: "todo", matchSearch: "", pickerFor: null, matchFocus: null, matchAll: false, matchOpen: new Set(),
  issueFilter: "review", issueFocus: null, checked: new Set(),   // issueFocus：只看某一類警示 {stage, code, label}
  traces: {}, openTrace: new Set(),   // 執行紀錄：好奇時才向程式要，要過的先記著
};
const LEVEL_TEXT = { review: "需檢查", notice: "提示", error: "無法執行" };
/* 警示被處理的方式：留在畫面上當紀錄，不會直接消失 */
const RESOLVED_TEXT = { edited: "已人工修改", mapped: "已補對照", matched: "已人工配對" };
const handledText = (issue) => RESOLVED_TEXT[issue.resolved] || "已確認";
const STAGE_TEXT = { load: "Load", gate: "Gate", normalize: "Normalize", match: "Match", transform: "Transform", validate: "Validate", mapping: "Mapping", export: "Export" };
const MATCH_TEXT = { auto: ["已配對", "ok"], review: ["待確認", "review"], confirmed: ["已確認", "manual"], manual: ["人工指定", "manual"], none: ["確認沒有", "manual"], ambiguous: ["待選擇", "review"], unmatched: ["找不到", "missing"] };

/* 畫面偏好（顯示哪些欄位、緊湊或寬鬆）只存在這台電腦的瀏覽器，存不了也不影響使用 */
const prefs = {
  get(key, fallback) {
    try { const value = JSON.parse(window.localStorage.getItem(`dp:${key}`)); return value ?? fallback; } catch (_e) { return fallback; }
  },
  set(key, value) {
    try { window.localStorage.setItem(`dp:${key}`, JSON.stringify(value)); } catch (_e) { /* 無痕或停用儲存時略過 */ }
  },
};

/* ---------- 版面：左欄與細節可以拖曳調整寬度、左欄可以收起 ---------- */
const PANES = {
  side: { split: "sideSplit", css: "--side-w", fallback: 272, min: 200, max: 520, edge: "left" },
  drawer: { split: "drawerSplit", css: "--drawer-w", fallback: 360, min: 280, max: 900, edge: "right" },
};

function paneWidth(name, width) {
  const pane = PANES[name];
  const room = window.innerWidth - 360;   // 中間至少留 360px 給結果
  const value = Math.round(Math.max(pane.min, Math.min(pane.max, room, width)));
  document.querySelector(".layout").style.setProperty(pane.css, `${value}px`);
  return value;
}

function setupPanes() {
  const layout = document.querySelector(".layout");
  for (const [name, pane] of Object.entries(PANES)) {
    paneWidth(name, prefs.get(`${name}Width`, pane.fallback));
    const split = $(pane.split);
    split.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      split.setPointerCapture(event.pointerId);
      split.classList.add("dragging");
      document.body.classList.add("resizing");
      const box = layout.getBoundingClientRect();
      const move = (e) => paneWidth(name, pane.edge === "left" ? e.clientX - box.left : box.right - e.clientX);
      const stop = () => {
        split.removeEventListener("pointermove", move);
        split.classList.remove("dragging");
        document.body.classList.remove("resizing");
        prefs.set(`${name}Width`, parseInt(getComputedStyle(layout).getPropertyValue(pane.css), 10));
      };
      split.addEventListener("pointermove", move);
      split.addEventListener("pointerup", stop, { once: true });
      split.addEventListener("pointercancel", stop, { once: true });
    });
    split.addEventListener("dblclick", () => prefs.set(`${name}Width`, paneWidth(name, pane.fallback)));
    split.addEventListener("keydown", (event) => {   // 鍵盤也能調整：左右鍵
      const step = { ArrowLeft: -16, ArrowRight: 16 }[event.key];
      if (!step) return;
      event.preventDefault();
      const now = parseInt(getComputedStyle(layout).getPropertyValue(pane.css), 10);
      prefs.set(`${name}Width`, paneWidth(name, now + (pane.edge === "left" ? step : -step)));
    });
  }
  const collapse = (on) => {
    layout.classList.toggle("side-collapsed", on);
    $("sideToggle").title = on ? "展開左欄" : "收起左欄";
    $("sideToggle").setAttribute("aria-label", $("sideToggle").title);
    $("sideToggle").setAttribute("aria-pressed", String(on));
    prefs.set("sideCollapsed", on);
  };
  collapse(prefs.get("sideCollapsed", false));
  $("sideToggle").addEventListener("click", () => collapse(!layout.classList.contains("side-collapsed")));
  window.addEventListener("resize", () => {
    for (const [name, pane] of Object.entries(PANES)) paneWidth(name, prefs.get(`${name}Width`, pane.fallback));
  });
}

/* ---------- Recipe ---------- */
async function loadRecipes(selectId) {
  const data = await api("/api/recipes");
  state.recipes = data.recipes;
  if (selectId) state.recipeId = selectId;
  if (!state.recipes.some((r) => r.id === state.recipeId)) {
    state.recipeId = (state.recipes.find((r) => !r.problems.length) || {}).id || null;
  }
  renderRecipes();
}

function renderRecipes() {
  const list = $("recipeList");
  if (!state.recipes.length) {
    list.replaceChildren(el("p", { class: "muted", text: "還沒有 recipe，按「新增」放一份進來。" }));
  } else {
    list.replaceChildren(...state.recipes.map((r) => el("div", {},
      el("button", {
        type: "button", class: `recipe-item${r.id === state.recipeId ? " active" : ""}`,
        onclick: () => { state.recipeId = r.id; renderRecipes(); },
      },
      el("div", { class: "name", text: r.name }),
      r.description ? el("div", { class: "desc", text: r.description }) : null,
      r.problems.length ? el("div", { class: "bad", text: `有 ${r.problems.length} 個問題，無法使用` }) : null),
      r.id === state.recipeId ? el("div", { class: "recipe-tools" },
        el("button", { type: "button", class: "link", text: "查看", onclick: () => viewRecipe(r) }),
        r.problems.length ? el("button", { type: "button", class: "link", text: "問題清單", onclick: () => showProblems(`${r.name} 的問題`, r.problems) }) : null,
        el("button", { type: "button", class: "link danger", text: "刪除", onclick: () => deleteRecipe(r) })) : null)));
  }
  updateRunButton();
}

/* recipe 的邏輯說明：由程式依 recipe 產生，和實際執行的邏輯一致。
   以一列資料為主角，依序寫出會經過的判斷；其他資料表的讀法放在後面。 */
function explainNode(node, index = null) {
  const code = node.code ? el("details", { class: "explain-code" }, el("summary", { text: "SQL 原文" }), el("pre", { text: node.code })) : null;
  const children = node.children.length ? el("ul", { class: "flow-children" }, node.children.map((child) => explainNode(child))) : null;
  if (node.kind === "detail") {
    return el("li", { class: "flow-detail" }, el("details", {}, el("summary", { text: node.text }), children));
  }
  return el("li", { class: `flow-${node.kind}` },
    index !== null ? el("span", { class: "flow-index", text: index }) : null,
    el("div", { class: "flow-body" }, el("div", { class: "flow-text", text: node.text }), children, code));
}

function explainView(data) {
  return el("div", { class: "explain" },
    data.description ? el("p", { class: "explain-lead", text: data.description }) : null,
    el("h4", { text: `每一列${data.subject}會經過` }),
    el("ol", { class: "flow" }, data.flow.map((node, i) => explainNode(node, i + 1))),
    data.sources.length ? [el("h4", { text: "其他資料表怎麼讀" }),
      el("ul", { class: "flow" }, data.sources.map((node) => explainNode(node)))] : null);
}

async function viewRecipe(recipe) {
  try {
    const [data, info] = await Promise.all([api(`/api/recipes/${encodeURIComponent(recipe.id)}`),
      api(`/api/recipes/${encodeURIComponent(recipe.id)}/explain`).catch(() => null)]);
    const area = el("textarea", { readonly: true });
    area.value = data.text;
    const body = el("div");
    const show = (mode) => {
      put(body, chips([["explain", "說明"], ["yaml", "YAML"]], mode, show),
        mode === "explain" && info ? explainView(info) : area);
    };
    show(info ? "explain" : "yaml");
    openDialog(recipe.name, body, [
      btn({ text: "複製 YAML", icon: "copy", variant: "default", size: "normal", onclick: () => copyText(data.text) }),
      btn({ text: "修改", icon: "edit", variant: "default", size: "normal", onclick: () => editRecipe(data.text) }),
      el("button", { type: "button", class: "primary", text: "關閉", onclick: closeDialog }),
    ]);
  } catch (error) { showError(error); }
}

async function deleteRecipe(recipe) {
  if (!window.confirm(`確定刪除「${recipe.name}」？`)) return;
  try {
    await api(`/api/recipes/${encodeURIComponent(recipe.id)}`, { method: "DELETE" });
    await loadRecipes();
  } catch (error) { showError(error); }
}

async function copySpec() {
  try { copyText((await api("/api/spec")).text); } catch (error) { showError(error); }
}

function editRecipe(text = "") {
  const area = el("textarea", { placeholder: "把 AI 寫好的 recipe（YAML）貼在這裡，或選擇 .yaml 檔案" });
  area.value = text;
  const file = el("input", { type: "file", accept: ".yaml,.yml,.txt", hidden: true });
  file.addEventListener("change", async () => { if (file.files[0]) area.value = await file.files[0].text(); });
  const problems = el("div");
  const showProblems = (error) => {
    if (!error.problems.length) { toast(error.message, true); return; }
    put(problems, el("ul", { class: "problems" }, error.problems.map((p) => el("li", { text: p }))),
      el("button", { type: "button", class: "link", text: "複製問題給 AI", onclick: () => copyText(problemsText(error.problems)) }));
  };
  const save = async () => {
    try {
      const data = await post("/api/recipes", { text: area.value });
      closeDialog();
      await loadRecipes(data.id);
      /* 正在看的結果用的就是這份 recipe：直接用新版重新處理，人工修改與確認都會保留 */
      if (state.result && state.result.recipe.id === data.id && await act("rerun")) {
        toast(`已儲存「${data.name}」，並用新版重新處理目前的檔案`);
      } else toast(`已儲存「${data.name}」`);
    } catch (error) { editStep(); showProblems(error); }
  };
  /* 第二步：先看白話說明，確認邏輯對了才存 */
  const review = async () => {
    try {
      const info = await post("/api/recipes/explain", { text: area.value });
      openDialog(`確認「${info.name}」的處理方式`, [
        el("p", { class: "muted", text: "下面是程式依 recipe 整理的說明，和實際執行的邏輯一致。確認每一步都符合你的規則再儲存；不對的地方回去請 AI 修改。" }),
        explainView(info),
      ], [
        btn({ text: "返回修改", icon: "left", variant: "default", size: "normal", onclick: editStep }),
        el("button", { type: "button", class: "primary", text: "確認並儲存", onclick: save }),
      ]);
    } catch (error) { showProblems(error); }
  };
  const editStep = () => openDialog("新增或更新 recipe", [
    el("p", { class: "muted" }, "先把規格複製給 AI，連同你的欄位與處理規則請它寫 recipe，再貼回這裡。下一步會把 recipe 翻成白話讓你確認。 ",
      el("button", { type: "button", class: "link accent", text: "複製規格給 AI", onclick: copySpec })),
    area, problems,
  ], [
    btn({ text: "選擇檔案", variant: "default", size: "normal", onclick: () => file.click() }), file,
    btn({ text: "取消", size: "normal", onclick: closeDialog }),
    el("button", { type: "button", class: "primary", text: "下一步：確認說明", onclick: review }),
  ]);
  editStep();
}

/* ---------- 資料檔 ---------- */
async function uploadWorkbook(file) {
  const form = new FormData();
  form.append("file", file);
  try {
    setWorkbook(await api("/api/workbooks", { method: "POST", body: form }));
  } catch (error) { showError(error); }
}

function setWorkbook(workbook) {
  state.workbook = workbook;
  $("workbookLabel").textContent = "換一個檔案";
  $("workbookInfo").replaceChildren(
    el("strong", { text: workbook.name }),
    el("div", { text: workbook.sheets.map((s) => `${s.name}（${s.rows} 列）`).join("、") }));
  updateRunButton();
}

async function loadSamples() {
  try {
    const data = await api("/api/samples");
    $("sampleBox").replaceChildren(...data.samples.map((name) => el("button", {
      type: "button", class: "link", text: `使用範例：${name}`,
      onclick: async () => { try { setWorkbook(await post(`/api/samples/${encodeURIComponent(name)}`)); } catch (error) { showError(error); } },
    })));
  } catch (_error) { /* 沒有範例就不顯示 */ }
}

function updateRunButton() {
  const recipe = state.recipes.find((r) => r.id === state.recipeId);
  $("runButton").disabled = !(recipe && !recipe.problems.length && state.workbook);
}

async function runNow() {
  try {
    state.selected = null;
    state.checked.clear();
    setResult(await post("/api/runs", { recipe: state.recipeId, workbook: state.workbook.id }), true);
  } catch (error) { showError(error, "無法執行"); }
}

/* ---------- 結果 ---------- */
async function act(path, body) {
  try {
    setResult(await post(`/api/runs/${state.result.run_id}/${path}`, body));
    return true;
  } catch (error) { showError(error); return false; }
}

/* ---------- Pop out / Pop in ---------- */
/* Pop out 把「目前的分頁」搬到另一個瀏覽器視窗，可以拖到另一個螢幕看完整的表格。
   搬出去的分頁在主視窗只留一行說明，不會兩邊各顯示一份；其他分頁照常在主視窗使用，
   所以兩個螢幕可以看不同的東西（例如一邊看結果、一邊處理配對）。
   每個視窗都能修改，任何一個視窗更新結果，其他視窗用 BroadcastChannel 同步。
   從一個視窗跳到另一個視窗的分頁（例如在結果裡按「前往配對」），會交給擁有那個分頁的視窗顯示。 */
const pageParams = new URLSearchParams(location.search);
const isPopout = pageParams.has("run");
const ownTab = isPopout ? (pageParams.get("tab") || "rows") : null;
const channel = window.BroadcastChannel ? new BroadcastChannel("dataprocessor") : null;
const popped = new Map();   // 主視窗：分頁 → pop out 視窗（重新整理後拿不到視窗，只知道分頁在外面）
const TAB_NAMES = { rows: "結果", match: "配對", mapping: "對照表", excluded: "排除", issues: "所有警示", source: "原始資料" };

function popOut() {
  const tab = state.tab;
  const known = popped.get(tab);
  if (known && known.win && !known.win.closed) { known.win.focus(); return; }
  const r = state.result;
  const url = `/?run=${encodeURIComponent(r.run_id)}&tab=${encodeURIComponent(tab)}`;
  const w = Math.min(screen.availWidth, 1600), h = Math.min(screen.availHeight, 1000);
  const win = window.open(url, `dp-${tab}`, `popup,width=${w},height=${h}`);
  if (!win) { toast("瀏覽器擋下了新視窗，請允許這個網站開啟彈出式視窗後再試一次", true); return; }
  popped.set(tab, { win });
  const rest = tabList().find(([id]) => !popped.has(id));   // 主視窗換到還在這裡的分頁
  if (rest) { state.tab = rest[0]; state.issueFocus = null; }
  renderTabs();
}

function popInAll() {
  channel?.postMessage({ type: "popin-all" });
  for (const { win } of popped.values()) if (win && !win.closed) win.close();
  popped.clear();
  renderTabs();
}

function popIn() {
  channel?.postMessage({ type: "popin", tab: ownTab, run_id: state.result?.run_id, view: viewState() });
  window.close();
  // 不是由主視窗開的（例如重新整理過），關不掉時就回到一般畫面
  setTimeout(() => { location.href = "/"; }, 300);
}

/* Pop in 時把這個分頁的檢視狀態（篩選、搜尋、選到的列）帶回主視窗，不用重新找 */
function viewState() {
  const keys = ["filter", "search", "selected", "matchName", "matchFilter", "matchSearch", "matchFocus", "issueFilter", "issueFocus"];
  return Object.fromEntries(keys.map((k) => [k, state[k]]));
}

/* 換到某個分頁：分頁在另一個視窗時交給那個視窗顯示，並切過去 */
function goTo(changes) {
  const tab = changes.tab || state.tab;
  if (isPopout && tab !== ownTab) {
    channel?.postMessage({ type: "show", target: "main", changes });
    try { window.opener?.focus(); } catch (_e) { /* 主視窗已關閉 */ }
    toast(`已在主視窗打開「${TAB_NAMES[tab] || tab}」`);
    return;
  }
  if (!isPopout && popped.has(tab)) {
    channel?.postMessage({ type: "show", target: tab, changes });
    popped.get(tab).win?.focus();
    toast(`已在 pop out 視窗打開「${TAB_NAMES[tab] || tab}」`);
    return;
  }
  Object.assign(state, changes);
  renderTabs();
}

channel?.addEventListener("message", ({ data }) => {
  if (data.type === "result") {
    const same = state.result && state.result.run_id === data.result.run_id;
    if (same) setResult(data.result, false, true);
    else if (isPopout) setResult(data.result, true, true);   // 主視窗換了新的處理，pop out 視窗跟著換
  } else if (data.type === "show") {
    if (isPopout && data.target === ownTab) { Object.assign(state, data.changes, { tab: ownTab }); renderTabs(); window.focus(); }
    if (!isPopout && data.target === "main") { goTo(data.changes); window.focus(); }
  } else if (isPopout) {
    if (data.type === "popin-all" || (data.type === "popin-tab" && data.tab === ownTab)) popIn();
    if (data.type === "ping") channel.postMessage({ type: "hello", tab: ownTab });
  } else if (data.type === "hello") {
    if (!popped.has(data.tab)) popped.set(data.tab, { win: null });
    if (state.result) renderTabs();
  } else if (data.type === "closed") {
    popped.delete(data.tab);
    if (state.result) renderTabs();
  } else if (data.type === "popin") {
    popped.delete(data.tab);
    if (state.result && data.run_id === state.result.run_id) { Object.assign(state, data.view || {}, { tab: data.tab }); renderTabs(); }
    window.focus();
  }
});

if (!isPopout) {
  channel?.postMessage({ type: "ping" });   // 主視窗重新整理後，問問看哪些分頁還在外面
  setInterval(() => {                         // 視窗被直接關掉、來不及通知時
    let changed = false;
    for (const [tab, { win }] of popped) if (win && win.closed) { popped.delete(tab); changed = true; }
    if (changed && state.result) renderTabs();
  }, 1500);
}

async function startPopout() {
  document.body.classList.add("popout");
  $("popInButton").hidden = false;
  $("popInButton").addEventListener("click", popIn);
  window.addEventListener("pagehide", () => channel?.postMessage({ type: "closed", tab: ownTab }));
  channel?.postMessage({ type: "hello", tab: ownTab });
  try {
    state.tab = ownTab;
    setResult(await api(`/api/runs/${encodeURIComponent(pageParams.get("run"))}`), true, true);
  } catch (error) {
    put($("empty"), el("h2", { text: "這個結果已經不在了" }),
      el("p", { class: "muted", text: "工具重新啟動過，或主視窗已經換成別的處理。請關閉這個視窗，回到主視窗重新執行。" }));
  }
}

/* 主視窗裡已經 pop out 的分頁：只留一行說明，不重複顯示同一份內容 */
function renderPoppedNote() {
  const name = TAB_NAMES[state.tab] || state.tab;
  const known = popped.get(state.tab);
  put($("tabBody"), el("div", { class: "popped-note" },
    el("h3", { text: `「${name}」在 pop out 視窗` }),
    el("p", { class: "muted", text: "在那個視窗做的修改，會同步到這裡的其他分頁。" }),
    el("div", { class: "actions-row" },
      known && known.win && !known.win.closed
        ? btn({ text: "切到那個視窗", icon: "external", variant: "default", onclick: () => known.win.focus() }) : null,
        el("button", { type: "button", class: "primary small", onclick: () => {
        channel?.postMessage({ type: "popin-tab", tab: state.tab });
        if (known && known.win && !known.win.closed) known.win.close();
        popped.delete(state.tab);
        renderTabs();
        } }, icon("popin"), el("span", { text: "Pop in" })))));
        }

/* 另一個視窗更新時，若這個視窗正在打字（細節的欄位、搜尋框），先不重畫，離開輸入框後再更新，打到一半的字不會不見 */
function isTyping() {
  const node = document.activeElement;
  return Boolean(node && node.matches("input:not([type=checkbox]):not([type=file]), textarea, select") && node.closest("#result, #drawer"));
}
let pendingRemote = null;
document.addEventListener("focusout", () => setTimeout(() => {
  if (pendingRemote && !isTyping()) { const next = pendingRemote; pendingRemote = null; setResult(next.result, next.fresh, true); }
}, 0), true);

function setResult(result, fresh = false, remote = false) {
  if (remote && isTyping()) { pendingRemote = { result, fresh }; return; }
  pendingRemote = null;
  if (!remote) channel?.postMessage({ type: "result", result });
  state.result = result;
  if (isPopout) document.title = `${result.recipe.name}・${result.workbook.name}`;
  state.traces = {};
  if (fresh) {
    state.tab = isPopout ? ownTab : result.status === "error" ? "issues" : "rows";
    if (!isPopout && popped.has(state.tab)) state.tab = (tabList(result).find(([id]) => !popped.has(id)) || [state.tab])[0];
    state.filter = result.counts.review ? "review" : "all";
    state.issueFilter = result.status === "error" ? "all" : "review";
    state.matchName = result.matches[0]?.name || null;
    state.stageOpen = result.status === "error" ? result.stages.find((s) => s.status === "error")?.id : null;
    }
    /* 一開始就打開第一筆要看的列：細節在右邊，可以直接開始檢查 */
    if (state.tab === "rows" && result.status !== "error" && !result.output.rows.some((x) => x.rid === state.selected)) {
      state.selected = visibleRows(result)[0]?.rid || null;
    }
  $("empty").hidden = true;
  $("result").hidden = false;
  $("resultTitle").textContent = result.recipe.name;
  const rows = result.output.rows;
  const reviewRows = rows.filter((r) => r.status === "review").length;
  $("resultSub").textContent = result.status === "error" ? `${result.workbook.name}・無法執行`
    : `${result.workbook.name}・${rows.length} 列・${reviewRows} 列需檢查`;
  const status = $("runStatus");
  status.hidden = false;
  put(status, el("span", { class: `dot ${result.status}` }),
    { ok: "全部正常", review: `${result.counts.review} 個地方需檢查`, error: "無法執行" }[result.status] || "全部正常");
  renderProgress(result);
  $("exportButton").href = `/api/runs/${result.run_id}/export`;
  resetButton(result);
  $("exportButton").toggleAttribute("hidden", result.status === "error");
  renderPipeline();
  renderTabs();
}

/* 檢查進度（Stageshow 的 Meter）：需要人看的列裡，已經處理了幾列 */
function renderProgress(result) {
  const rows = result.output.rows;
  const open = rows.filter((x) => x.status === "review").length;
  const done = rows.filter((x) => x.status === "confirmed").length;
  const total = open + done;
  const node = $("progress");
  node.hidden = result.status === "error";
  if (!total) { put(node, el("span", { class: "progress-text", text: "沒有需要人工檢查的列" })); return; }
  put(node,
    el("span", { class: "meter", role: "meter", "aria-valuemin": "0", "aria-valuemax": String(total), "aria-valuenow": String(done),
      "aria-label": "檢查進度" }, el("i", { style: `width:${Math.round((done / total) * 100)}%` })),
    el("span", { class: "progress-text", text: open ? `已處理 ${done} / ${total} 列` : `${total} 列都已處理，可以下載` }));
}

/* 流程：卡片只放一句摘要，點開才看細節 */
function renderPipeline() {
  const stages = state.result.stages;
  const open = stages.find((s) => s.id === state.stageOpen);
  put($("pipeline"), stages.map((stage) => el("li", {},
    el("button", {
      type: "button", class: `stage ${stage.status}${state.stageOpen === stage.id ? " open" : ""}`,
      onclick: () => { state.stageOpen = state.stageOpen === stage.id ? null : stage.id; renderPipeline(); },
    },
    el("span", { class: "label" }, el("span", { class: `dot ${stage.status === "skip" ? "" : stage.status}` }), STAGE_TEXT[stage.id]),
    el("span", { class: "summary", text: stage.summary || (stage.status === "skip" ? "未執行" : "") })))));
  const detail = $("stageDetail");
  detail.hidden = !open;
  if (open) {
    put(detail, el("h3", { text: open.label }),
      open.checks || (open.groups && open.groups.length) ? null : el("ul", {}, open.lines.length ? open.lines.map((line) => el("li", { class: line.startsWith("　") ? "sub" : null, text: line.trim() }))
        : el("li", { class: "muted", text: "沒有細節" })),
      stageLinks(open));
  }
}

/* 每張卡片都可以直接跳到相關的列：卡片上的數字和點進去看到的是同一批 */
function stageLinks(stage) {
  const r = state.result;
  const go = (changes) => () => goTo({ issueFocus: null, ...changes });
  const issuesOf = (test) => activeIssues().filter(test);
  const items = [];
  const link = (text, extra, onclick) => el("li", {}, text, extra ? el("span", { class: "muted", text: extra }) : null,
    onclick ? el("button", { type: "button", class: "link", style: "margin-left:10px", text: "查看", onclick }) : null);
  if (stage.id === "load") {
    const notes = issuesOf((i) => i.stage === "load");
    if (notes.length) items.push(link(`讀取時的提醒 ${notes.length} 則`, null, go({ tab: "issues", issueFilter: "all", issueFocus: { stage: "load", label: "讀取時的提醒" } })));
  } else if (stage.id === "gate") {
    if (r.excluded.length) items.push(link(`排除 ${r.excluded.length} 列`, null, go({ tab: "excluded" })));
  } else if (stage.id === "normalize") {
    for (const g of stage.groups || []) {
      items.push(link(`${g.label} ${g.open + g.done} 格`, g.done ? `（已處理 ${g.done}）` : null,
        go({ tab: "issues", issueFilter: "all", issueFocus: { stage: "normalize", code: g.code, label: g.label } })));
    }
  } else if (stage.id === "match") {
    for (const m of r.matches) {
      items.push(link(`${m.label}：${m.counts.todo} 列待處理`, null,
        go({ tab: "match", matchName: m.name, matchFilter: m.counts.todo ? "todo" : "all", matchFocus: null })));
    }
  } else if (stage.id === "validate") {
    for (const check of stage.checks || []) {
      items.push(link(`${check.message}：${check.rows} 列`, check.done ? `（已處理 ${check.done}）` : null,
        check.rows ? go({ tab: "issues", issueFilter: "all", issueFocus: { code: check.code, label: check.message } }) : null));
    }
  } else if (stage.id === "mapping") {
    const pending = r.unmapped.filter((u) => u.missing === "ask").length;
    if (r.mappings.length) items.push(link(`待補對照 ${pending} 種寫法`, null, go({ tab: "mapping" })));
    const edited = r.output.rows.filter((x) => Object.keys(x.edited).length).length;
    if (edited) items.push(link(`人工修改 ${edited} 列`, null, go({ tab: "rows", filter: "confirmed" })));
  } else if (stage.id === "export") {
    const review = r.output.rows.filter((x) => x.status === "review").length;
    const done = r.output.rows.filter((x) => x.status === "confirmed").length;
    items.push(link(`需檢查 ${review} 列`, null, review ? go({ tab: "rows", filter: "review" }) : null));
    if (done) items.push(link(`已確認 ${done} 列`, null, go({ tab: "rows", filter: "confirmed" })));
  }
  return items.length ? el("ul", { class: "stage-links" }, items) : null;
}

function activeIssues() { return state.result.issues.filter((i) => i.level !== "skip"); }

function tabList(r = state.result) {
  const pendingMaps = r.unmapped.filter((u) => u.missing === "ask").length;
  const todo = r.matches.reduce((n, m) => n + (m.counts.todo || 0), 0);
  const open = r.issues.filter((i) => i.level !== "skip" && !i.dismissed && i.level !== "notice").length;
  return [
    ["rows", "結果", r.output.rows.filter((x) => x.status === "review").length],
    r.matches.length ? ["match", "配對", todo] : null,
    r.mappings.length ? ["mapping", "對照表", pendingMaps] : null,
    r.excluded.length ? ["excluded", "排除", r.excluded.length, true] : null,
    ["issues", "所有警示", open],
    ["source", "原始資料", 0],
    ].filter(Boolean);
}

function renderTabs() {
  let tabs = tabList();
  if (isPopout) {
    state.tab = ownTab;
    tabs = tabs.filter(([id]) => id === ownTab);   // pop out 視窗只負責一個分頁
  }
  if (!tabs.some((t) => t[0] === state.tab)) state.tab = tabs[0]?.[0] || "rows";
  const away = (id) => !isPopout && popped.has(id);
  put($("tabs"), tabs.map(([id, label, n, plain]) => el("button", {
    type: "button", class: `tab${state.tab === id ? " active" : ""}${away(id) ? " away" : ""}`,
    title: away(id) ? "在 pop out 視窗" : null,
    onclick: () => { if (!isPopout) { state.tab = id; state.issueFocus = null; renderTabs(); } },
  }, label, away(id) ? el("span", { class: "away-mark", text: "↗" }) : null,
  n ? el("span", { class: `count${plain ? "" : " review"}`, text: n }) : null)),
  isPopout ? null : el("div", { class: "tab-tools" },
    popped.size ? btn({ text: "全部 Pop in", icon: "popin", onclick: popInAll }) : null,
    away(state.tab) ? null : btn({ text: "Pop out", icon: "external", onclick: popOut,
      title: "把這個分頁搬到另一個視窗，可以拖到另一個螢幕看完整的表格。兩邊的修改會同步。" })));
  if (away(state.tab)) renderPoppedNote();
  else ({ rows: renderRows, match: renderMatch, mapping: renderMapping, excluded: renderExcluded, issues: renderIssues, source: renderSource })[state.tab]();
  renderDrawer();
}

function chips(options, current, onPick) {
  return el("div", { class: "chips" }, options.map(([id, label]) => el("button", {
    type: "button", class: `chip${current === id ? " active" : ""}`, text: label, onclick: () => onPick(id),
  })));
}

/* 搜尋時會重畫整個分頁，搜尋框也跟著重建；重畫後把游標放回新的搜尋框原本的位置，才能連續打字 */
function searchBox(value, placeholder, onInput, key) {
  const input = el("input", { class: "search", type: "search", placeholder, dataset: { key } });
  input.value = value;
  let timer;
  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      const typing = document.activeElement === input;
      const [start, end] = [input.selectionStart, input.selectionEnd];
      onInput(input.value);
      const next = document.querySelector(`input.search[data-key="${key}"]`);
      if (typing && next && next !== input) {
        next.focus();
        next.setSelectionRange(start, end);
      }
    }, 200);
  });
  return input;
}

function fmt(value, type) {
  if (value === null || value === undefined || value === "") return "";
  if ((type === "number" || type === "integer") && typeof value === "number") {
    return value.toLocaleString("zh-TW", { maximumFractionDigits: 6 });
  }
  return String(value);
}

function cellIssues(row, column) {
  return row.issues.map((i) => state.result.issues[i]).filter((i) => !i.dismissed && i.out_columns.includes(column));
}

function rowMatches(row, text) {
  if (!text) return true;
  const needle = text.toLowerCase();
  return Object.values(row.values).some((v) => String(v ?? "").toLowerCase().includes(needle))
    || Object.values(row.raw).some((v) => String(v).toLowerCase().includes(needle));
}

/* 顯示哪些欄位、表格密度，依 recipe 記在這台電腦 */
function visibleColumns() {
  const all = state.result.output.columns.map((c) => c.name);
  const hidden = new Set(prefs.get(`hidden:${state.result.recipe.id}`, []));
  return state.result.output.columns.filter((c) => !hidden.has(c.name) || !all.includes(c.name));
}

function columnMenu() {
  const recipeId = state.result.recipe.id;
  const hidden = new Set(prefs.get(`hidden:${recipeId}`, []));
  const menu = el("details", { class: "menu" }, el("summary", { class: "button ghost small" }, icon("columns"), el("span", { text: `欄位${hidden.size ? `（隱藏 ${hidden.size}）` : ""}` })),
    el("div", { class: "menu-body" },
      state.result.output.columns.map((c) => {
        const box = el("input", { type: "checkbox", checked: !hidden.has(c.name) });
        box.addEventListener("change", () => {
          box.checked ? hidden.delete(c.name) : hidden.add(c.name);
          prefs.set(`hidden:${recipeId}`, [...hidden]);
          renderRows(true);
        });
        return el("label", {}, box, c.name);
      }),
      hidden.size ? el("button", { type: "button", class: "link", text: "全部顯示", onclick: () => { prefs.set(`hidden:${recipeId}`, []); renderRows(); } }) : null));
  return menu;
}

const ROW_FILTERS = { all: () => true, review: (x) => x.status === "review", confirmed: (x) => x.status === "confirmed" };
const FILTER_TEXT = { review: "需檢查", confirmed: "已確認", all: "全部" };

function visibleRows(r = state.result) {
  return r.output.rows.filter(ROW_FILTERS[state.filter]).filter((x) => rowMatches(x, state.search));
}

/* 開關（Stageshow 的 Toggle）：設定是開或關，用開關比按鈕清楚 */
function toggle(text, on, onChange, title = null) {
  return el("button", { type: "button", role: "switch", "aria-checked": String(Boolean(on)), class: "switch", title,
    onclick: () => onChange(!on) }, el("span", { class: "switch-track" }), el("span", { text }));
}

function kbd(text) { return el("kbd", { text }); }

function renderRows(keepMenu = false) {
  const r = state.result;
  if (r.status === "error") { renderIssues(); return; }
  const columns = visibleColumns();
  const dense = prefs.get("dense", false);
  const wrap = prefs.get("wrap", false);   // 多行儲存格：換行顯示（最多幾行，超過收起）或壓成一行
  const rows = visibleRows();
  const menuWasOpen = keepMenu && document.querySelector(".menu")?.open;
  const table = el("table", { class: `grid${dense ? " dense" : ""}${wrap ? " wrap" : ""}` },
    el("thead", {}, el("tr", {}, el("th", { class: "status-col" }), el("th", { text: "列" }), columns.map((c) => el("th", { text: c.name, title: c.name })))),
    el("tbody", {}, rows.slice(0, 2000).map((row) => el("tr", {
      class: state.selected === row.rid ? "selected" : null,
      onclick: () => { state.selected = row.rid; renderTabs(); },
    },
    el("td", { class: "status-col" }, el("span", { class: `dot ${row.status}` })),
    el("td", { class: "rowno", text: row.row ?? "", title: row.sheet ? `${row.sheet}・第 ${row.row} 列` : null }),
    columns.map((c) => {
      const flags = cellIssues(row, c.name);
      const settled = row.issues.some((i) => state.result.issues[i].dismissed && state.result.issues[i].out_columns.includes(c.name));
      const value = row.values[c.name];
      const raw = row.raw[c.name];
      const classes = [c.type === "number" || c.type === "integer" ? "num" : "",
        flags.some((i) => i.level === "review") ? "cell-review" : flags.length ? "cell-notice" : "",
        c.name in row.edited ? "cell-edited" : !flags.length && settled ? "cell-confirmed" : ""].filter(Boolean).join(" ");
      const isRaw = (value === null || value === undefined || value === "") && raw;
      const text = isRaw ? raw : fmt(value, c.type);
      const tips = [text, ...flags.map((i) => i.message)];
      if (c.name in row.edited) tips.push(`人工修改，原值：${row.edited[c.name] ?? "（空白）"}`);
      const shown = wrap ? text : String(text).replace(/\n+/g, " ↵ ");
      return el("td", { class: classes || null, title: tips.filter(Boolean).join("\n") || null },
        el("div", { class: `cell-text${isRaw ? " raw" : ""}`, text: shown }));
    })))));
  const menu = columnMenu();
  if (menuWasOpen) menu.open = true;
  put($("tabBody"),
    el("div", { class: "toolbar" },
      chips([["review", "需檢查"], ["confirmed", "已確認"], ["all", "全部"]], state.filter, (id) => { state.filter = id; renderTabs(); }),
      searchBox(state.search, "搜尋", (v) => { state.search = v; renderRows(); }, "rows"),
      el("span", { class: "spacer" }),
      el("span", { class: "muted", text: `${rows.length} 列` }),
      menu,
      toggle("換行", wrap, (on) => { prefs.set("wrap", on); renderRows(); }, "儲存格有多行時換行顯示（最多 4 行）；關閉時壓成一行"),
      toggle("緊湊", dense, (on) => { prefs.set("dense", on); renderRows(); }, "縮小列高，一次看更多列")),
    rows.length ? el("div", { class: "table-wrap" }, table)
      : el("div", { class: "note", text: state.filter === "review" ? "沒有需要檢查的列。" : "沒有符合的列。" }),
    rows.length > 2000 ? el("p", { class: "muted", text: "只顯示前 2000 列，請用搜尋縮小範圍。" }) : null);
}

/* ---------- 單列細節 ---------- */
function issueLine(issue, extra = null) {
  const actions = [];
  if (issue.ref && issue.rid && state.result.matches.some((m) => m.name === issue.ref)) {
    actions.push(el("button", { type: "button", class: "link", text: "前往配對", onclick: () => focusMatch(issue.ref, issue.rid.split("|")[0]) }));
  }
  if (issue.code === "unmapped" && !issue.resolved) actions.push(el("button", { type: "button", class: "link", text: "補對照", onclick: () => goTo({ tab: "mapping" }) }));
  if (extra) actions.push(extra);
  if (issue.level !== "error" && !issue.resolved) {   // 修改、補對照、配對要到原本的地方還原
    actions.push(el("button", {
      type: "button", class: "link", text: issue.dismissed ? "取消確認" : "確認無誤",
      onclick: () => act("dismiss", { keys: [issue.key], on: !issue.dismissed }),
    }));
  }
  return el("div", { class: `issue ${issue.dismissed ? "dismissed" : issue.level}` },
    el("span", { class: `dot ${issue.level}` }),
    el("div", { class: "body" }, el("div", { class: "message", text: issue.message }),
      issue.note ? el("div", { class: "resolution", text: `→ ${issue.note}` }) : null,
      el("div", { class: "issue-actions" }, el("span", { class: "meta", text: `${STAGE_TEXT[issue.stage] || issue.stage}${issue.dismissed ? `・${handledText(issue)}` : ""}` }), actions)));
}

function renderDrawer() {
  const r = state.result;
  /* 看原始資料時細節也留著，可以左右對照 */
  const row = r && (state.tab === "rows" || state.tab === "source") && r.output.rows.find((x) => x.rid === state.selected);
  $("drawer").hidden = !row;
  document.querySelector(".layout").classList.toggle("with-drawer", Boolean(row));
  if (!row) return;
  $("drawerTitle").textContent = row.sheet && state.result.inputs && Object.values(state.result.inputs).some((i) => (i.sheets || []).length > 1)
    ? `${row.sheet}・第 ${row.row ?? "?"} 列` : `第 ${row.row ?? "?"} 列`;
  const issues = row.issues.map((i) => r.issues[i]).filter((i) => i.level !== "skip");
  const fields = r.output.columns.map((c) => {
    /* 文字欄位用會自動長高的文字框，多行內容不會被截掉；Enter 儲存，Shift+Enter 換行 */
    const multiline = c.type === "text";
    const input = multiline
      ? el("textarea", { rows: 1, disabled: !c.editable, placeholder: row.raw[c.name] ? `原始：${row.raw[c.name]}` : "" })
      : el("input", { value: row.values[c.name] ?? "", disabled: !c.editable, placeholder: row.raw[c.name] ? `原始：${row.raw[c.name]}` : "" });
    if (multiline) {
      input.value = row.values[c.name] ?? "";
      const grow = () => { input.style.height = "auto"; input.style.height = `${Math.min(input.scrollHeight, 220)}px`; };
      input.addEventListener("input", grow);
      requestAnimationFrame(grow);
    }
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !(multiline && e.shiftKey)) { e.preventDefault(); input.blur(); }
      if (e.key === "Escape") { input.value = row.values[c.name] ?? ""; input.blur(); }
    });
    input.addEventListener("change", () => {
      if (String(input.value) !== String(row.values[c.name] ?? "")) act("edit", { rid: row.rid, column: c.name, value: input.value });
    });
    const flagged = cellIssues(row, c.name).some((i) => i.level === "review");
    const traceKey = `${row.rid}\u0000${c.name}`;
    const open = state.openTrace.has(traceKey);
    const hint = c.name in row.edited ? el("div", { class: "hint" }, `原值：${row.edited[c.name] ?? "（空白）"}　`,
      el("button", { type: "button", class: "link", text: "還原", onclick: () => act("edit", { rid: row.rid, column: c.name, revert: true }) })) : null;
      const why = el("button", {
        type: "button", class: `link why${open ? " open" : ""}`, text: open ? "收起" : "怎麼來的",
        onclick: () => { open ? state.openTrace.delete(traceKey) : state.openTrace.add(traceKey); renderDrawer(); },
      });
      /* 原始儲存格：點了在旁邊跳出小卡對照，不離開這一列 */
      const origin = cellPlace(row.origins && row.origins[c.name]);
      const cellLink = origin ? el("button", {
        type: "button", class: "link why cell-link", text: origin.cell, title: `看原始 Excel 的儲存格 ${origin.cell}（${origin.sheet}）`,
        onclick: (e) => openSource(origin, e.currentTarget, { label: c.name, value: row.values[c.name] }),
      }) : null;
    const story = open ? traceList(row, (t) => t.columns[c.name]) : null;
    return el("div", { class: `field${flagged ? " flag-review" : ""}` },
      el("div", { class: "field-label" }, el("label", { text: c.name, title: c.name }), el("span", { class: "field-tools" }, cellLink, why)), input, hint, story);
  });
  const rowKey = `${row.rid}\u0000*`;
  const rowStory = el("details", { class: "row-trace", open: state.openTrace.has(rowKey) },
    el("summary", { text: "這一列的處理過程" }), state.openTrace.has(rowKey) ? traceList(row, (t) => t.steps) : null);
  rowStory.addEventListener("toggle", () => {
    if (rowStory.open === state.openTrace.has(rowKey)) return;
    rowStory.open ? state.openTrace.add(rowKey) : state.openTrace.delete(rowKey);
    renderDrawer();
  });
  put($("drawerBody"),
    ...[["需要注意", issues.filter((i) => !i.dismissed)], ["處理紀錄", issues.filter((i) => i.dismissed)]].map(([title, list]) =>
      list.length ? el("section", {}, el("h4", { class: "section-title", text: title }), el("div", { class: "list" }, list.map((i) => issueLine(i)))) : null),
    el("section", {}, el("h4", { class: "section-title", text: "欄位" }), el("p", { class: "muted small-text", style: "margin:-4px 0 10px", text: "修改後按 Enter 儲存（Shift+Enter 換行），會保留原值。" }), fields),
    el("section", {}, rowStory),
    sourceSection(row));
    renderDrawerFoot(row);
    }

    /* 檢查流程：細節下方固定一列，看完這一列直接到下一列 */
    function neighbors(rid) {
      const list = visibleRows();
      const index = list.findIndex((x) => x.rid === rid);
      return { list, index, prev: index > 0 ? list[index - 1] : null, next: index >= 0 ? list[index + 1] || null : list[0] || null };
    }

    function selectRow(rid) {
      closePeek();
      state.selected = rid;
      renderTabs();
      requestAnimationFrame(() => document.querySelector("table.grid tr.selected")?.scrollIntoView({ block: "nearest" }));
    }

    async function confirmAndNext(row) {
      const { list, index } = neighbors(row.rid);
      const after = list[index + 1] || null;
      const keys = row.issues.map((i) => state.result.issues[i]).filter((i) => !i.dismissed && i.level === "review" && !i.resolved).map((i) => i.key);
      if (keys.length && !(await act("dismiss", { keys, on: true }))) return;
      /* 篩選「需檢查」時，確認過的列會離開清單，下一筆就是原本排在它後面的那一列 */
      const still = new Set(visibleRows().map((x) => x.rid));
      const next = (after && still.has(after.rid) && after) || visibleRows().find((x, i) => i >= Math.max(index, 0)) || null;
      selectRow(next ? next.rid : null);
      if (!next) toast(state.filter === "review" ? "需檢查的列都處理完了" : "已經是最後一列");
    }

    function renderDrawerFoot(row) {
      const { list, index, prev, next } = neighbors(row.rid);
      const open = row.issues.map((i) => state.result.issues[i]).filter((i) => !i.dismissed && i.level === "review" && !i.resolved);
      put($("drawerFoot"),
        el("div", { class: "foot-nav" },
          btn({ icon: "up", label: "上一筆（K）", disabled: !prev, onclick: () => selectRow(prev.rid) }),
          btn({ icon: "down", label: "下一筆（J）", disabled: !next, onclick: () => selectRow(next.rid) }),
          el("span", { class: "foot-count", text: index >= 0 ? `${FILTER_TEXT[state.filter]} ${index + 1} / ${list.length}` : `不在「${FILTER_TEXT[state.filter]}」裡` })),
        open.length
          ? el("button", { type: "button", class: "primary small", title: "確認這一列的警示都沒問題，然後看下一筆（Shift+Enter 以外的 Enter 在欄位裡是儲存）",
            onclick: () => confirmAndNext(row) }, icon("check"), el("span", { text: open.length > 1 ? `確認 ${open.length} 個警示，下一筆` : "確認無誤，下一筆" }))
          : el("button", { type: "button", class: "small", disabled: !next, onclick: () => next && selectRow(next.rid) },
            el("span", { text: "下一筆" }), kbd("J")));
    }

    /* 這一列在原始 Excel 的哪裡：主要的輸入表，加上配對帶進來的其他表。點了在旁邊跳出小卡 */
function sourceSection(row) {
  const places = [row.source, ...Object.values(row.links || {})].map(sourcePlace).filter(Boolean);
  return el("section", {}, el("h4", { class: "section-title", text: "原始 Excel" }),
    el("div", { class: "source-list" }, places.map((place) => el("div", { class: "source-item" },
      el("span", { class: "source-label", text: place.label }),
      el("button", { type: "button", class: "link", text: `${place.sheet}・第 ${place.row} 列`,
        onclick: (e) => openSource(place, e.currentTarget) })))),
    el("p", { class: "muted small-text", text: `列代號 ${row.rid}` }));
}

/* 執行紀錄：要看的時候才向程式要，同一次執行內記著不重複要 */
function traceList(row, pick) {
  const box = el("ol", { class: "trace" });
  /* 「　」開頭的是上一步的補充，併進同一點，編號才會連續 */
  const fill = (data) => {
    const items = [];
    for (const line of pick(data) || []) {
      if (line.startsWith("　") && items.length) items[items.length - 1].push(line.trim());
      else items.push([line.trim()]);
    }
    put(box, items.map(([head, ...rest]) => el("li", {}, head, rest.map((more) => el("div", { class: "sub", text: more })))));
  };
  const cached = state.traces[row.rid];
  if (cached) {
    fill(cached);
  } else {
    put(box, el("li", { class: "muted", text: "讀取中…" }));
    api(`/api/runs/${state.result.run_id}/trace?rid=${encodeURIComponent(row.rid)}`)
      .then((data) => { state.traces[row.rid] = data; fill(data); })
      .catch((error) => put(box, el("li", { class: "muted", text: error.message })));
  }
  return box;
}

/* ---------- 配對 ---------- */
function focusMatch(name, rid) {
  goTo({ tab: "match", matchName: name, matchFilter: "all", matchFocus: rid, matchSearch: "", pickerFor: null });
}

/* 先顯示比對用到的欄位，其他欄位收起來，避免一張卡片塞太多字 */
function pickColumns(values, preferred, all = false) {
  const keys = Object.keys(values);
  if (all) return keys;
  const shown = preferred.filter((k) => keys.includes(k));
  for (const k of keys) {
    if (shown.length >= Math.max(3, preferred.length)) break;
    if (!shown.includes(k) && values[k] !== null && values[k] !== "") shown.push(k);
  }
  return shown;
}

function valuesList(values, columns, compare) {
  return el("dl", { class: "kv" }, columns.flatMap((k) => {
    const v = values[k];
    const blank = v === null || v === undefined || v === "";
    let cls = blank ? "blank" : null;
    if (!blank && compare && k in compare && compare[k] !== null && compare[k] !== "") cls = String(v) === String(compare[k]) ? "same" : "diff";
    return [el("dt", { text: k, title: k }), el("dd", { class: cls, text: blank ? "空白" : v })];
  }));
}

/* 一列的辨識資訊：辨識欄位（例如發票號碼）加上 Excel 列號，讓人分得出是哪一筆 */
function rowTitle(record, titleColumns, rid = null) {
  const place = rid ? sourcePlace(rid) : null;
  const link = place ? btn({ icon: "sheet", variant: "quiet", label: `看原始資料：${place.sheet} 第 ${place.row} 列`,
    extra: "row-source", onclick: (e) => openSource(place, e.currentTarget) }) : null;
  const title = rowTitleText(record, titleColumns);
  if (link) title.append(link);
  return title;
}

function rowTitleText(record, titleColumns) {
  const title = titleColumns.map((k) => record.values[k]).filter((v) => v !== null && v !== "").join("・");
  return el("span", { class: "row-title" }, title ? el("strong", { text: title }) : null,
    el("span", { class: "muted", text: `${title ? "　" : ""}第 ${record.row ?? "?"} 列` }));
}

/* 候選之間值不一樣的欄位：一定要顯示，否則候選看起來會一模一樣 */
function differingColumns(records) {
  if (records.length < 2) return [];
  const keys = Object.keys(records[0].values);
  return keys.filter((k) => new Set(records.map((r) => String(r.values[k] ?? ""))).size > 1);
}

function oneLine(values, columns) {
  return columns.map((k) => values[k]).filter((v) => v !== null && v !== "").join("・");
}

function uniq(list) { return [...new Set(list)]; }

function renderMatch() {
  const r = state.result;
  const match = r.matches.find((m) => m.name === state.matchName) || r.matches[0];
  state.matchName = match.name;
  const todo = new Set(["ambiguous", "unmatched", "review"]);   // 已確認（confirmed）不算待處理
  const filters = { todo: (x) => x.open, all: () => true, manual: (x) => ["manual", "none", "confirmed"].includes(x.status) || x.acknowledged };
  const needle = state.matchSearch.toLowerCase();
  let rows = match.rows.filter(filters[state.matchFilter]);
  if (state.matchFocus) rows = rows.filter((x) => x.left === state.matchFocus);
  if (needle) {
    rows = rows.filter((x) => JSON.stringify(match.left_rows[x.left]?.values || {}).toLowerCase().includes(needle)
      || x.rights.some((rid) => JSON.stringify(match.right_rows[rid]?.values || {}).toLowerCase().includes(needle)));
  }
  const c = match.counts;
  put($("tabBody"),
    r.matches.length > 1 ? el("div", { class: "toolbar" }, chips(r.matches.map((m) => [m.name, m.label]), match.name,
      (id) => { Object.assign(state, { matchName: id, matchFocus: null, pickerFor: null }); renderTabs(); })) : null,
    el("div", { class: "toolbar" },
      chips([["todo", `需處理 ${c.todo}`], ["all", `全部 ${match.rows.length}`],
        ["manual", `已確認 ${match.rows.filter((x) => ["manual", "none", "confirmed"].includes(x.status) || x.acknowledged).length}`]],
        state.matchFilter, (id) => { Object.assign(state, { matchFilter: id, matchFocus: null }); renderTabs(); }),
      searchBox(state.matchSearch, "搜尋", (v) => { state.matchSearch = v; renderMatch(); }, "match"),
      state.matchFocus ? btn({ text: "顯示全部", onclick: () => { state.matchFocus = null; renderTabs(); } }) : null,
      el("span", { class: "spacer" }),
      toggle("顯示全部欄位", state.matchAll, (on) => { state.matchAll = on; state.matchOpen.clear(); renderMatch(); },
        "每張卡片也可以用卡片下方的連結各自展開")),
    el("p", { class: "match-meta muted" }, `拿每一列${match.left_label}找對應的${match.right_label}（${match.mode_label}）。依序嘗試：${match.strategies.join(" → ")}`,
      match.multi && match.pairs ? `，共 ${match.pairs} 組` : ""),
    rows.length ? el("div", { class: "match-list" }, rows.slice(0, 200).map((row) => matchCard(match, row)))
      : el("div", { class: "note", text: state.matchFilter === "todo" ? "所有配對都已處理。" : "沒有符合的配對。" }),
    rows.length > 200 ? el("p", { class: "muted", text: `只顯示前 200 筆，共 ${rows.length} 筆，請用搜尋縮小範圍。` }) : null,
    match.unused_right.length ? el("details", { class: "unused" },
      el("summary", { text: `沒用到的${match.right_label}（${match.unused_right.length}）` }),
      el("div", { class: "picker-list" }, match.unused_right.slice(0, 200).map((rid) => el("div", { class: "pick-row" },
        rowTitle(match.right_rows[rid], match.right_title),
        el("span", { class: "summary muted", text: oneLine(match.right_rows[rid].values, Object.keys(match.right_rows[rid].values)) })))))
      : null);
}

function matchCard(match, row) {
  const left = match.left_rows[row.left];
  let [label, tone] = MATCH_TEXT[row.status];
  if (row.acknowledged && ["review", "ambiguous", "unmatched"].includes(row.status)) {
    [label, tone] = [`${label}・已確認`, "manual"];   // 問題還在，但你已經確認過
  }
  const decide = (rights) => { state.pickerFor = null; return act("match", { match: match.name, left: row.left, rights }); };
  const reviewIssue = state.result.issues.find((i) => i.code === "match_review" && i.rid === row.left && i.ref === match.name);
  /* 每張卡片可以各自展開全部欄位；上方的「全部展開」一次展開所有卡片 */
  const expanded = state.matchAll || state.matchOpen.has(row.left);
  const leftColumns = pickColumns(left.values, match.show.left, expanded).filter((k) => !match.left_title.includes(k));
  const candidates = row.candidates.map((c) => match.right_rows[c.rid]).filter(Boolean);
  const sample = match.right_rows[row.rights[0]] || candidates[0] || Object.values(match.right_rows)[0];
  const baseRight = sample ? pickColumns(sample.values, match.show.right, expanded) : [];
  const rightColumns = uniq([...baseRight, ...differingColumns(candidates)]).filter((k) => !match.right_title.includes(k));
  const togglePicker = () => { state.pickerFor = state.pickerFor === row.left ? null : row.left; renderMatch(); };

  const actions = [];
  if (reviewIssue && row.status === "review") actions.push(btn({ text: "確認正確", icon: "check", variant: "primary", onclick: () => act("dismiss", { keys: [reviewIssue.key], on: true }) }));
  if (reviewIssue && row.status === "confirmed") actions.push(el("button", { type: "button", class: "small ghost", text: "取消確認", onclick: () => act("dismiss", { keys: [reviewIssue.key], on: false }) }));
  if (row.status === "manual" || row.status === "none") actions.push(el("button", { type: "button", class: "small ghost", text: "交回自動", onclick: () => decide(null) }));
  actions.push(el("button", { type: "button", class: "small ghost", text: match.multi ? "加入" : row.rights.length ? "改選" : "手動指定", onclick: togglePicker }));
  if (row.status !== "none") actions.push(el("button", { type: "button", class: "small ghost", text: "沒有配對", onclick: () => decide([]) }));

  const how = (row.status === "ambiguous" ? `依「${row.how}」找到 ${row.total || candidates.length} 筆可能的${match.right_label}，請選一筆`
    : row.status === "unmatched" ? `每一種方式都找不到對應的${match.right_label}`
      : row.status === "none" ? "已確認沒有對應" : row.status === "manual" ? "人工指定"
        : row.status === "confirmed" ? `依「${row.how}」配到，你已確認` : `依「${row.how}」配到`) + (row.why ? `。${row.why}` : "");

  let side;
  if (row.status === "ambiguous") {
    side = el("div", { class: "candidates" }, candidates.map((target, i) => {
      const cand = row.candidates[i];
      return el("div", { class: "candidate" },
        el("div", { class: "candidate-head" }, rowTitle(target, match.right_title, cand.rid),
          cand.score !== null && cand.score !== undefined ? el("span", { class: "muted", text: `相似度 ${Number(cand.score).toFixed(2)}` }) : null,
          el("span", { class: "spacer" }),
          btn({ text: "選這筆", icon: "check", variant: "default", onclick: () => decide(match.multi ? [...row.rights, cand.rid] : [cand.rid]) })),
        valuesList(target.values, rightColumns, left.values));
    }));
  } else if (row.rights.length === 1 && !match.multi) {
    const target = match.right_rows[row.rights[0]];
    side = el("div", {}, el("div", { class: "side-title" }, rowTitle(target, match.right_title, row.rights[0])), valuesList(target.values, rightColumns, left.values));
  } else if (row.rights.length) {
    side = el("div", { class: "picker-list" }, row.rights.map((rid) => {
      const target = match.right_rows[rid];
      return el("div", { class: "pick-row" },
        rowTitle(target, match.right_title),
        el("span", { class: "summary muted", title: oneLine(target.values, Object.keys(target.values)), text: oneLine(target.values, rightColumns) }),
        el("button", { type: "button", class: "link danger", text: "移除", onclick: () => decide(row.rights.filter((x) => x !== rid)) }));
    }));
  } else {
    side = el("p", { class: "muted", text: row.status === "none" ? "已確認沒有對應的資料" : "沒有找到對應的資料" });
  }
  return el("article", { class: "match-card" },
    el("header", {},
      el("span", { class: `badge ${tone}`, text: label }),
      el("span", { class: "how", text: how }),
      el("span", { class: "spacer" }), actions),
    el("div", { class: "match-body" },
      el("div", { class: "side" }, el("h4", { text: match.left_label }), el("div", { class: "side-title" }, rowTitle(left, match.left_title, row.left)),
        valuesList(left.values, leftColumns)),
      el("div", { class: "side" }, el("h4", { text: match.right_label + (match.multi && row.rights.length ? `・${row.rights.length} 筆` : "") }), side,
        state.pickerFor === row.left ? picker(match, row, rightColumns, decide) : null)),
    expandToggle(match, row, left, sample, leftColumns, rightColumns, expanded));
}

function expandToggle(match, row, left, sample, leftColumns, rightColumns, expanded) {
  const total = Object.keys(left.values).filter((k) => !match.left_title.includes(k)).length
    + (sample ? Object.keys(sample.values).filter((k) => !match.right_title.includes(k)).length : 0);
  const hidden = total - leftColumns.length - rightColumns.length;
  if (state.matchAll || (!expanded && hidden <= 0)) return null;
  return el("footer", { class: "match-foot" }, el("button", {
    type: "button", class: "quiet small", text: expanded ? "收起欄位" : `顯示全部欄位（還有 ${hidden} 欄）`,
    onclick: () => { state.matchOpen[expanded ? "delete" : "add"](row.left); renderMatch(); },
  }));
}

function picker(match, row, columns, decide) {
  const taken = new Set(row.rights);
  const unused = new Set(match.unused_right);
  const owner = {};   // 右表列 → 已經配給哪一列左表
  for (const other of match.rows) {
    if (other.left === row.left) continue;
    for (const rid of other.rights) owner[rid] = match.left_rows[other.left];
  }
  const list = el("div", { class: "picker-list" });
  const draw = (text) => {
    const needle = text.trim().toLowerCase();
    const rids = Object.keys(match.right_rows)
      .filter((rid) => !taken.has(rid) && (!needle || JSON.stringify(match.right_rows[rid].values).toLowerCase().includes(needle)))
      .sort((a, b) => Number(unused.has(b)) - Number(unused.has(a)));
    put(list, rids.length ? rids.slice(0, 50).map((rid) => el("div", { class: "pick-row" },
      rowTitle(match.right_rows[rid], match.right_title),
      el("span", { class: "summary muted", title: oneLine(match.right_rows[rid].values, Object.keys(match.right_rows[rid].values)), text: oneLine(match.right_rows[rid].values, columns) }),
      unused.has(rid) ? el("span", { class: "badge", text: "未使用" }) : null,
      owner[rid] ? el("span", { class: "badge review", title: "一對一時改選這筆，另一列就要重新指定",
        text: `已配給${oneLine(owner[rid].values, match.left_title) || ""} 第 ${owner[rid].row ?? "?"} 列` }) : null,
      el("button", { type: "button", class: "small", text: match.multi ? "加入" : "選這筆", onclick: () => decide(match.multi ? [...row.rights, rid] : [rid]) })))
      : el("p", { class: "muted", text: "找不到符合的資料" }));
  };
  const input = el("input", { class: "search", type: "search", placeholder: `在${match.right_label}裡搜尋` });
  input.addEventListener("input", () => draw(input.value));
  draw("");
  return el("div", { class: "picker" }, input, list);
}

/* ---------- 對照表 ---------- */
function targetControl(allowed) {
  if (!allowed) return { node: el("input", { placeholder: "輸入對應值" }), read: (n) => ({ target: n.value.trim(), new_value: false }) };
  const select = el("select", {}, el("option", { value: "", text: "選擇對應值" }), allowed.map((v) => el("option", { value: v, text: v })),
    el("option", { value: "__new", text: "＋ 新增對應值…" }));
  const input = el("input", { placeholder: "新的對應值", hidden: true });
  select.addEventListener("change", () => { input.hidden = select.value !== "__new"; if (!input.hidden) input.focus(); });
  const node = el("div", { class: "target" }, select, input);
  return { node, read: () => (select.value === "__new" ? { target: input.value.trim(), new_value: true } : { target: select.value, new_value: false }) };
}

function renderMapping() {
  const r = state.result;
  const pending = r.unmapped;
  const sections = [];
  sections.push(el("section", { class: "block" },
    el("h3", { text: "待補對照" }),
    el("p", { class: "muted small-text", text: "這些寫法不在對照表裡。補上的對照存在這份 recipe，之後處理其他檔案也會套用。清單裡沒有合適的值，可以選「新增對應值」。" }),
    pending.length ? el("div", { class: "list" }, pending.map((entry) => {
      const control = targetControl(entry.allowed);
      const save = () => {
        const { target, new_value } = control.read(control.node);
        if (!target) { toast("請選擇或輸入對應值", true); return; }
        act("mapping", { mapping: entry.mapping, raw: entry.raw, target, new_value });
      };
      return el("div", { class: "map-row" },
        el("div", { class: "map-source" }, el("div", { class: "raw-value", text: entry.raw }),
          el("div", { class: "muted", text: `${entry.mapping}・${entry.count} 次・${entry.places.join("、")}` })),
        control.node,
        el("button", { type: "button", class: "primary small", text: "儲存", onclick: save }));
    })) : el("div", { class: "note", text: "所有值都有對照。" })));
  for (const mapping of r.mappings) {
    if (!mapping.added.length) continue;
    sections.push(el("section", { class: "block" },
      el("h3", { text: `已補上的對照・${mapping.name}` }),
      el("div", { class: "picker-list" }, mapping.added.map((entry) => el("div", { class: "pick-row" },
        el("span", { class: "summary" }, entry.raw, el("span", { class: "muted", text: "  →  " }), entry.target,
          mapping.custom_values.includes(entry.target) ? el("span", { class: "badge manual", style: "margin-left:8px", text: "自訂值" }) : null),
        el("button", { type: "button", class: "link danger", text: "移除", onclick: () => act("mapping", { mapping: mapping.name, raw: entry.raw, target: null }) }))))));
  }
  put($("tabBody"), sections);
}

/* ---------- 排除 ---------- */
function renderExcluded() {
  const rows = state.result.excluded;
  const names = [...new Set(rows.flatMap((r) => Object.keys(r.values)))];
  put($("tabBody"), el("div", { class: "table-wrap" }, el("table", { class: `grid${prefs.get("dense", false) ? " dense" : ""}` },
    el("thead", {}, el("tr", {}, ["輸入表", "列", "原因", ...names].map((n) => el("th", { text: n })))),
    el("tbody", {}, rows.map((r) => el("tr", {}, el("td", { text: r.input }),
      el("td", { class: "rowno" }, btn({ text: String(r.row), icon: "sheet", variant: "quiet", title: "看原始資料的這一列",
        onclick: (e) => { const place = sourcePlace(r.rid); if (place) openSource(place, e.currentTarget); } })),
      el("td", { text: r.label }),
      names.map((n) => el("td", { text: r.values[n] ?? "", title: r.values[n] ?? null }))))))));
}

/* ---------- 原始資料 ---------- */
/* 回到上傳的 Excel 核對：照 Excel 的欄名（A、B、C）與列號顯示，標出表頭與要看的那一列、那一格。
   找不到原因時可以回來看原本寫的是什麼。也可以 pop out 到另一個螢幕，和結果左右對照。 */
function colLetter(index) {
  let n = index + 1, text = "";
  while (n > 0) { const m = (n - 1) % 26; text = String.fromCharCode(65 + m) + text; n = Math.floor((n - 1) / 26); }
  return text;
}

/* 列代號（表:列 或 表:工作表:列）→ 原始 Excel 的位置 */
function sourcePlace(rid) {
  if (!rid || !state.result) return null;
  const parts = String(rid).split("|")[0].split(":");
  const input = state.result.inputs[parts[0]];
  if (!input) return null;
  const [sheet, row] = parts.length >= 3 ? [parts.slice(1, -1).join(":"), Number(parts[parts.length - 1])] : [input.sheets[0], Number(parts[1])];
  if (!sheet || !row) return null;
  return { table: parts[0], label: input.label || parts[0], sheet, row, col: null, cell: null };
}

/* 輸出欄位的來源 [列代號, 輸入欄位] → 原始 Excel 的那一格 */
function cellPlace(origin) {
  const place = origin ? sourcePlace(origin[0]) : null;
  const col = place && state.result.inputs[place.table].positions?.[place.sheet]?.columns?.[origin[1]];
  if (col === undefined || col === null) return null;
  return { ...place, col, cell: `${colLetter(col)}${place.row}` };
}

/* 看原始資料：預設在按鈕旁邊跳出小卡（表頭、那一列與前後兩列），不離開正在檢查的地方，才能對照。
   要看整張工作表再按小卡上的「完整工作表」。沒有按鈕可以對齊時（例如鍵盤操作）直接打開完整工作表。 */
function openSource(place, anchor = null, compare = null) {
  if (!anchor) { showSheet(place); return; }
  peek(place, anchor, compare);
}

function showSheet(place) {
  closePeek();
  goTo({ tab: "source", source: { sheet: place.sheet, row: place.row, col: place.col, start: null } });
}

/* 一次讀 200 列，對齊成固定的區段，小卡與完整工作表共用 */
async function sheetBlock(runId, sheet, row) {
  const start = Math.floor((Math.max(row, 1) - 1) / 200) * 200 + 1;
  const key = `${runId}\u0000${sheet}\u0000${start}`;
  if (!sheetCache.has(key)) {
    sheetCache.set(key, api(`/api/runs/${encodeURIComponent(runId)}/sheet?name=${encodeURIComponent(sheet)}&start=${start}`));
  }
  try { return await sheetCache.get(key); } catch (error) { sheetCache.delete(key); throw error; }
}

async function sheetRows(runId, sheet, numbers) {
  const out = {};
  let width = 0;
  for (const n of numbers) {
    const page = await sheetBlock(runId, sheet, n);
    width = Math.max(width, page.width);
    if (n <= page.total) out[n] = page.rows[n - page.start] || [];
  }
  return { rows: out, width };
}

let peekAnchor = null;

function closePeek() {
  const card = document.getElementById("peek");
  if (card) card.remove();
  peekAnchor = null;
}

async function peek(place, anchor, compare) {
  const r = state.result;
  if (peekAnchor === anchor) { closePeek(); return; }   // 再按一次收起
  closePeek();
  peekAnchor = anchor;
  const card = el("div", { id: "peek", class: "peek", role: "dialog", "aria-label": "原始資料" });
  document.body.append(card);
  put(card, el("div", { class: "peek-body muted", text: "讀取原始資料…" }));
  placePeek(card, anchor);
  const header = r.inputs[place.table]?.positions?.[place.sheet]?.header_row || null;
  const around = [place.row - 2, place.row - 1, place.row, place.row + 1, place.row + 2].filter((n) => n >= 1);
  let data;
  try {
    data = await sheetRows(r.run_id, place.sheet, [...new Set([...(header ? [header] : []), ...around])].sort((a, b) => a - b));
  } catch (error) { put(card, el("div", { class: "peek-body", text: error.message })); return; }
  if (peekAnchor !== anchor) return;
  const numbers = Object.keys(data.rows).map(Number).sort((a, b) => a - b);
  const body = [];
  numbers.forEach((n, i) => {
    if (i && n - numbers[i - 1] > 1) body.push(el("tr", { class: "gap" }, el("th", { class: "rowno", text: "⋯" }), el("td", { colspan: data.width })));
    const cells = data.rows[n];
    body.push(el("tr", { class: [n === header ? "src-header" : "", n === place.row ? "src-target" : ""].filter(Boolean).join(" ") || null },
      el("th", { class: "rowno", text: n }),
      Array.from({ length: data.width }, (_, c) => el("td", { class: n === place.row && c === place.col ? "src-cell" : null, title: cells[c] || null },
        el("div", { class: "cell-text", text: cells[c] ?? "" })))));
  });
  const table = el("table", { class: "grid source-grid" },
    el("thead", {}, el("tr", {}, el("th", { class: "corner" }),
      Array.from({ length: data.width }, (_, c) => el("th", { class: c === place.col ? "target-col" : null, text: colLetter(c) })))),
    el("tbody", {}, body));
  const original = place.col !== null && place.col !== undefined ? data.rows[place.row]?.[place.col] : null;
  put(card,
    el("div", { class: "peek-head" },
      el("div", { class: "peek-title" }, el("strong", { text: place.label }),
        el("span", { class: "muted", text: `${place.sheet}・第 ${place.row} 列${place.cell ? `・${place.cell}` : ""}` })),
      btn({ text: "完整工作表", icon: "sheet", onclick: () => showSheet(place) }),
      btn({ icon: "x", label: "關閉", onclick: closePeek })),
    compare && place.cell ? el("div", { class: "peek-compare" },
      el("span", { class: "muted", text: "原始" }), el("span", { class: "peek-raw", text: original === null || original === undefined || original === "" ? "（空白）" : original }),
      icon("arrow"),
      el("span", { class: "muted", text: `整理後的${compare.label}` }),
      el("span", { class: "peek-value", text: compare.value === null || compare.value === undefined || compare.value === "" ? "（空白）" : String(compare.value) })) : null,
    el("div", { class: "peek-body source-wrap" }, table),
    header ? el("p", { class: "peek-note muted", text: `第 ${header} 列是表頭` }) : null);
  placePeek(card, anchor);
  const focus = card.querySelector(".src-cell") || card.querySelector(".src-target td");
  if (focus) scrollToCell(focus, false);
}

/* 小卡放在按鈕旁邊：下方放得下就放下方，否則放上方；左右不超出視窗 */
function placePeek(card, anchor) {
  const rect = anchor.getBoundingClientRect();
  const width = Math.min(720, window.innerWidth - 24);
  card.style.width = `${width}px`;
  const height = card.offsetHeight;
  const below = rect.bottom + 8 + height <= window.innerHeight - 12;
  card.style.top = `${below ? rect.bottom + 8 : Math.max(12, rect.top - 8 - height)}px`;
  card.style.left = `${Math.max(12, Math.min(rect.right - width, window.innerWidth - width - 12))}px`;
}

document.addEventListener("mousedown", (e) => {
  const card = document.getElementById("peek");
  if (card && !card.contains(e.target) && !(peekAnchor && peekAnchor.contains(e.target))) closePeek();
});
window.addEventListener("resize", closePeek);

const sheetCache = new Map();

async function renderSource() {
  const r = state.result;
  const firstInput = Object.values(r.inputs)[0];
  const src = state.source = { sheet: firstInput?.sheets?.[0] || null, row: null, col: null, start: null, ...(state.source || {}) };
  const start = src.start || Math.max(1, (src.row || 1) - 20);
  const key = `${r.run_id}\u0000${src.sheet}\u0000${start}`;
  let page = sheetCache.get(key);
  if (page && typeof page.then === "function") page = await page.catch(() => null);   // 小卡讀過的段落
  if (!page) {
    put($("tabBody"), el("div", { class: "note", text: "讀取原始資料…" }));
    try {
      page = await api(`/api/runs/${encodeURIComponent(r.run_id)}/sheet?name=${encodeURIComponent(src.sheet || "")}&start=${start}`);
    } catch (error) { put($("tabBody"), el("div", { class: "note", text: error.message })); return; }
    sheetCache.set(key, page);
    if (state.tab !== "source" || state.result !== r) return;   // 讀取時已經換到別的分頁
  }
  src.sheet = page.name;
  const headers = Object.values(r.inputs).flatMap((input) => {
    const pos = input.positions?.[page.name];
    return pos ? [{ row: pos.header_row, label: input.label }] : [];
  });
  const usedBy = (name) => Object.values(r.inputs).filter((input) => (input.sheets || []).includes(name)).map((input) => input.label);
  const end = page.start + page.rows.length - 1;
  const go = (changes) => { Object.assign(src, changes); renderSource(); };
  const jump = el("input", { class: "search jump", type: "number", min: 1, max: page.total, placeholder: "跳到第幾列" });
  jump.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && Number(jump.value) >= 1) go({ row: Number(jump.value), col: null, start: null });
  });
  const wrap = prefs.get("wrap", false);
  const table = el("table", { class: `grid source-grid${wrap ? " wrap" : ""}` },
    el("thead", {}, el("tr", {}, el("th", { class: "corner" }), Array.from({ length: page.width }, (_, i) => el("th", {
      class: i === src.col ? "target-col" : null, text: colLetter(i) })))),
    el("tbody", {}, page.rows.map((cells, offset) => {
      const number = page.start + offset;
      const header = headers.find((h) => h.row === number);
      const target = number === src.row;
      return el("tr", { class: [header ? "src-header" : "", target ? "src-target" : ""].filter(Boolean).join(" ") || null, dataset: { row: number } },
        el("th", { class: "rowno", title: header ? `${header.label}的表頭` : null, text: number }),
        cells.map((value, i) => el("td", { class: target && i === src.col ? "src-cell" : null, title: value || null },
          el("div", { class: "cell-text", text: value }))));
    })));
  put($("tabBody"),
    el("div", { class: "toolbar" },
      chips(page.names.map((name) => [name, usedBy(name).length ? `${name}・${usedBy(name).join("、")}` : name]), page.name,
        (name) => go({ sheet: name, row: null, col: null, start: 1 })),
      el("span", { class: "spacer" }),
      jump,
      el("span", { class: "muted", text: page.total ? `第 ${page.start}–${end} 列，共 ${page.total} 列` : "空白的工作表" }),
      btn({ icon: "left", label: "上一段", disabled: page.start <= 1, onclick: () => go({ start: Math.max(1, page.start - page.page) }) }),
      btn({ icon: "right", label: "下一段", disabled: end >= page.total, onclick: () => go({ start: page.start + page.page }) })),
    headers.length || src.row ? el("p", { class: "muted small-text source-legend" },
      headers.map((h) => `第 ${h.row} 列是「${h.label}」的表頭`).join("，"),
      src.row ? `${headers.length ? "；" : ""}標示的是第 ${src.row} 列${src.col !== null && src.col !== undefined ? `的 ${colLetter(src.col)}${src.row}` : ""}` : "") : null,
    page.rows.length ? el("div", { class: "table-wrap source-wrap" }, table) : el("div", { class: "note", text: "這張工作表沒有資料。" }));
  const focus = $("tabBody").querySelector(".src-cell") || $("tabBody").querySelector(".src-target");
  if (focus) requestAnimationFrame(() => scrollToCell(focus));
}

/* 捲到要看的那一列（置中）與那一格。左右捲動時對齊到欄的開頭，左邊的欄位不會被切一半 */
function scrollToCell(cell, page = true) {
  const wrap = cell.closest(".source-wrap");
  if (!wrap) return;
  /* 用畫面上的實際位置計算：表頭與列號固定在邊上（sticky），offsetLeft 不可靠 */
  const box = wrap.getBoundingClientRect();
  const at = (node) => node.getBoundingClientRect().left - box.left + wrap.scrollLeft;   // 在表格裡的水平位置
  const rect = cell.getBoundingClientRect();
  wrap.scrollTop = Math.max(0, rect.top - box.top + wrap.scrollTop - wrap.clientHeight / 2 + rect.height / 2);
  const heads = [...wrap.querySelectorAll("thead th")];
  const rowno = heads[0].getBoundingClientRect().width;
  const right = at(cell) + rect.width;
  let left = 0;
  if (cell.tagName === "TD" && right > wrap.clientWidth) {
    const fit = heads.slice(1).find((th) => right - (at(th) - rowno) <= wrap.clientWidth);
    left = at(fit || cell) - rowno;
  }
  wrap.scrollLeft = left;
  if (page) wrap.scrollIntoView({ block: "nearest" });
}

/* ---------- 所有警示 ---------- */
function renderIssues() {
  const filters = {
    review: (i) => !i.dismissed && (i.level === "review" || i.level === "error"), notice: (i) => !i.dismissed && i.level === "notice",
    dismissed: (i) => i.dismissed, all: () => true,
  };
  const focus = state.issueFocus;
  const issues = activeIssues().filter(filters[state.issueFilter])
    .filter((i) => !focus || ((!focus.code || i.code === focus.code) && (!focus.stage || i.stage === focus.stage)));
  const rowOf = new Map();
  state.result.output.rows.forEach((row) => row.issues.forEach((i) => rowOf.set(i, row)));
  const selectable = issues.filter((i) => i.level !== "error" && !i.resolved);
  put($("tabBody"),
    el("div", { class: "toolbar" },
      chips([["review", "需檢查"], ["notice", "提示"], ["dismissed", "已處理"], ["all", "全部"]], state.issueFilter,
        (id) => { state.issueFilter = id; state.checked.clear(); renderTabs(); }),
      focus ? el("span", { class: "badge manual" }, `只看：${focus.label}`,
        btn({ icon: "x", variant: "quiet", label: "顯示全部", extra: "chip-close", onclick: () => { state.issueFocus = null; renderTabs(); } })) : null,
      el("span", { class: "spacer" }),
      selectable.length ? btn({ text: "全選", onclick: () => { selectable.forEach((i) => state.checked.add(i.key)); renderTabs(); } }) : null,
      state.checked.size ? el("button", {
        type: "button", class: "small primary", text: `${state.issueFilter === "dismissed" ? "取消確認" : "確認無誤"}（${state.checked.size}）`,
        onclick: async () => { const keys = [...state.checked]; state.checked.clear(); await act("dismiss", { keys, on: state.issueFilter !== "dismissed" }); },
      }) : null),
    issues.length ? el("div", { class: "issue-list" }, issues.map((issue) => {
      const row = rowOf.get(issue.id);
      const box = el("input", { type: "checkbox", checked: state.checked.has(issue.key), disabled: issue.level === "error" || Boolean(issue.resolved) });
      box.addEventListener("change", () => { box.checked ? state.checked.add(issue.key) : state.checked.delete(issue.key); renderTabs(); });
      return el("div", { class: "issue-row" }, box, issueLine(issue, row ? el("button", {
        type: "button", class: "link", text: `第 ${row.row ?? "?"} 列`,
        onclick: () => goTo({ tab: "rows", filter: "all", selected: row.rid }),
      }) : null));
    })) : el("div", { class: "note", text: "沒有警示。" }));
}

/* ---------- 與本機程式的連線 ---------- */
/* 頁面全部關閉後，本機程式會自動結束，不會留在背景。 */
const clientId = window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`.replace(/\./g, "");
let heartbeatFailures = 0;
async function heartbeat() {
  try {
    const response = await fetch(`/api/heartbeat?client=${encodeURIComponent(clientId)}`, { method: "POST" });
    if (!response.ok) throw new Error();
    heartbeatFailures = 0;
  } catch (_error) {
    heartbeatFailures += 1;
    if (heartbeatFailures === 2) toast("工具已經關閉。請重新執行 run.bat，再重新整理這個頁面。", true);
  }
}
/* 主要靠保持連線判斷：瀏覽器整個關掉時連線會斷，工具幾秒內就會發現並結束。heartbeat 是備援。 */
let liveSource = null;
function openLive() {
  if (!window.EventSource || liveSource) return;
  liveSource = new EventSource(`/api/live?client=${encodeURIComponent(clientId)}`);
}
function watchConnection() {
  openLive();
  heartbeat();
  setInterval(heartbeat, 15000);
  window.addEventListener("pagehide", () => {
    liveSource?.close();
    liveSource = null;
    navigator.sendBeacon(`/api/bye?client=${encodeURIComponent(clientId)}`);
  });
  window.addEventListener("pageshow", (event) => { if (event.persisted) { openLive(); heartbeat(); } });
}

/* 鍵盤：J／K 上一筆下一筆（打字時不作用），Esc 先關小卡再關細節 */
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && document.getElementById("peek")) { closePeek(); e.preventDefault(); return; }
  if (e.metaKey || e.ctrlKey || e.altKey || $("dialog").open || isTyping() || e.target.closest?.("input, textarea, select")) return;
  if (!state.result || state.tab !== "rows") return;
  const key = e.key.toLowerCase();
  if (key !== "j" && key !== "k") return;
  const { list, prev, next } = neighbors(state.selected);
  const target = key === "j" ? (state.selected ? next : list[0]) : prev;
  if (target) { e.preventDefault(); selectRow(target.rid); }
});

function bind() {
  $("newRecipe").addEventListener("click", () => editRecipe());
  $("workbookInput").addEventListener("change", (e) => { if (e.target.files[0]) uploadWorkbook(e.target.files[0]); e.target.value = ""; });
  const zone = $("dropZone");
  zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("over"));
  zone.addEventListener("drop", (e) => { e.preventDefault(); zone.classList.remove("over"); if (e.dataTransfer.files[0]) uploadWorkbook(e.dataTransfer.files[0]); });
  $("runButton").addEventListener("click", runNow);
  $("drawerClose").addEventListener("click", () => { closePeek(); state.selected = null; renderTabs(); });
  $("dialog").addEventListener("click", (e) => { if (e.target === $("dialog")) closeDialog(); });
}

/* 頁面上固定的按鈕：依 data-icon 放進圖示（文字包成 span，圖示和文字的間距才一致） */
function decorateButtons() {
  for (const node of document.querySelectorAll("[data-icon]")) {
    const text = node.textContent.trim();
    node.replaceChildren(icon(node.dataset.icon), ...(text ? [el("span", { text })] : []));
  }
}

async function main() {
  decorateButtons();
  watchConnection();
  bind();
  setupPanes();
  if (isPopout) {
    const status = await api("/api/status").catch(() => ({}));
    $("version").textContent = status.version ? `v${status.version}` : "";
    await startPopout();
    return;
  }
  try {
    const status = await api("/api/status");
    $("version").textContent = status.version ? `v${status.version}` : "";
    await loadRecipes();
    await loadSamples();
  } catch (error) {
    toast(error.message, true);
  }
}
main();
