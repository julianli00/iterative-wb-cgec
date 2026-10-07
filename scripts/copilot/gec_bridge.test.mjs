import assert from "node:assert/strict";
import test from "node:test";
import { generateCorrection, sessionConfig } from "./gec_bridge.mjs";

function fixture(usageOverrides = {}, extraEvents = []) {
  const configs = [];
  let disconnected = 0;
  const client = {
    async createSession(config) {
      configs.push(config);
      return {
        sessionId: `session-${configs.length}`,
        async sendAndWait() {
          config.onEvent({
            type: "assistant.usage",
            data: { model: "gpt-6-astra", inputTokens: 10, outputTokens: 3, finishReason: "stop", ...usageOverrides },
          });
          for (const event of extraEvents) config.onEvent(event);
          return { data: { content: "corrected sentence" } };
        },
        async abort() {},
        async disconnect() { disconnected++; },
      };
    },
  };
  return { client, configs, disconnected: () => disconnected };
}

test("sessions disable ambient context and leave generation settings at defaults", () => {
  const config = sessionConfig("gpt-6-astra", "/isolated");
  assert.deepEqual(config.availableTools, []);
  for (const key of ["enableConfigDiscovery", "enableSessionStore", "enableSkills", "enableHostGitOperations", "enableFileHooks"]) {
    assert.equal(config[key], false);
  }
  assert.equal(config.remoteSession, "off");
  assert.equal(config.systemMessage.mode, "replace");
  for (const key of ["temperature", "reasoningEffort", "modelCapabilities"]) {
    assert.equal(Object.hasOwn(config, key), false);
  }
  assert.equal(config.onPermissionRequest().kind, "denied-by-rules");
});

test("each correction creates an independent session and records usage", async () => {
  const fake = fixture();
  const request = { prompt: "correct this", timeout: 1 };
  const first = await generateCorrection(fake.client, request, "gpt-6-astra", "/isolated");
  const second = await generateCorrection(fake.client, request, "gpt-6-astra", "/isolated");
  assert.notEqual(first.metadata.session_id, second.metadata.session_id);
  assert.equal(fake.disconnected(), 2);
  assert.deepEqual(first.metadata.usage, { prompt_tokens: 10, completion_tokens: 3, total_tokens: 13 });
});

for (const [label, overrides, pattern] of [
  ["wrong model", { model: "different-model" }, /Model mismatch/],
  ["truncated output", { finishReason: "length" }, /truncated/],
  ["missing usage", { inputTokens: undefined }, /token usage/],
]) {
  test(`rejects ${label} and closes the session`, async () => {
    const fake = fixture(overrides);
    await assert.rejects(
      generateCorrection(fake.client, { prompt: "correct this", timeout: 1 }, "gpt-6-astra", "/isolated"),
      pattern,
    );
    assert.equal(fake.disconnected(), 1);
  });
}

test("unexpected tool execution fails closed", async () => {
  const fake = fixture({}, [{ type: "tool.execution_start", data: {} }]);
  await assert.rejects(
    generateCorrection(fake.client, { prompt: "correct this", timeout: 1 }, "gpt-6-astra", "/isolated"),
    /Unexpected tool call/,
  );
});

test("content filtering is explicitly reported for the existing identity policy", async () => {
  const fake = fixture({ finishReason: "content_filter", contentFilterTriggered: true });
  const result = await generateCorrection(
    fake.client, { prompt: "correct this", timeout: 1 }, "gpt-6-astra", "/isolated",
  );
  assert.equal(result.metadata.content_filter_fallback, true);
});
