const DEFAULT_LOCALE = "zh-CN";

export function makeSessionId(now = Date.now) {
  return `web-session-${now()}`;
}

export function buildChatPayload({ message, sessionId, userId }) {
  const content = String(message ?? "").trim();
  if (!content) {
    throw new Error("message is required");
  }

  return {
    session_id: sessionId,
    user_id: userId,
    locale: DEFAULT_LOCALE,
    stream: false,
    messages: [{ role: "user", content }],
  };
}

export function extractAssistantText(response) {
  const choice = response?.choices?.[0];
  const content = choice?.message?.content ?? choice?.delta?.content;
  if (typeof content === "string" && content.trim()) {
    return content;
  }
  return "后端返回了空回复，请稍后再试。";
}

export async function sendChatMessage({ apiBaseUrl, message, sessionId, userId, fetchImpl = fetch }) {
  const payload = buildChatPayload({ message, sessionId, userId });
  const response = await fetchImpl(`${apiBaseUrl.replace(/\/$/, "")}/api/v1/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `HTTP ${response.status}`);
  }

  const data = await response.json();
  return {
    text: extractAssistantText(data),
    raw: data,
    sessionId: data.session_id || sessionId,
  };
}
