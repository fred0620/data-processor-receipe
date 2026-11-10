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

function toast(message, bad = false) {
  const node = $("toast");
  node.textContent = message;
  node.classList.toggle("bad", bad);
  node.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { node.hidden = true; }, 5000);
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
function openDialog(title, body, actions) {
  $("dialogTitle").textContent = title;
  $("dialogBody").replaceChildren(...[body].flat());
  $("dialogActions").replaceChildren(...actions);
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
    el("button", { type: "button", class: "ghost", text: "複製給 AI", onclick: () => copyText(problemsText(problems)) }),
    el("button", { type: "button", class: "primary", text: "關閉", onclick: closeDialog }),
  ]);
}

/* ---------- 狀態 ---------- */
const state = {
  recipes: [], recipeId: null, workbook: null, result: null,
  tab: "rows", filter: "review", search: "", selected: null, stageOpen: null,
  matchName: null, matchFilter: "todo", matchSearch: "", pickerFor: null, matchFocus: null, matchAll: false,
  issueFilter: "review", checked: new Set(),
};
const LEVEL_TEXT = { review: "需檢查", notice: "提示", error: "無法執行" };
const STAGE_TEXT = { load: "Load", gate: "Gate", normalize: "Normalize", match: "Match", transform: "Transform", validate: "Validate", mapping: "Mapping", export: "Export" };
const MATCH_TEXT = { auto: ["已配對", "ok"], review: ["待確認", "review"], manual: ["人工指定", "manual"], none: ["確認沒有", "manual"], ambiguous: ["待選擇", "review"], unmatched: ["找不到", "missing"] };

/* 畫面偏好（顯示哪些欄位、緊湊或寬鬆）只存在這台電腦的瀏覽器，存不了也不影響使用 */
const prefs = {
  get(key, fallback) {
    try { const value = JSON.parse(window.localStorage.getItem(`dp:${key}`)); return value ?? fallback; } catch (_e) { return fallback; }
  },
  set(key, value) {
    try { window.localStorage.setItem(`dp:${key}`, JSON.stringify(value)); } catch (_e) { /* 無痕或停用儲存時略過 */ }
  },
};

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

