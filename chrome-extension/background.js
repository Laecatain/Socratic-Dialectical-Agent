// background.js — 右键菜单 + 划词质询
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "socratic-ask",
    title: "🤔 使用苏格拉底模式质询",
    contexts: ["selection"]
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "socratic-ask" && info.selectionText) {
    // 先打开侧边栏
    chrome.sidePanel.open({ tabId: tab.id }).then(() => {
      // 发送选中文本到侧边栏
      chrome.runtime.sendMessage({
        type: "SELECT_TEXT",
        text: info.selectionText,
        contextUrl: tab.url || ""
      });
    });
  }
});
