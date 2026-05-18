import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildChatPayload,
  extractAssistantText,
  makeSessionId,
} from "../src/chat-client.js";

test("buildChatPayload creates a non-streaming chat request with session and user ids", () => {
  const payload = buildChatPayload({
    message: "帮我规划北京到上海的差旅",
    sessionId: "session-123",
    userId: "demo-user",
  });

  assert.deepEqual(payload, {
    session_id: "session-123",
    user_id: "demo-user",
    locale: "zh-CN",
    stream: false,
    messages: [{ role: "user", content: "帮我规划北京到上海的差旅" }],
  });
});

test("buildChatPayload rejects blank messages", () => {
  assert.throws(
    () => buildChatPayload({ message: "   ", sessionId: "session-123", userId: "demo-user" }),
    /message is required/,
  );
});

test("extractAssistantText reads OpenAI-compatible response content", () => {
  const response = {
    choices: [
      {
        message: {
          role: "assistant",
          content: "可以，我先确认你的出发日期。",
        },
      },
    ],
  };

  assert.equal(extractAssistantText(response), "可以，我先确认你的出发日期。");
});

test("makeSessionId creates stable travel-agent session ids", () => {
  const sessionId = makeSessionId(() => 1710000000000);

  assert.equal(sessionId, "web-session-1710000000000");
});