async function viewRecipe(recipe) {
  try {
    const data = await api(`/api/recipes/${encodeURIComponent(recipe.id)}`);
    const area = el("textarea", { readonly: true });
    area.value = data.text;
    openDialog(recipe.name, area, [
      el("button", { type: "button", class: "ghost", text: "複製", onclick: () => copyText(data.text) }),
      el("button", { type: "button", class: "ghost", text: "修改後另存", onclick: () => editRecipe(data.text) }),
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
  const problems = el("div");
  file.addEventListener("change", async () => { if (file.files[0]) area.value = await file.files[0].text(); });
  const save = async () => {
    try {
      const data = await post("/api/recipes", { text: area.value });
      closeDialog();
      toast(`已儲存「${data.name}」`);
      await loadRecipes(data.id);
    } catch (error) {
      if (!error.problems.length) { toast(error.message, true); return; }
      problems.replaceChildren(
        el("ul", { class: "problems" }, error.problems.map((p) => el("li", { text: p }))),
        el("button", { type: "button", class: "link", text: "複製問題給 AI", onclick: () => copyText(problemsText(error.problems)) }));
    }
  };
  openDialog("新增或更新 recipe", [
    el("p", { class: "muted" }, "先把規格複製給 AI，連同你的欄位與處理規則請它寫 recipe，再貼回這裡。存檔前會完整檢查；id 相同時會覆蓋舊的 recipe。 ",
      el("button", { type: "button", class: "link", text: "複製規格給 AI", onclick: copySpec })),
    area, problems,
  ], [
    el("button", { type: "button", class: "ghost", text: "選擇檔案", onclick: () => file.click() }), file,
    el("button", { type: "button", class: "ghost", text: "取消", onclick: closeDialog }),
    el("button", { type: "button", class: "primary", text: "檢查並儲存", onclick: save }),
  ]);
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

function setResult(result, fresh = false) {
  state.result = result;
  if (fresh) {
    state.tab = result.status === "error" ? "issues" : "rows";
    state.filter = result.counts.review ? "review" : "all";
    state.issueFilter = result.status === "error" ? "all" : "review";
    state.matchName = result.matches[0]?.name || null;
    state.stageOpen = result.status === "error" ? result.stages.find((s) => s.status === "error")?.id : null;
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
    { ok: "全部正常", review: `${result.counts.review} 個地方需檢查`, error: "無法執行" }[result.status]);
  $("exportButton").href = `/api/runs/${result.run_id}/export`;
  $("exportButton").toggleAttribute("hidden", result.status === "error");
  renderPipeline();
  renderTabs();
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
      el("ul", {}, open.lines.length ? open.lines.map((line) => el("li", { class: line.startsWith("　") ? "sub" : null, text: line.trim() }))
        : el("li", { class: "muted", text: "沒有細節" })));
  }
}

function activeIssues() { return state.result.issues.filter((i) => i.level !== "skip"); }

function renderTabs() {
  const r = state.result;
  const pendingMaps = r.unmapped.filter((u) => u.missing === "ask").length;
  const todo = r.matches.reduce((n, m) => n + m.counts.ambiguous + m.counts.unmatched + m.counts.review, 0);
  const open = activeIssues().filter((i) => !i.dismissed && i.level !== "notice").length;
  const tabs = [
    ["rows", "結果", r.output.rows.filter((x) => x.status === "review").length],
    r.matches.length ? ["match", "配對", todo] : null,
    r.mappings.length ? ["mapping", "對照表", pendingMaps] : null,
    r.excluded.length ? ["excluded", "排除", r.excluded.length, true] : null,
    ["issues", "所有警示", open],
  ].filter(Boolean);
  if (!tabs.some((t) => t[0] === state.tab)) state.tab = "rows";
  put($("tabs"), tabs.map(([id, label, n, plain]) => el("button", {
    type: "button", class: `tab${state.tab === id ? " active" : ""}`, onclick: () => { state.tab = id; renderTabs(); },
  }, label, n ? el("span", { class: `count${plain ? "" : " review"}`, text: n }) : null)));
  ({ rows: renderRows, match: renderMatch, mapping: renderMapping, excluded: renderExcluded, issues: renderIssues })[state.tab]();
  renderDrawer();
}

function chips(options, current, onPick) {
  return el("div", { class: "chips" }, options.map(([id, label]) => el("button", {
    type: "button", class: `chip${current === id ? " active" : ""}`, text: label, onclick: () => onPick(id),
  })));
}

function searchBox(value, placeholder, onInput) {
  const input = el("input", { class: "search", type: "search", placeholder });
  input.value = value;
  let timer;
  input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => onInput(input.value), 200); });
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
  const menu = el("details", { class: "menu" }, el("summary", { class: "button ghost small", text: `欄位${hidden.size ? `（隱藏 ${hidden.size}）` : ""}` }),
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

function renderRows(keepMenu = false) {
  const r = state.result;
  if (r.status === "error") { renderIssues(); return; }
  const columns = visibleColumns();
  const dense = prefs.get("dense", false);
  const filters = { all: () => true, review: (x) => x.status === "review", edited: (x) => Object.keys(x.edited).length };
  const rows = r.output.rows.filter(filters[state.filter]).filter((x) => rowMatches(x, state.search));
  const menuWasOpen = keepMenu && document.querySelector(".menu")?.open;
  const table = el("table", { class: `grid${dense ? " dense" : ""}` },
    el("thead", {}, el("tr", {}, el("th", { class: "status-col" }), el("th", { text: "列" }), columns.map((c) => el("th", { text: c.name, title: c.name })))),
    el("tbody", {}, rows.slice(0, 2000).map((row) => el("tr", {
      class: state.selected === row.rid ? "selected" : null,
      onclick: () => { state.selected = row.rid; renderTabs(); },
    },
    el("td", { class: "status-col" }, el("span", { class: `dot ${row.status}` })),
    el("td", { class: "rowno", text: row.row ?? "", title: row.sheet ? `${row.sheet}・第 ${row.row} 列` : null }),
    columns.map((c) => {
      const flags = cellIssues(row, c.name);
      const value = row.values[c.name];
      const raw = row.raw[c.name];
      const classes = [c.type === "number" || c.type === "integer" ? "num" : "",
        flags.some((i) => i.level === "review") ? "cell-review" : flags.length ? "cell-notice" : "",
        c.name in row.edited ? "cell-edited" : ""].filter(Boolean).join(" ");
      const text = (value === null || value === undefined || value === "") && raw ? raw : fmt(value, c.type);
      const tips = [text, ...flags.map((i) => i.message)];
      if (c.name in row.edited) tips.push(`人工修改，原值：${row.edited[c.name] ?? "（空白）"}`);
      return el("td", { class: classes || null, title: tips.filter(Boolean).join("\n") || null },
        (value === null || value === undefined || value === "") && raw ? el("span", { class: "raw", text: raw }) : text);
    })))));
  const menu = columnMenu();
  if (menuWasOpen) menu.open = true;
  put($("tabBody"),
    el("div", { class: "toolbar" },
      chips([["review", "需檢查"], ["all", "全部"], ["edited", "已修改"]], state.filter, (id) => { state.filter = id; renderTabs(); }),
      searchBox(state.search, "搜尋", (v) => { state.search = v; renderRows(); }),
      el("span", { class: "spacer" }),
      el("span", { class: "muted", text: `${rows.length} 列` }),
      menu,
      el("button", { type: "button", class: "ghost small", text: dense ? "寬鬆" : "緊湊", title: "切換表格密度",
        onclick: () => { prefs.set("dense", !dense); renderRows(); } })),
    rows.length ? el("div", { class: "table-wrap" }, table)
      : el("div", { class: "note", text: state.filter === "review" ? "沒有需要檢查的列。" : "沒有符合的列。" }),
    rows.length > 2000 ? el("p", { class: "muted", text: "只顯示前 2000 列，請用搜尋縮小範圍。" }) : null);
}

/* ---------- 單列細節 ---------- */
function issueLine(issue, extra = null) {
  const actions = [];
  if (issue.stage === "match" && issue.rid) {
    const match = state.result.matches.find((m) => issue.message.startsWith(`${m.name}：`));
    if (match) actions.push(el("button", { type: "button", class: "link", text: "前往配對", onclick: () => focusMatch(match.name, issue.rid.split("|")[0]) }));
  }
  if (issue.code === "unmapped") actions.push(el("button", { type: "button", class: "link", text: "補對照", onclick: () => { state.tab = "mapping"; renderTabs(); } }));
  if (extra) actions.push(extra);
  if (issue.level !== "error") {
    actions.push(el("button", {
      type: "button", class: "link", text: issue.dismissed ? "取消確認" : "確認無誤",
      onclick: () => act("dismiss", { keys: [issue.key], on: !issue.dismissed }),
    }));
  }
  return el("div", { class: `issue ${issue.dismissed ? "dismissed" : issue.level}` },
    el("span", { class: `dot ${issue.level}` }),
    el("div", { class: "body" }, el("div", { class: "message", text: issue.message }),
      el("div", { class: "issue-actions" }, el("span", { class: "meta", text: `${STAGE_TEXT[issue.stage] || issue.stage}${issue.dismissed ? "・已確認" : ""}` }), actions)));
}

function renderDrawer() {
  const r = state.result;
  const row = r && state.tab === "rows" && r.output.rows.find((x) => x.rid === state.selected);
  $("drawer").hidden = !row;
  document.querySelector(".layout").classList.toggle("with-drawer", Boolean(row));
  if (!row) return;
  $("drawerTitle").textContent = row.sheet && state.result.inputs && Object.values(state.result.inputs).some((i) => (i.sheets || []).length > 1)
    ? `${row.sheet}・第 ${row.row ?? "?"} 列` : `第 ${row.row ?? "?"} 列`;
  const issues = row.issues.map((i) => r.issues[i]).filter((i) => i.level !== "skip");
  const fields = r.output.columns.map((c) => {
    const input = el("input", { value: row.values[c.name] ?? "", disabled: !c.editable, placeholder: row.raw[c.name] ? `原始：${row.raw[c.name]}` : "" });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") input.blur();
      if (e.key === "Escape") { input.value = row.values[c.name] ?? ""; input.blur(); }
    });
    input.addEventListener("change", () => {
      if (String(input.value) !== String(row.values[c.name] ?? "")) act("edit", { rid: row.rid, column: c.name, value: input.value });
    });
    const flagged = cellIssues(row, c.name).some((i) => i.level === "review");
    const hint = c.name in row.edited ? el("div", { class: "hint" }, `原值：${row.edited[c.name] ?? "（空白）"}　`,
      el("button", { type: "button", class: "link", text: "還原", onclick: () => act("edit", { rid: row.rid, column: c.name, revert: true }) })) : null;
    return el("div", { class: `field${flagged ? " flag-review" : ""}` }, el("label", { text: c.name, title: c.name }), input, hint);
  });
  put($("drawerBody"),
    issues.length ? el("section", {}, el("h4", { class: "section-title", text: "需要注意" }), el("div", { class: "list" }, issues.map((i) => issueLine(i)))) : null,
    el("section", {}, el("h4", { class: "section-title", text: "欄位" }), el("p", { class: "muted small-text", style: "margin:-4px 0 10px", text: "修改後按 Enter，會保留原值。" }), fields),
    el("section", {}, el("h4", { class: "section-title", text: "來源" }),
      el("dl", { class: "kv" }, row.sheet ? [el("dt", { text: "工作表" }), el("dd", { text: row.sheet })] : null,
        el("dt", { text: "Excel 列" }), el("dd", { text: row.row ?? "" }), el("dt", { text: "列代號" }), el("dd", { text: row.rid }))));
}

