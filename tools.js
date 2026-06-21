// tools.js — defines the MCP tool surface for the switchboard.
//
// Every tool an agent can call (send a message, long-poll for one, list who's
// online, etc.) is registered here. Each one is a thin wrapper that validates its
// arguments with zod and forwards to a method on the shared `bus` singleton — the
// bus holds all the real logic and state (SQLite + the in-process event emitter).
// A tool's `description` string is the contract the calling agent actually reads,
// so it's written for that audience, not for us.
import { z } from "zod";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const ROOT = dirname(fileURLToPath(import.meta.url));
// Fallback base URL the `bootstrap` tool puts in the install one-liner when the
// caller doesn't pass one. Set SWITCHBOARD_PUBLIC_BASE on the server so a
// self-hosted instance advertises its own URL instead of localhost.
const DEFAULT_BASE = (process.env.SWITCHBOARD_PUBLIC_BASE || "http://localhost:3107").replace(/\/+$/, "");

// MCP tool results are a `content` array; these wrap our plain return values in
// that shape. `ok` = success (JSON-stringified payload), `fail` = error result.
const ok = (obj) => ({ content: [{ type: "text", text: JSON.stringify(obj) }] });
const fail = (msg) => ({ content: [{ type: "text", text: String(msg) }], isError: true });

// Read a file shipped inside the image (used by `bootstrap` to return the hook
// source). Returns null if it's missing rather than throwing.
function readAsset(rel) {
  try { return readFileSync(join(ROOT, rel), "utf8"); } catch { return null; }
}

