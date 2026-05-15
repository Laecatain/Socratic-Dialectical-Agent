// content.js — 划词监听 + 悬浮按钮
(function () {
  "use strict";

  let floatBtn = null;

  function getOrCreateBtn() {
    if (!floatBtn) {
      floatBtn = document.createElement("button");
      floatBtn.className = "socratic-float-btn";
      floatBtn.textContent = "🤔 苏格拉底提问";
      floatBtn.style.display = "none";
      floatBtn.addEventListener("click", handleClick);
      floatBtn.addEventListener("mousedown", (e) => e.stopPropagation());
      document.body.appendChild(floatBtn);
    }
    return floatBtn;
  }

  function handleClick(e) {
    e.preventDefault();
    e.stopPropagation();

    const selection = window.getSelection();
    const text = selection ? selection.toString().trim() : "";
    if (!text) return;

    const contextUrl = window.location.href;

    chrome.runtime.sendMessage({ action: "openSocratic" }, () => {
      setTimeout(() => {
        chrome.runtime.sendMessage({
          action: "sendToSidePanel",
          text: text,
          contextUrl: contextUrl
        });
      }, 300);
    });

    hideBtn();
  }

  function showBtn(x, y) {
    const btn = getOrCreateBtn();
    btn.style.display = "block";
    btn.style.left = x + "px";
    btn.style.top = y + "px";
  }

  function hideBtn() {
    if (floatBtn) floatBtn.style.display = "none";
  }

  document.addEventListener("mouseup", (e) => {
    setTimeout(() => {
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed) { hideBtn(); return; }
      const text = selection.toString().trim();
      if (text.length < 2 || text.length > 5000) { hideBtn(); return; }
      const range = selection.getRangeAt(0);
      const rect = range.getBoundingClientRect();
      if (!rect || (rect.width === 0 && rect.height === 0)) { hideBtn(); return; }
      const btnX = rect.right + window.scrollX + 10;
      const btnY = rect.bottom + window.scrollY + 6;
      showBtn(btnX, btnY);
    }, 10);
  });

  document.addEventListener("mousedown", (e) => {
    if (floatBtn && e.target !== floatBtn) hideBtn();
  });

  document.addEventListener("scroll", () => hideBtn(), { passive: true });
  console.log("[苏格拉底提问] Content script 已注入");
})();