/* ---------- 配對 ---------- */
function focusMatch(name, rid) {
  Object.assign(state, { tab: "match", matchName: name, matchFilter: "all", matchFocus: rid, matchSearch: "" });
  renderTabs();
}

/* 先顯示比對用到的欄位，其他欄位收起來，避免一張卡片塞太多字 */
function pickColumns(values, preferred) {
  const keys = Object.keys(values);
  if (state.matchAll) return keys;
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
    let cls = null;
    if (compare && k in compare && v !== null && compare[k] !== null) cls = String(v) === String(compare[k]) ? "same" : "diff";
    return [el("dt", { text: k, title: k }), el("dd", { class: cls, text: v ?? "" })];
  }));
}

function oneLine(values, columns) {
  return columns.map((k) => values[k]).filter((v) => v !== null && v !== "").join("・");
}

function renderMatch() {
  const r = state.result;
  const match = r.matches.find((m) => m.name === state.matchName) || r.matches[0];
  state.matchName = match.name;
  const todo = new Set(["ambiguous", "unmatched", "review"]);
  const filters = { todo: (x) => todo.has(x.status), all: () => true, manual: (x) => x.status === "manual" || x.status === "none" };
  const needle = state.matchSearch.toLowerCase();
  let rows = match.rows.filter(filters[state.matchFilter]);
  if (state.matchFocus) rows = rows.filter((x) => x.left === state.matchFocus);
  if (needle) {
    rows = rows.filter((x) => JSON.stringify(match.left_rows[x.left]?.values || {}).toLowerCase().includes(needle)
      || x.rights.some((rid) => JSON.stringify(match.right_rows[rid]?.values || {}).toLowerCase().includes(needle)));
  }
  const c = match.counts;
  put($("tabBody"),
    r.matches.length > 1 ? el("div", { class: "toolbar" }, chips(r.matches.map((m) => [m.name, `${m.left} → ${m.right}`]), match.name,
      (id) => { Object.assign(state, { matchName: id, matchFocus: null, pickerFor: null }); renderTabs(); })) : null,
    el("div", { class: "toolbar" },
      chips([["todo", `需處理 ${c.ambiguous + c.unmatched + c.review}`], ["all", `全部 ${match.rows.length}`], ["manual", `人工 ${c.manual + c.none}`]],
        state.matchFilter, (id) => { Object.assign(state, { matchFilter: id, matchFocus: null }); renderTabs(); }),
      searchBox(state.matchSearch, "搜尋", (v) => { state.matchSearch = v; renderMatch(); }),
      state.matchFocus ? el("button", { type: "button", class: "ghost small", text: "顯示全部", onclick: () => { state.matchFocus = null; renderTabs(); } }) : null,
      el("span", { class: "spacer" }),
      el("button", { type: "button", class: "ghost small", text: state.matchAll ? "只看比對欄位" : "顯示全部欄位",
        onclick: () => { state.matchAll = !state.matchAll; renderMatch(); } })),
    el("p", { class: "match-meta muted" }, `${match.mode_label}・${match.strategies.join(" → ")}`,
      match.multi && match.pairs ? `・共 ${match.pairs} 組` : ""),
    rows.length ? el("div", { class: "match-list" }, rows.slice(0, 200).map((row) => matchCard(match, row)))
      : el("div", { class: "note", text: state.matchFilter === "todo" ? "所有配對都已處理。" : "沒有符合的配對。" }),
    rows.length > 200 ? el("p", { class: "muted", text: `只顯示前 200 筆，共 ${rows.length} 筆，請用搜尋縮小範圍。` }) : null,
    match.unused_right.length ? el("details", { class: "unused" },
      el("summary", { text: `${match.right} 沒用到的列（${match.unused_right.length}）` }),
      el("div", { class: "picker-list" }, match.unused_right.slice(0, 200).map((rid) => el("div", { class: "pick-row" },
        el("span", { class: "rowno", text: match.right_rows[rid].row ?? "" }),
        el("span", { class: "summary", text: oneLine(match.right_rows[rid].values, Object.keys(match.right_rows[rid].values)) })))))
      : null);
}