export function registerTools(server, bus) {
  // ---- registration & roster ----
  server.registerTool(
    "register_agent",
    {
      description:
        "Register/refresh this agent on the bus (idempotent). Call on startup. `wake_url` (daemons only) is a harness HTTP endpoint the bus POSTs to wake an idle agent — do NOT set it for interactive Claude Code.",
      inputSchema: {
        agent_id: z.string().describe("Stable id, e.g. 'claude-code' or 'hermes'"),
        name: z.string(),
        capabilities: z.array(z.string()).optional(),
        wake_url: z.string().url().optional().describe("Daemon trigger endpoint; the bus POSTs here to wake the agent"),
        wake_secret: z.string().optional(),
      },
    },
    async (a) => ok(bus.registerAgent(a))
  );

  server.registerTool(
    "list_agents",
    { description: "List all known agents with presence (online if seen < 60s ago) and current activity.", inputSchema: {} },
    async () => ok({ agents: bus.listAgents() })
  );

  // ---- channels ----
  server.registerTool(
    "create_channel",
    { description: "Create a channel (idempotent).", inputSchema: { channel_id: z.string(), name: z.string().optional() } },
    async (a) => ok(bus.createChannel(a))
  );

  server.registerTool(
    "list_channels",
    { description: "List channels with member counts.", inputSchema: {} },
    async () => ok({ channels: bus.listChannels() })
  );

  server.registerTool(
    "join_channel",
    {
      description: "Join a channel. Cursor starts at the current head (no history flood).",
      inputSchema: { agent_id: z.string(), channel_id: z.string() },
    },
    async (a) => ok(bus.joinChannel(a))
  );

  // ---- messaging (send / receive / acknowledge) ----
  server.registerTool(
    "send_message",
    {
      description:
        "Send a direct message (`to`) or channel broadcast (`channel_id`) — exactly one. `type` (chat/instruction/result/ack), `thread_id`, and `reply_to` support structured coordination. Wakes any waiting recipient instantly.",
      inputSchema: {
        from: z.string(),
        to: z.string().optional().describe("Recipient agent id (direct message)"),
        channel_id: z.string().optional().describe("Channel id (broadcast)"),
        content: z.string(),
        type: z.string().optional(),
        thread_id: z.string().optional(),
        reply_to: z.number().optional(),
      },
    },
    async (a) => {
      if ((a.to == null) === (a.channel_id == null)) return fail("Provide exactly one of `to` or `channel_id`.");
      return ok({ ok: true, message_id: bus.send(a) });
    }
  );

  server.registerTool(
    "wait_for_message",
    {
      description:
        "Long-poll: blocks up to `timeout_seconds` (max 25, default 20) and returns the instant a message arrives, or `timed_out:true`. Drains the inbox. Loop this for real-time receipt.",
      inputSchema: {
        agent_id: z.string(),
        timeout_seconds: z.number().min(1).max(25).default(20),
      },
    },
    async (a, extra) => {
      const ms = Math.min(a.timeout_seconds ?? 20, 25) * 1000;
      const messages = await bus.waitForMessage(a.agent_id, ms, extra?.signal);
      return ok({ messages, timed_out: messages.length === 0 });
    }
  );

  server.registerTool(
    "get_messages",
    {
      description:
        "Non-blocking read. Default drains this agent's unread inbox. Pass `channel_id`/`since_id` for history (no cursor side-effects), or `peek:true` to read unread without advancing the cursor.",
      inputSchema: {
        agent_id: z.string(),
        channel_id: z.string().optional(),
        since_id: z.number().optional(),
        limit: z.number().max(200).default(50),
        peek: z.boolean().default(false),
        drain: z.boolean().default(true),
      },
    },
    async (a) => ok(bus.getMessages(a.agent_id, a))
  );

  server.registerTool(
    "ack",
    {
      description: "Advance this agent's read cursor up to `up_to_id` (for peek-then-act instruction flows).",
      inputSchema: { agent_id: z.string(), up_to_id: z.number() },
    },
    async (a) => ok(bus.ack(a.agent_id, a.up_to_id))
  );

  // ---- presence & awareness ----
  server.registerTool(
    "heartbeat",
    { description: "Refresh presence between polls; returns currently-online agents.", inputSchema: { agent_id: z.string() } },
    async (a) => ok(bus.heartbeat(a.agent_id))
  );

  server.registerTool(
    "set_status",
    {
      description:
        "Self-report current activity (awareness layer), e.g. activity='editing server.js'. Updates presence and emits a status event other agents see via get_activity.",
      inputSchema: { agent_id: z.string(), activity: z.string(), detail: z.string().optional() },
    },
    async (a) => ok(bus.setStatus(a))
  );

  server.registerTool(
    "get_activity",
    {
      description:
        "Read the cross-agent activity feed plus a snapshot of every agent's current status + online flag. The source for awareness digests.",
      inputSchema: { since_id: z.number().optional(), limit: z.number().max(200).default(50), agent_id: z.string().optional() },
    },
    async (a) => ok(bus.getActivity(a))
  );

  // ---- self-install ----
  // `bootstrap` is how a connected agent wires ITSELF in without an operator running
  // the installer: it returns both a copy-paste one-liner AND the raw files + target
  // paths, so the agent can either shell out or write the files with its own tools.
  server.registerTool(
    "bootstrap",
    {
      description:
        "Self-install kit for wiring THIS agent into the switchboard. Returns the one-line install command for your platform PLUS the full hook file contents, target paths, and settings.json merge — so you can either run the one-liner (via your shell) or write the files yourself. Pass your agent_id; pass base if it differs from the default host. After installing, restart your session so the hooks load.",
      inputSchema: {
        agent_id: z.string().describe("The stable id to register this agent under, e.g. 'billy'"),
        platform: z.enum(["windows", "unix"]).optional().describe("Defaults to unix"),
        base: z.string().optional().describe("Switchboard base URL you connected to (default the LAN host)"),
        token: z.string().optional().describe("Bearer token; omit to get a <TOKEN> placeholder in the command"),
      },
    },
    async ({ agent_id, platform = "unix", base, token }) => {
      const b = (base || DEFAULT_BASE).replace(/\/+$/, "");
      const tok = token || "<SWITCHBOARD_MCP_TOKEN>"; // placeholder if the caller withheld the token
      // Read the hook source straight from the image so the manual path below ships
      // the exact files this server serves (no drift between served + embedded copies).
      const publish = readAsset("hooks/switchboard-publish.mjs");
      const digest = readAsset("hooks/switchboard-digest.mjs");
      if (!publish || !digest) return fail("Hook assets not found in image — rebuild with hooks/ copied in.");

      // Path A — the easy route: one command that fetches and runs the installer.
      const oneLiner =
        platform === "windows"
          ? `$env:SWITCHBOARD_AGENT_ID='${agent_id}'; $env:SWITCHBOARD_MCP_TOKEN='${tok}'; irm ${b}/install.ps1 | iex`
          : `curl -fsSL ${b}/install.sh | sh -s -- --agent-id ${agent_id} --token ${tok}`;

      // The settings.json hook commands (referenced in the manual block below).
      const pub = `node "~/.claude/hooks/switchboard-publish.mjs"`;
      const dig = `node "~/.claude/hooks/switchboard-digest.mjs"`;

      // Path B — `manual`: everything needed to self-install by hand. Four parts:
      //   config        → ~/.switchboard/config.json (base/token/agent_id, shared by hooks + daemon)
      //   hooks         → the two hook scripts' full source + where to write them
      //   settings_merge→ the hook wiring to merge into ~/.claude/settings.json (don't clobber existing)
      //   mcp_entry     → the mcpServers entry that exposes the bus as an MCP server
      return ok({
        agent_id,
        base: b,
        install_command: oneLiner,
        note: "Easiest path: run install_command. To self-install instead, write the files below, then restart your session.",
        manual: {
          config: {
            path: "~/.switchboard/config.json",
            content: { base: b, token: tok, agent_id, name: agent_id, inbound: { deliver: true, block_on_stop: true } },
          },
          hooks: [
            { path: "~/.claude/hooks/switchboard-publish.mjs", content: publish },
            { path: "~/.claude/hooks/switchboard-digest.mjs", content: digest },
          ],
          settings_merge: {
            path: "~/.claude/settings.json",
            hooks: {
              SessionStart: [{ hooks: [{ type: "command", command: dig }] }],
              UserPromptSubmit: [{ hooks: [{ type: "command", command: dig }] }],
              PostToolUse: [{ matcher: "", hooks: [{ type: "command", command: pub }] }],
              Stop: [{ hooks: [{ type: "command", command: pub }] }],
            },
            note: "Merge these into existing event arrays — do not clobber other hooks.",
          },
          mcp_entry: {
            path: "~/.claude.json mcpServers.switchboard",
            content: { type: "http", url: `${b}/mcp`, headers: { Authorization: `Bearer ${tok}` } },
          },
        },
      });
    }
  );
}
