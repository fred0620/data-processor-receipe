"use strict";
/* 使用手冊離線搜尋：純本機比對標題與段落，不載入外部資源，符合工具 CSP。 */
(function () {
  const input = document.getElementById("manualSearch");
  const status = document.getElementById("manualSearchStatus");
  if (!input) return;
  const sections = [...document.querySelectorAll("main section[data-sec]")];
  const tocLinks = [...document.querySelectorAll(".sidebar-toc a")];

  const filter = () => {
    const q = input.value.trim().toLowerCase();
    let shown = 0;
    for (const sec of sections) {
      const match = !q || sec.textContent.toLowerCase().includes(q);
      sec.hidden = !match;
      if (match) shown += 1;
    }
    for (const a of tocLinks) {
      const id = (a.getAttribute("href") || "").replace(/^#/, "");
      const target = id ? document.getElementById(id) : null;
      const sec = target?.closest("section[data-sec]");
      a.parentElement.hidden = Boolean(q && sec && sec.hidden);
    }
    if (status) status.textContent = q ? `找到 ${shown} 節` : "";
  };

  input.addEventListener("input", filter);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { input.value = ""; filter(); }
  });
})();