function matchCard(match, row) {
  const left = match.left_rows[row.left];
  const [label, tone] = MATCH_TEXT[row.status];
  const decide = (rights) => { state.pickerFor = null; return act("match", { match: match.name, left: row.left, rights }); };
  const reviewIssue = state.result.issues.find((i) => i.code === "match_review" && i.rid === row.left && i.message.startsWith(`${match.name}：`));
  const leftColumns = pickColumns(left.values, match.show.left);
  const sample = match.right_rows[row.rights[0] || row.candidates[0]?.rid] || Object.values(match.right_rows)[0];
  const rightColumns = sample ? pickColumns(sample.values, match.show.right) : [];
  const togglePicker = () => { state.pickerFor = state.pickerFor === row.left ? null : row.left; renderMatch(); };

  const actions = [];
  if (reviewIssue && !reviewIssue.dismissed) actions.push(el("button", { type: "button", class: "small primary", text: "確認正確", onclick: () => act("dismiss", { keys: [reviewIssue.key], on: true }) }));
  if (row.status === "manual" || row.status === "none") actions.push(el("button", { type: "button", class: "small ghost", text: "交回自動", onclick: () => decide(null) }));
  actions.push(el("button", { type: "button", class: "small ghost", text: match.multi ? "加入" : row.rights.length ? "改選" : "手動指定", onclick: togglePicker }));
  if (row.status !== "none") actions.push(el("button", { type: "button", class: "small ghost", text: "沒有配對", onclick: () => decide([]) }));

  let side;
  if (row.status === "ambiguous") {
    side = el("div", { class: "candidates" }, el("p", { class: "muted small-text", style: "margin:0 0 4px", text: match.multi ? "選擇要歸到這一列的資料" : "選擇正確的一筆" }),
      row.candidates.map((cand) => {
        const target = match.right_rows[cand.rid];
        return el("div", { class: "candidate" },
          valuesList(target.values, rightColumns, left.values),
          el("div", { class: "candidate-side" }, cand.score !== null && cand.score !== undefined ? el("span", { class: "muted", text: `相似 ${Number(cand.score).toFixed(2)}` }) : null,
            el("button", { type: "button", class: "small primary", text: "選這筆", onclick: () => decide(match.multi ? [...row.rights, cand.rid] : [cand.rid]) })));
      }));
  } else if (row.rights.length === 1 && !match.multi) {
    side = valuesList(match.right_rows[row.rights[0]].values, rightColumns, left.values);
  } else if (row.rights.length) {
    side = el("div", { class: "picker-list" }, row.rights.map((rid) => el("div", { class: "pick-row" },
      el("span", { class: "rowno", text: match.right_rows[rid].row ?? "" }),
      el("span", { class: "summary", title: oneLine(match.right_rows[rid].values, Object.keys(match.right_rows[rid].values)), text: oneLine(match.right_rows[rid].values, rightColumns) }),
      el("button", { type: "button", class: "link danger", text: "移除", onclick: () => decide(row.rights.filter((x) => x !== rid)) }))));
  } else {
    side = el("p", { class: "muted", text: row.status === "none" ? "已確認沒有對應的資料" : "沒有找到對應的資料" });
  }
  const rightTitle = row.rights.length === 1 && !match.multi ? `${match.right}・第 ${match.right_rows[row.rights[0]].row ?? "?"} 列`
    : row.rights.length ? `${match.right}・${row.rights.length} 列` : match.right;
  return el("article", { class: "match-card" },
    el("header", {},
      el("span", { class: `badge ${tone}`, text: label }),
      row.how ? el("span", { class: "muted", text: row.how }) : null,
      el("span", { class: "spacer" }), actions),
    el("div", { class: "match-body" },
      el("div", { class: "side" }, el("h4", { text: `${match.left}・第 ${left.row ?? "?"} 列` }), valuesList(left.values, leftColumns)),
      el("div", { class: "side" }, el("h4", { text: rightTitle }), side,
        state.pickerFor === row.left ? picker(match, row, rightColumns, decide) : null)));
}

