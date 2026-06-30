chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === "UPDATE_BADGE") {
    const count = msg.count;
    chrome.action.setBadgeText({ text: count > 0 ? String(count) : "" });
    chrome.action.setBadgeBackgroundColor({ color: "#1a1a2e" });
  }
});
