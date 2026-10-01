import { homedir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";

const MAX_OUTPUT_BYTES = 1024 * 1024;
const MAX_SERVER_COUNT = 1000;
const OUTER_TIMEOUT_MS = 25_000;
const SAFE_SERVER_NAME = /^[A-Za-z0-9_.:-]{1,200}$/;
const ALLOWED_REASONS: Record<string, true> = {
  connected: true,
  auth_required: true,
  connection_failed: true,
  timeout: true,
  unavailable: true,
  unparseable: true,
  not_probed: true,
  probe_in_progress: true,
};

type HealthServer = {
  name: string;
  status: "healthy" | "disabled" | "degraded";
  reason_code: string;
};

type HealthReport = {
  schema_version: 1;
  observed_at: string;
  harness: "omp";
  status: "ok" | "degraded";
  servers: HealthServer[];
};

function helperPath(): string {
  if (process.env.MANIFEST_MCP_HEALTH_HELPER) {
    return process.env.MANIFEST_MCP_HEALTH_HELPER;
  }
  const dataHome =
    process.env.XDG_DATA_HOME ?? join(homedir(), ".local", "share");
  return join(dataHome, "manifest", "health", "mcp_health.py");
}


function parseReport(raw: Uint8Array): HealthReport | undefined {
  let value: unknown;
  try {
    value = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(raw));
  } catch {
    return undefined;
  }
  if (
    !value ||
    typeof value !== "object" ||
    !("schema_version" in value) ||
    !("observed_at" in value) ||
    !("harness" in value) ||
    !("status" in value) ||
    !("servers" in value)
  ) {
    return undefined;
  }
  const { schema_version, observed_at, harness, status, servers } = value;
  if (
    schema_version !== 1 ||
    typeof observed_at !== "string" ||
    !observed_at.endsWith("Z") ||
    harness !== "omp" ||
    (status !== "ok" && status !== "degraded") ||
    !Array.isArray(servers) ||
    servers.length > MAX_SERVER_COUNT
  ) {
    return undefined;
  }
  const validatedServers: HealthServer[] = [];
  const names = new Set<string>();
  let hasDegraded = false;
  for (const server of servers) {
    if (
      !server ||
      typeof server !== "object" ||
      !("name" in server) ||
      !("status" in server) ||
      !("reason_code" in server)
    ) {
      return undefined;
    }
    const name = server.name;
    const serverStatus = server.status;
    const reasonCode = server.reason_code;
    if (
      typeof name !== "string" ||
      !SAFE_SERVER_NAME.test(name) ||
      names.has(name) ||
      (serverStatus !== "healthy" &&
        serverStatus !== "disabled" &&
        serverStatus !== "degraded") ||
      typeof reasonCode !== "string" ||
      !Object.prototype.hasOwnProperty.call(ALLOWED_REASONS, reasonCode) ||
      (serverStatus === "healthy" && reasonCode !== "connected") ||
      (serverStatus === "disabled" && reasonCode !== "not_probed") ||
      (serverStatus === "degraded" && reasonCode === "connected")
    ) {
      return undefined;
    }
    names.add(name);
    hasDegraded ||= serverStatus === "degraded";
    validatedServers.push({
      name,
      status: serverStatus,
      reason_code: reasonCode,
    });
  }
  if ((status === "degraded") !== hasDegraded) {
    return undefined;
  }
  return {
    schema_version: 1,
    observed_at,
    harness: "omp",
    status,
    servers: validatedServers,
  };
}

async function readBounded(
  stream: ReadableStream<Uint8Array>,
  onOverflow: () => void,
): Promise<Uint8Array | undefined> {
  const reader = stream.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > MAX_OUTPUT_BYTES) {
        onOverflow();
        return undefined;
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const result = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return result;
}

function degradedReasons(report: HealthReport | undefined): string {
  if (!report) return "invalid_result";
  const reasons = [
    ...new Set(
      report.servers
        .filter((server) => server.status === "degraded")
        .map((server) => server.reason_code),
    ),
  ].sort();
  return reasons.slice(0, 3).join(",") || "unavailable";
}

export default function manifestHealth(pi: ExtensionAPI) {
  pi.on("session_start", async (_event, ctx) => {
    const notify = (reason: string) => {
      if (ctx.hasUI) {
        ctx.ui.notify(`MCP health: degraded (${reason})`, "warning");
      }
    };

    try {
      const python =
        process.env.MANIFEST_HEALTH_PYTHON ?? Bun.which("python3") ?? undefined;
      if (!python) {
        notify("python_unavailable");
        return;
      }

      let inventoryObserved = true;
      const serverNames = new Set<string>();
      try {
        const tools = pi.getAllTools();
        if (!Array.isArray(tools)) {
          inventoryObserved = false;
        } else {
          for (const tool of tools) {
            if (
              !tool ||
              typeof tool !== "object" ||
              !("mcpServerName" in tool)
            ) {
              continue;
            }
            const name = tool.mcpServerName;
            if (name === undefined) continue;
            if (typeof name !== "string" || !SAFE_SERVER_NAME.test(name)) {
              inventoryObserved = false;
              continue;
            }
            if (!serverNames.has(name) && serverNames.size >= MAX_SERVER_COUNT) {
              inventoryObserved = false;
              continue;
            }
            serverNames.add(name);
          }
        }
      } catch {
        inventoryObserved = false;
      }

      const command = [
        python,
        helperPath(),
        "--json",
        "--probe",
        "--harness",
        "omp",
        "--timeout-seconds",
        "20",
      ];
      if (inventoryObserved) command.push("--inventory-observed");
      for (const name of [...serverNames].sort()) {
        command.push("--observed-server", name);
      }

      const child = Bun.spawn({
        cmd: command,
        stdin: "ignore",
        stdout: "pipe",
        stderr: "ignore",
        env: process.env,
      });
      let timedOut = false;
      const timeout = setTimeout(() => {
        timedOut = true;
        try {
          child.kill(9);
        } catch {
          // The helper may have exited between the timer firing and kill().
        }
      }, OUTER_TIMEOUT_MS);
      const outputPromise = readBounded(child.stdout, () => {
        try {
          child.kill(9);
        } catch {
          // A closed child needs no further cleanup.
        }
      });
      const [exitCode, output] = await Promise.all([
        child.exited,
        outputPromise,
      ]).finally(() => clearTimeout(timeout));

      if (timedOut) {
        notify("outer_timeout");
        return;
      }
      const report = output ? parseReport(output) : undefined;
      if (!report) {
        notify("invalid_result");
        return;
      }
      if (exitCode === 0 && report.status === "ok") return;
      if (exitCode === 1 && report.status === "degraded") {
        notify(degradedReasons(report));
        return;
      }
      notify("invalid_result");
    } catch {
      notify("unavailable");
    }
  });
}
