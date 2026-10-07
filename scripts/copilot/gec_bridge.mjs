import { mkdir, readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { createInterface } from "node:readline";
import { pathToFileURL } from "node:url";

export const SYSTEM_MESSAGE = "You are a helpful assistant.";

export function sessionConfig(model, workingDirectory) {
  return {
    model,
    workingDirectory,
    systemMessage: { mode: "replace", content: SYSTEM_MESSAGE },
    availableTools: [],
    tools: [],
    mcpServers: {},
    customAgents: [],
    skillDirectories: [],
    pluginDirectories: [],
    instructionDirectories: [],
    enableConfigDiscovery: false,
    enableOnDemandInstructionDiscovery: false,
    enableHostGitOperations: false,
    enableSessionStore: false,
    enableFileHooks: false,
    enableSkills: false,
    enableCitations: false,
    skipEmbeddingRetrieval: true,
    embeddingCacheStorage: "in-memory",
    infiniteSessions: { enabled: false },
    remoteSession: "off",
    onPermissionRequest: () => ({ kind: "denied-by-rules" }),
  };
}

export async function generateCorrection(client, request, model, workingDirectory) {
  if (typeof request.prompt !== "string" || !request.prompt.trim()) {
    throw new Error("A non-empty correction prompt is required");
  }
  if (!Number.isFinite(request.timeout) || request.timeout <= 0) {
    throw new Error("A positive timeout is required");
  }
  const usages = [];
  let toolAttempted = false;
  let content = null;
  const session = await client.createSession({
    ...sessionConfig(model, workingDirectory),
    onEvent: (event) => {
      if (event.type === "assistant.usage") usages.push(event.data);
      if (event.type === "tool.execution_start") toolAttempted = true;
    },
  });
  try {
    const response = await session.sendAndWait(
      { prompt: request.prompt },
      request.timeout * 1000,
    );
    content = response?.data?.content ?? null;
    if (toolAttempted) throw new Error("Unexpected tool call in isolated GEC session");
    if (usages.length !== 1) {
      throw new Error(`Expected one model completion, received ${usages.length} usage events`);
    }
    if (usages[0].model !== model) {
      throw new Error(`Model mismatch: requested ${model}, received ${usages[0].model}`);
    }
    if (usages[0].finishReason === "length") {
      throw new Error("The model completion was truncated");
    }
    const filtered = usages[0].contentFilterTriggered === true
      || usages[0].finishReason === "content_filter";
    if (typeof content !== "string" && !filtered) {
      throw new Error("Copilot returned no correction");
    }
    const inputTokens = usages[0].inputTokens;
    const outputTokens = usages[0].outputTokens;
    if (!Number.isFinite(inputTokens) || !Number.isFinite(outputTokens)) {
      throw new Error("Copilot did not report input/output token usage");
    }
    return {
      content: content ?? "",
      metadata: {
        model,
        backend: "copilot-sdk",
        session_id: session.sessionId,
        usage: {
          prompt_tokens: inputTokens,
          completion_tokens: outputTokens,
          total_tokens: inputTokens + outputTokens,
        },
        provider_usage: usages[0],
        content_filter_fallback: filtered,
        fallback_without_thinking: false,
      },
    };
  } catch (error) {
    error.attempt = { content, usage_events: usages, session_id: session.sessionId };
    await session.abort();
    throw error;
  } finally {
    await session.disconnect();
  }
}

async function main() {
  const [model, stateDirectory] = process.argv.slice(2);
  if (!model || !stateDirectory) {
    throw new Error("Usage: node gec_bridge.mjs MODEL STATE_DIRECTORY");
  }
  const { CopilotClient } = await import("@github/copilot-sdk");
  const workingDirectory = resolve(stateDirectory, "empty-workspace");
  await mkdir(workingDirectory, { recursive: true });
  const client = new CopilotClient({
    mode: "empty",
    baseDirectory: resolve(stateDirectory),
    workingDirectory,
    logLevel: "error",
    useLoggedInUser: true,
    enableRemoteSessions: false,
  });
  const write = (value) => process.stdout.write(`${JSON.stringify(value)}\n`);
  const pending = new Set();
  try {
    await client.start();
    if (!(await client.getAuthStatus()).isAuthenticated) {
      throw new Error("Copilot is not authenticated; use the official copilot login command");
    }
    const modelInfo = (await client.listModels()).find((item) => item.id === model);
    if (!modelInfo || modelInfo.policy?.state === "disabled") {
      throw new Error(`The requested model is not available: ${model}`);
    }
    const manifest = JSON.parse(await readFile(new URL("package.json", import.meta.url), "utf8"));
    const status = await client.getStatus();
    write({
      id: "ready",
      ok: true,
      model: modelInfo,
      sdk_version: manifest.dependencies["@github/copilot-sdk"],
      runtime_version: status.version,
      system_message: SYSTEM_MESSAGE,
      generation_parameters: "provider defaults; no sampling or reasoning overrides",
      isolated_sessions: true,
    });
    const input = createInterface({ input: process.stdin });
    for await (const line of input) {
      if (!line.trim()) continue;
      const request = JSON.parse(line);
      if (request.action === "shutdown") break;
      if (request.action !== "generate" || typeof request.id !== "string") {
        throw new Error("Invalid bridge request");
      }
      const work = generateCorrection(client, request, model, workingDirectory)
        .then((result) => write({ id: request.id, ok: true, result }))
        .catch((error) => write({
          id: request.id,
          ok: false,
          error: String(error.message),
          attempt: error.attempt,
        }));
      pending.add(work);
      void work.finally(() => pending.delete(work));
    }
    input.close();
    await Promise.all(pending);
  } finally {
    const errors = await client.stop();
    if (errors.length) throw new AggregateError(errors, "Copilot shutdown failed");
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().catch((error) => {
    process.stderr.write(`${error.name}: ${error.message}\n`);
    process.exitCode = 1;
  });
}
