// background.js — Service Worker (Manifest V3)

chrome.runtime.onInstalled.addListener(() => {
  console.log("苏格拉底辩证提问 扩展已安装");
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "openSocratic") {
    chrome.windows.getCurrent({ populate: true }, (window) => {
      chrome.sidePanel.open({ windowId: window.id });
    });
    sendResponse({ status: "ok" });
  }
  return true;
});