function picker(match, row, columns, decide) {
  const taken = new Set(row.rights);
  const unused = new Set(match.unused_right);
  const list = el("div", { class: "picker-list" });
  const draw = (text) => {
    const needle = text.trim().toLowerCase();
    const rids = Object.keys(match.right_rows)
      .filter((rid) => !taken.has(rid) && (!needle || JSON.stringify(match.right_rows[rid].values).toLowerCase().includes(needle)))
      .sort((a, b) => Number(unused.has(b)) - Number(unused.has(a)));
    put(list, rids.length ? rids.slice(0, 50).map((rid) => el("div", { class: "pick-row" },
      el("span", { class: "rowno", text: match.right_rows[rid].row ?? "" }),
      el("span", { class: "summary", title: oneLine(match.right_rows[rid].values, Object.keys(match.right_rows[rid].values)), text: oneLine(match.right_rows[rid].values, columns) }),
      unused.has(rid) ? el("span", { class: "badge", text: "未使用" }) : null,
      el("button", { type: "button", class: "small", text: match.multi ? "加入" : "選這筆", onclick: () => decide(match.multi ? [...row.rights, rid] : [rid]) })))
      : el("p", { class: "muted", text: "找不到符合的資料" }));
  };
  const input = el("input", { class: "search", type: "search", placeholder: `在 ${match.right} 裡搜尋` });
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
    el("tbody", {}, rows.map((r) => el("tr", {}, el("td", { text: r.input }), el("td", { class: "rowno", text: r.row }), el("td", { text: r.label }),
      names.map((n) => el("td", { text: r.values[n] ?? "", title: r.values[n] ?? null }))))))));
}

