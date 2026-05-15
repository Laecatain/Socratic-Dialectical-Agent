// sidepanel.js — 侧边栏核心逻辑
(function () {
  "use strict";

  const API_URL = "http://localhost:8000/api/v1/socratic/stream";

  // ---------- DOM refs ----------
  const mainContent = document.getElementById("mainContent");
  const statusBadge = document.getElementById("statusBadge");
  const backendStatus = document.getElementById("backendStatus");

  let currentAbort = null;
  let currentQuestionEl = null;
  let currentCursorEl = null;

  // ---------- 初始化：检查后端健康状态 ----------
  checkBackendHealth();

  async function checkBackendHealth() {
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

  // ---------- 监听来自 content script 的消息 ----------
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === "sendToSidePanel") {
      handleNewQuery(message.text, message.contextUrl);
      sendResponse({ status: "received" });
    }
    return true;
  });

  // ---------- 处理新查询 ----------
  function handleNewQuery(text, contextUrl) {
    // 取消之前的请求
    if (currentAbort) {
      currentAbort.abort();
      currentAbort = null;
    }

    renderUI(text, contextUrl);
    streamFromBackend(text, contextUrl);
  }

  // ---------- 渲染 UI 结构 ----------
  function renderUI(selectedText, contextUrl) {
    mainContent.className = "chat-area";
    mainContent.innerHTML = "";

    // 来源卡片
    const sourceCard = document.createElement("div");
    sourceCard.className = "source-card";
    sourceCard.innerHTML = '<div class="label">📌 划词内容</div>' +
      '<div class="source-text">' + escapeHtml(selectedText) + '</div>' +
      (contextUrl ? '<div class="source-url">' + escapeHtml(contextUrl) + '</div>' : '');
    mainContent.appendChild(sourceCard);

    // 状态消息
    const statusMsg = document.createElement("div");
    statusMsg.className = "status-msg";
    statusMsg.id = "statusMsg";
    statusMsg.innerHTML = '<div class="dot"></div>正在分析...';
    mainContent.appendChild(statusMsg);

    // 提问卡片（先占位）
    const qCard = document.createElement("div");
    qCard.className = "question-card";
    qCard.style.display = "none";
    qCard.id = "questionCard";
    qCard.innerHTML = '<div class="q-label">💬 苏格拉底之问</div>' +
      '<div class="q-text" id="qText"><span class="cursor" id="qCursor"></span></div>';
    mainContent.appendChild(qCard);

    currentQuestionEl = null;
    currentCursorEl = null;

    statusBadge.textContent = "分析中...";
    statusBadge.style.background = "#f59e0b";
  }

  // ---------- 流式请求 ----------
  async function streamFromBackend(text, contextUrl) {
    const abortController = new AbortController();
    currentAbort = abortController;

    const statusMsg = document.getElementById("statusMsg");
    const questionCard = document.getElementById("questionCard");

    try {
      const response = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text, context_url: contextUrl }),
        signal: abortController.signal,
      });

      if (!response.ok) {
        throw new Error("HTTP " + response.status + ": " + response.statusText);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // 解析 SSE 事件
        const lines = buffer.split("\n");
        buffer = lines.pop() || ""; // 保留不完整的行

        let currentEvent = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            const dataStr = line.slice(6);
            try {
              const data = JSON.parse(dataStr);
              handleSSEEvent(currentEvent, data, statusMsg, questionCard);
            } catch (e) {
              // JSON 解析失败，跳过
            }
          }
        }
      }

      // 处理 buffer 中剩余的数据
      if (buffer.trim()) {
        // 尝试最后清理
      }

    } catch (err) {
      if (err.name === "AbortError") return;
      showError(err.message);
    } finally {
      if (currentAbort === abortController) {
        currentAbort = null;
      }
      // 隐藏光标
      if (currentCursorEl) {
        currentCursorEl.classList.add("done");
        currentCursorEl = null;
      }
      statusBadge.textContent = "就绪";
      statusBadge.style.background = "#22c55e";
    }
  }

  // ---------- SSE 事件处理 ----------
  function handleSSEEvent(eventType, data, statusMsg, questionCard) {
    switch (eventType) {
      case "status":
        if (statusMsg) {
          statusMsg.innerHTML = '<div class="dot"></div>' + escapeHtml(data.message || "");
        }
        break;

      case "node_start":
        if (statusMsg) {
          statusMsg.innerHTML = '<div class="dot"></div>' + escapeHtml(data.message || data.node || "");
        }
        break;

      case "node_end":
        // 节点完成，可以显示中间结果（调试用）
        break;

      case "token":
        // 打字机效果：追加 token
        appendToken(data.content);
        break;

      case "done":
        if (statusMsg) statusMsg.style.display = "none";
        // 显示分析结果
        if (data.core_claim || data.philosophy) {
          showDebugInfo(data.core_claim, data.philosophy);
        }
        finishTyping();
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

    // 首次收到 token 时显示卡片
    if (questionCard.style.display === "none") {
      questionCard.style.display = "block";
    }

    if (!currentQuestionEl) {
      currentQuestionEl = document.createTextNode("");
      qText.insertBefore(currentQuestionEl, qText.firstChild);
    }

    currentQuestionEl.textContent += tokenText;

    // 确保光标在最后
    if (currentCursorEl) {
      currentCursorEl.remove();
    }
    currentCursorEl = document.createElement("span");
    currentCursorEl.className = "cursor";
    currentCursorEl.id = "qCursor";
    qText.appendChild(currentCursorEl);

    // 更新状态消息
    const statusMsg = document.getElementById("statusMsg");
    if (statusMsg) {
      statusMsg.innerHTML = '<div class="dot"></div>苏格拉底正在提问...';
    }

    // 自动滚动
    mainContent.scrollTop = mainContent.scrollHeight;
  }

  function finishTyping() {
    if (currentCursorEl) {
      currentCursorEl.classList.add("done");
      currentCursorEl = null;
    }
  }

  // ---------- 调试信息 ----------
  function showDebugInfo(coreClaim, philosophy) {
    const debugCard = document.createElement("div");
    debugCard.className = "debug-card";
    const claimShort = coreClaim ? coreClaim.slice(0, 80) + (coreClaim.length > 80 ? "..." : "") : "无";
    debugCard.innerHTML = "核心主张: <span>" + escapeHtml(claimShort) + "</span> &nbsp;|&nbsp; 流派: <span>" + escapeHtml(philosophy || "未知") + "</span>";
    mainContent.appendChild(debugCard);
  }

  // ---------- 错误展示 ----------
  function showError(message) {
    const errCard = document.createElement("div");
    errCard.className = "error-card";
    errCard.textContent = "❌ " + (message || "未知错误");
    mainContent.appendChild(errCard);
    finishTyping();
    statusBadge.textContent = "出错";
    statusBadge.style.background = "#e94560";
  }

  // ---------- 工具函数 ----------
  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  console.log("[苏格拉底提问] Side panel 已初始化");
})();
