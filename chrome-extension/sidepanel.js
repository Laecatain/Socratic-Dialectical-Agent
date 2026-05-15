// sidepanel.js — 流式接收苏格拉底提问
(function () {
  "use strict";

  const API_URL = "http://localhost:8000/api/v1/socratic/stream";

  const mainContent = document.getElementById("mainContent");
  const statusBadge = document.getElementById("statusBadge");
  const backendStatus = document.getElementById("backendStatus");

  let currentAbort = null;
  let currentQuestionEl = null;
  let currentCursorEl = null;

  // ---------- 健康检查 ----------
  checkHealth();
  async function checkHealth() {
    try {
      const res = await fetch("http://localhost:8000/health", { signal: AbortSignal.timeout(3000) });
      if (res.ok) {
        backendStatus.textContent = "已连接 ✓";
        backendStatus.style.color = "#4ade80";
        statusBadge.textContent = "就绪";
        statusBadge.style.background = "#22c55e";
      }
    } catch {
      backendStatus.textContent = "未连接 ✗";
      backendStatus.style.color = "#e94560";
      statusBadge.textContent = "离线";
      statusBadge.style.background = "#e94560";
    }
  }

  // ---------- 监听来自 background.js 的消息 ----------
  chrome.runtime.onMessage.addListener((message) => {
    if (message.type === "SELECT_TEXT" && message.text) {
      handleQuery(message.text, message.contextUrl || "");
    }
  });

  function handleQuery(text, contextUrl) {
    if (currentAbort) {
      currentAbort.abort();
      currentAbort = null;
    }
    renderUI(text, contextUrl);
    streamFromBackend(text, contextUrl);
  }

  // ---------- 渲染 UI ----------
  function renderUI(selectedText, contextUrl) {
    mainContent.className = "chat-area";
    mainContent.innerHTML = "";

    const sourceCard = document.createElement("div");
    sourceCard.className = "source-card";
    sourceCard.innerHTML =
      '<div class="label">📌 划词内容</div>' +
      '<div class="source-text">' + esc(selectedText) + '</div>' +
      (contextUrl ? '<div class="source-url">' + esc(contextUrl) + '</div>' : '');
    mainContent.appendChild(sourceCard);

    const statusMsg = document.createElement("div");
    statusMsg.className = "status-msg";
    statusMsg.id = "statusMsg";
    statusMsg.innerHTML = '<div class="dot"></div>正在分析...';
    mainContent.appendChild(statusMsg);

    const qCard = document.createElement("div");
    qCard.className = "question-card";
    qCard.style.display = "none";
    qCard.id = "questionCard";
    qCard.innerHTML =
      '<div class="q-label">💬 苏格拉底之问</div>' +
      '<div class="q-text" id="qText"><span class="cursor" id="qCursor"></span></div>';
    mainContent.appendChild(qCard);

    currentQuestionEl = null;
    currentCursorEl = null;
    statusBadge.textContent = "分析中...";
    statusBadge.style.background = "#f59e0b";
  }

  // ---------- 流式请求（fetch + body.getReader） ----------
  async function streamFromBackend(text, contextUrl) {
    const abortController = new AbortController();
    currentAbort = abortController;

    const statusMsg = document.getElementById("statusMsg");

    try {
      const response = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, context_url: contextUrl }),
        signal: abortController.signal,
      });

      if (!response.ok) {
        throw new Error("HTTP " + response.status);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        let currentEvent = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            const dataStr = line.slice(6);
            // 处理 [DONE] 标记
            if (dataStr === "[DONE]") {
              finishStreaming();
              return;
            }
            try {
              const data = JSON.parse(dataStr);
              handleEvent(currentEvent, data, statusMsg);
            } catch (_) { /* skip malformed */ }
          }
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") {
        showError(err.message);
      }
    } finally {
      if (currentAbort === abortController) currentAbort = null;
      finishStreaming();
    }
  }

  function finishStreaming() {
    if (currentCursorEl) {
      currentCursorEl.classList.add("done");
      currentCursorEl = null;
    }
    statusBadge.textContent = "就绪";
    statusBadge.style.background = "#22c55e";
    const sm = document.getElementById("statusMsg");
    if (sm) sm.style.display = "none";
  }

  // ---------- SSE 事件分发 ----------
  function handleEvent(eventType, data, statusMsg) {
    switch (eventType) {
      case "status":
        if (statusMsg) {
          statusMsg.innerHTML = '<div class="dot"></div>' + esc(data.message || "");
        }
        break;

      case "node_start":
        if (statusMsg) {
          statusMsg.innerHTML = '<div class="dot"></div>' + esc(data.message || data.node || "");
        }
        break;

      case "token":
        appendToken(data.content);
        break;

      case "done":
        // 后端完成：显示分析结果
        if (data.core_claim || data.philosophy) {
          const dc = document.createElement("div");
          dc.className = "debug-card";
          const claim = data.core_claim ? data.core_claim.slice(0, 80) + (data.core_claim.length > 80 ? "..." : "") : "无";
          dc.innerHTML = "核心主张: <span>" + esc(claim) + "</span> &nbsp;|&nbsp; 流派: <span>" + esc(data.philosophy || "未知") + "</span>";
          mainContent.appendChild(dc);
        }
        break;

      case "error":
        showError(data.message);
        break;
    }
  }

  // ---------- 打字机效果 ----------
  function appendToken(tokenText) {
    const qText = document.getElementById("qText");
    const questionCard = document.getElementById("questionCard");
    if (!qText || !questionCard) return;

    if (questionCard.style.display === "none") {
      questionCard.style.display = "block";
    }

    if (!currentQuestionEl) {
      currentQuestionEl = document.createTextNode("");
      qText.insertBefore(currentQuestionEl, qText.firstChild);
    }

    currentQuestionEl.textContent += tokenText;

    if (currentCursorEl) currentCursorEl.remove();
    currentCursorEl = document.createElement("span");
    currentCursorEl.className = "cursor";
    currentCursorEl.id = "qCursor";
    qText.appendChild(currentCursorEl);

    const sm = document.getElementById("statusMsg");
    if (sm) sm.innerHTML = '<div class="dot"></div>苏格拉底正在提问...';

    mainContent.scrollTop = mainContent.scrollHeight;
  }

  function showError(message) {
    const ec = document.createElement("div");
    ec.className = "error-card";
    ec.textContent = "❌ " + (message || "未知错误");
    mainContent.appendChild(ec);
    finishStreaming();
    statusBadge.textContent = "出错";
    statusBadge.style.background = "#e94560";
  }

  function esc(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  console.log("[苏格拉底] Side panel ready");
})();