/* ---------- 所有警示 ---------- */
function renderIssues() {
  const filters = {
    review: (i) => !i.dismissed && (i.level === "review" || i.level === "error"), notice: (i) => !i.dismissed && i.level === "notice",
    dismissed: (i) => i.dismissed, all: () => true,
  };
  const issues = activeIssues().filter(filters[state.issueFilter]);
  const rowOf = new Map();
  state.result.output.rows.forEach((row) => row.issues.forEach((i) => rowOf.set(i, row)));
  const selectable = issues.filter((i) => i.level !== "error");
  put($("tabBody"),
    el("div", { class: "toolbar" },
      chips([["review", "需檢查"], ["notice", "提示"], ["dismissed", "已確認"], ["all", "全部"]], state.issueFilter,
        (id) => { state.issueFilter = id; state.checked.clear(); renderTabs(); }),
      el("span", { class: "spacer" }),
      selectable.length ? el("button", { type: "button", class: "ghost small", text: "全選", onclick: () => { selectable.forEach((i) => state.checked.add(i.key)); renderTabs(); } }) : null,
      state.checked.size ? el("button", {
        type: "button", class: "small primary", text: `${state.issueFilter === "dismissed" ? "取消確認" : "確認無誤"}（${state.checked.size}）`,
        onclick: async () => { const keys = [...state.checked]; state.checked.clear(); await act("dismiss", { keys, on: state.issueFilter !== "dismissed" }); },
      }) : null),
    issues.length ? el("div", { class: "issue-list" }, issues.map((issue) => {
      const row = rowOf.get(issue.id);
      const box = el("input", { type: "checkbox", checked: state.checked.has(issue.key), disabled: issue.level === "error" });
      box.addEventListener("change", () => { box.checked ? state.checked.add(issue.key) : state.checked.delete(issue.key); renderTabs(); });
      return el("div", { class: "issue-row" }, box, issueLine(issue, row ? el("button", {
        type: "button", class: "link", text: `第 ${row.row ?? "?"} 列`,
        onclick: () => { Object.assign(state, { tab: "rows", filter: "all", selected: row.rid }); renderTabs(); },
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

function bind() {
  $("newRecipe").addEventListener("click", () => editRecipe());
  $("workbookInput").addEventListener("change", (e) => { if (e.target.files[0]) uploadWorkbook(e.target.files[0]); e.target.value = ""; });
  const zone = $("dropZone");
  zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("over"));
  zone.addEventListener("drop", (e) => { e.preventDefault(); zone.classList.remove("over"); if (e.dataTransfer.files[0]) uploadWorkbook(e.dataTransfer.files[0]); });
  $("runButton").addEventListener("click", runNow);
  $("rerunButton").addEventListener("click", () => act("rerun"));
  $("drawerClose").addEventListener("click", () => { state.selected = null; renderTabs(); });
  $("dialog").addEventListener("click", (e) => { if (e.target === $("dialog")) closeDialog(); });
}

async function main() {
  watchConnection();
  bind();
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
