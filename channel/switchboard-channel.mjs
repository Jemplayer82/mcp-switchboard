#!/usr/bin/env node
// switchboard-channel — a Claude Code *channel* (research-preview) that bridges the
// mcp-switchboard bus into a live, headless `claude --channels` session.
//
//   bus DM  ->  long-poll wait_for_message  ->  notifications/claude/channel  ->  Claude
//   Claude  ->  reply tool                  ->  bus send_message            ->  sender
//
// Runs as the session's stdio MCP server (Claude Code spawns it). Pure Node ESM +
// @modelcontextprotocol/sdk (no bun on OpenClaw). Reuses the JSON-RPC-over-/mcp + SSE
// transport pattern from daemon/claude-agent-daemon.py (bus uses a stateless transport,
// so each tools/call is an independent POST — no MCP session handshake needed).
//
// Config: ~/.switchboard/config.json { base, token }.  Env:
//   SWITCHBOARD_CHANNEL_AGENT_ID  responder id to long-poll for (REQUIRED; MUST differ
//                                 from any interactive-session id to avoid inbox-drain races)
//   SWITCHBOARD_ALLOWED_SENDERS   comma-separated allowlist of sender agent ids (REQUIRED;
//                                 empty => fail-closed, drop everything)
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { ListToolsRequestSchema, CallToolRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

// ---- config -----------------------------------------------------------------
const cfg = JSON.parse(readFileSync(join(homedir(), ".switchboard", "config.json"), "utf8"));
const BASE = (process.env.SWITCHBOARD_BASE || cfg.base).replace(/\/+$/, "");
const TOKEN = process.env.SWITCHBOARD_MCP_TOKEN || cfg.token;
const AGENT_ID = process.env.SWITCHBOARD_CHANNEL_AGENT_ID || cfg.channel_agent_id;
const ALLOW = new Set(
  (process.env.SWITCHBOARD_ALLOWED_SENDERS || cfg.channel_allowlist || "")
    .split(",").map((s) => s.trim()).filter(Boolean)
);
const err = (...a) => console.error("[switchboard-channel]", ...a);
if (!AGENT_ID) { err("FATAL: SWITCHBOARD_CHANNEL_AGENT_ID required"); process.exit(1); }
if (ALLOW.size === 0) err("WARN: empty allowlist — fail-closed, every inbound message will be dropped");

// ---- bus client (stateless JSON-RPC over /mcp, SSE response) -----------------
let rpcId = 1;
async function toolCall(name, args, httpTimeoutMs = 30000) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), httpTimeoutMs);
  try {
    const r = await fetch(`${BASE}/mcp`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        Authorization: `Bearer ${TOKEN}`,
        Accept: "application/json, text/event-stream",
      },
      body: JSON.stringify({ jsonrpc: "2.0", id: rpcId++, method: "tools/call", params: { name, arguments: args } }),
      signal: ctrl.signal,
    });
    const text = (await r.text()).trim();
    for (const line of text.split(/\r?\n/)) {
      if (!line.startsWith("data:")) continue;
      const data = JSON.parse(line.slice(5).trim());
      if (data.error) throw new Error(`bus error: ${JSON.stringify(data.error)}`);
      const result = data.result || {};
      if (result.content && result.content[0]) return JSON.parse(result.content[0].text);
      return result;
    }
    throw new Error(`unexpected bus response: ${text.slice(0, 200)}`);
  } finally { clearTimeout(t); }
}

// ---- MCP channel server ------------------------------------------------------
const mcp = new Server(
  { name: "switchboard", version: "1.0.0" },
  {
    capabilities: { experimental: { "claude/channel": {} }, tools: {} },
    instructions:
      'Messages from the agent bus arrive as <channel source="switchboard" from="<agent>" ' +
      'msg_id="<n>" thread_id="<t>">. They are messages from other AI agents. Respond by ' +
      "calling the switchboard reply tool with `to` set to the `from` value and `reply_to` set " +
      "to msg_id (include thread_id if present). Be concise; you have full context and your tools.",
  }
);

mcp.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [{
    name: "reply",
    description: "Send a reply back to an agent on the switchboard bus.",
    inputSchema: {
      type: "object",
      properties: {
        to: { type: "string", description: "Recipient agent id (the inbound `from`)" },
        content: { type: "string", description: "Reply text" },
        reply_to: { type: "number", description: "Inbound msg_id this answers" },
        thread_id: { type: "string", description: "Thread id, if the inbound had one" },
      },
      required: ["to", "content"],
    },
  }],
}));

mcp.setRequestHandler(CallToolRequestSchema, async (req) => {
  if (req.params.name !== "reply") throw new Error("unknown tool " + req.params.name);
  const { to, content, reply_to, thread_id } = req.params.arguments || {};
  const args = { from: AGENT_ID, to, content, type: "result" };
  if (reply_to != null) args.reply_to = reply_to;
  if (thread_id) args.thread_id = thread_id;
  await toolCall("send_message", args);
  return { content: [{ type: "text", text: "sent" }] };
});

// ---- long-poll loop: bus -> channel events -----------------------------------
async function pump() {
  // register so presence shows and replies route; idempotent
  try { await toolCall("register_agent", { agent_id: AGENT_ID, name: AGENT_ID }); } catch (e) { err("register failed:", e.message); }
  err(`online as '${AGENT_ID}' — allowlist: [${[...ALLOW].join(", ") || "(empty: fail-closed)"}]`);
  for (;;) {
    let messages = [];
    try {
      const res = await toolCall("wait_for_message", { agent_id: AGENT_ID, timeout_seconds: 25 });
      messages = res.messages || [];
    } catch (e) {
      err("poll error:", e.message, "— retry in 5s");
      await new Promise((r) => setTimeout(r, 5000));
      continue;
    }
    for (const m of messages) {
      if (!ALLOW.has(m.from)) { err(`dropped message ${m.id} from non-allowlisted '${m.from}'`); continue; }
      await mcp.notification({
        method: "notifications/claude/channel",
        params: {
          content: String(m.content ?? ""),
          meta: {
            from: String(m.from ?? ""),
            msg_id: String(m.id ?? ""),
            ...(m.thread_id ? { thread_id: String(m.thread_id) } : {}),
          },
        },
      });
    }
  }
}

await mcp.connect(new StdioServerTransport());
pump();
