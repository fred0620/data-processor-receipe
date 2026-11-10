"use strict";
const $ = (id) => document.getElementById(id);

function toast(message, bad = false) {
  const node = $("toast");
  node.textContent = message;
  node.classList.toggle("bad", bad);
  node.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { node.hidden = true; }, 5000);
}

async function api(path, options = {}) {
  const init = { ...options, headers: { "Content-Type": "application/json", ...(options.headers || {}) } };
  const response = await fetch(path, init);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "請求失敗");
  return data;
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
function watchConnection() {
  heartbeat();
  setInterval(heartbeat, 15000);
  window.addEventListener("pagehide", () => navigator.sendBeacon(`/api/bye?client=${encodeURIComponent(clientId)}`));
  window.addEventListener("pageshow", (event) => { if (event.persisted) heartbeat(); });
}

/* ---------- 範例功能：換成工具真正的功能 ---------- */
$("exampleForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const data = await api("/api/example", { method: "POST", body: JSON.stringify({ text: $("exampleInput").value }) });
    $("result").textContent = `收到：${data.echo}`;
  } catch (error) {
    toast(error.message, true);
  }
});

async function main() {
  watchConnection();
  try {
    const status = await api("/api/status");
    $("version").textContent = status.version ? `v${status.version}` : "";
  } catch (error) {
    toast(error.message, true);
  }
}
main();
