import { makeSessionId, sendChatMessage } from "./chat-client.js";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
const SESSION_KEY = "travel-agent-session-id";

const elements = {
  apiBaseUrl: document.querySelector("#apiBaseUrl"),
  chatLog: document.querySelector("#chatLog"),
  form: document.querySelector("#chatForm"),
  input: document.querySelector("#messageInput"),
  sendButton: document.querySelector("#sendButton"),
  status: document.querySelector("#statusText"),
  sessionId: document.querySelector("#sessionId"),
  resetSession: document.querySelector("#resetSession"),
};

function getOrCreateSessionId() {
  const existing = localStorage.getItem(SESSION_KEY);
  if (existing) {
    return existing;
  }
  const next = makeSessionId();
  localStorage.setItem(SESSION_KEY, next);
  return next;
}

let sessionId = getOrCreateSessionId();
elements.apiBaseUrl.value = DEFAULT_API_BASE_URL;
elements.sessionId.textContent = sessionId;

function setStatus(text, tone = "neutral") {
  elements.status.textContent = text;
  elements.status.dataset.tone = tone;
}

function appendMessage(role, text) {
  const item = document.createElement("article");
  item.className = `message ${role}`;

  const label = document.createElement("div");
  label.className = "message-label";
  label.textContent = role === "user" ? "你" : "差旅助手";

  const body = document.createElement("div");
  body.className = "message-body";
  body.textContent = text;

  item.append(label, body);
  elements.chatLog.append(item);
  elements.chatLog.scrollTop = elements.chatLog.scrollHeight;
  return item;
}

function setBusy(isBusy) {
  elements.sendButton.disabled = isBusy;
  elements.input.disabled = isBusy;
}

elements.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = elements.input.value.trim();
  if (!message) {
    elements.input.focus();
    return;
  }

  appendMessage("user", message);
  elements.input.value = "";
  setBusy(true);
  setStatus("正在请求后端...", "busy");

  try {
    const result = await sendChatMessage({
      apiBaseUrl: elements.apiBaseUrl.value || DEFAULT_API_BASE_URL,
      message,
      sessionId,
      userId: "web-user",
    });
    sessionId = result.sessionId;
    localStorage.setItem(SESSION_KEY, sessionId);
    elements.sessionId.textContent = sessionId;
    appendMessage("assistant", result.text);
    setStatus("已连接本地后端", "ok");
  } catch (error) {
    appendMessage("assistant", `请求失败：${error.message}`);
    setStatus("请求失败，请检查后端服务", "error");
  } finally {
    setBusy(false);
    elements.input.focus();
  }
});

elements.resetSession.addEventListener("click", () => {
  sessionId = makeSessionId();
  localStorage.setItem(SESSION_KEY, sessionId);
  elements.sessionId.textContent = sessionId;
  elements.chatLog.replaceChildren();
  appendMessage("assistant", "新的会话已开始。你可以直接描述差旅需求。");
  setStatus("已重置会话", "ok");
  elements.input.focus();
});

appendMessage(
  "assistant",
  "你好，我可以帮你规划差旅、检查差标、整理审批风险。试试输入：帮我规划 2026-06-01 北京到上海的两天差旅，预算 3000 元。",
);
setStatus("等待发送消息", "neutral");
