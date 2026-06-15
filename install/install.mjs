#!/usr/bin/env node
// install/install.mjs — cross-platform switchboard agent installer.
//
// All the real install logic lives here; install.sh / install.ps1 are thin
// wrappers that fetch this file and run it with `node`. Node is guaranteed
// present because Claude Code requires it.
//
// What it does (every step idempotent, every overwrite backed up first):
//   1. write/merge  ~/.switchboard/config.json   (shared by hooks + daemon)
//   2. download     switchboard-{publish,digest}.mjs  ->  ~/.claude/hooks/
//   3. merge        ~/.claude/settings.json       (4 hook events)
//   4. merge        ~/.claude.json mcpServers.switchboard (or print fallback)
//   5. --with-daemon (Linux): drop the responder + systemd user unit, enable it
//
// Inputs (flag OR env; flags win):
//   --agent-id   SWITCHBOARD_AGENT_ID     (required)
//   --token      SWITCHBOARD_MCP_TOKEN    (required)
//   --base       SWITCHBOARD_BASE         (default http://192.168.7.50:3108)
//   --name       SWITCHBOARD_AGENT_NAME   (default: agent-id)
//   --with-daemon   --dry-run

import { readFileSync, writeFileSync, mkdirSync, copyFileSync, existsSync } from "node:fs";
import { homedir, platform } from "node:os";
import { join } from "node:path";
import { execSync } from "node:child_process";

const DEFAULT_BASE = "http://192.168.7.50:3108";

// ---- args ---------------------------------------------------------------
function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith("--")) continue;
    const key = a.slice(2);
    if (key === "with-daemon" || key === "dry-run") out[key] = true;
    else out[key] = argv[++i];
  }
  return out;
}
const args = parseArgs(process.argv.slice(2));

const agentId = args["agent-id"] || process.env.SWITCHBOARD_AGENT_ID;
const token = args["token"] || process.env.SWITCHBOARD_MCP_TOKEN;
const base = (args["base"] || process.env.SWITCHBOARD_BASE || DEFAULT_BASE).replace(/\/+$/, "");
const name = args["name"] || process.env.SWITCHBOARD_AGENT_NAME || agentId;
const withDaemon = !!args["with-daemon"];
const dryRun = !!args["dry-run"];

const missing = [];
if (!agentId) missing.push("--agent-id (or SWITCHBOARD_AGENT_ID)");
if (!token) missing.push("--token (or SWITCHBOARD_MCP_TOKEN)");
if (missing.length) {
  console.error("✗ Missing required input:\n  " + missing.join("\n  "));
  console.error("\nUsage: node install.mjs --agent-id <id> --token <token> [--base <url>] [--with-daemon] [--dry-run]");
  process.exit(1);
}

const home = homedir();
const claudeDir = join(home, ".claude");
const hooksDir = join(claudeDir, "hooks");
const sbDir = join(home, ".switchboard");
const isWin = platform() === "win32";

const log = (...m) => console.log(...m);
const tag = dryRun ? "[dry-run] would" : "→";

// Node accepts forward slashes on every platform; keeps settings.json clean.
const fwd = (p) => p.replace(/\\/g, "/");

function backup(path) {
  if (!existsSync(path)) return;
  const bak = `${path}.bak.${Date.now()}`;
  if (!dryRun) copyFileSync(path, bak);
  log(`  ${tag} back up ${path} -> ${bak}`);
}

function ensureDir(d) {
  if (!dryRun) mkdirSync(d, { recursive: true });
}

function readJson(path) {
  try { return JSON.parse(readFileSync(path, "utf8")); } catch { return null; }
}

function writeJson(path, obj) {
  if (!dryRun) writeFileSync(path, JSON.stringify(obj, null, 2) + "\n");
}

async function download(url, dest) {
  if (dryRun) { log(`  ${tag} download ${url} -> ${dest}`); return; }
  const r = await fetch(url);
  if (!r.ok) throw new Error(`GET ${url} -> ${r.status}`);
  writeFileSync(dest, await r.text());
  log(`  → downloaded ${url} -> ${dest}`);
}

// ---- 1. config.json -----------------------------------------------------
function writeConfig() {
  log("\n[1/5] switchboard config");
  ensureDir(sbDir);
  const path = join(sbDir, "config.json");
  const existing = readJson(path) || {};
  backup(path);
  const config = {
    base,
    token,
    agent_id: agentId,
    name,
    // preserve any inbound prefs the operator already set
    inbound: { deliver: true, block_on_stop: true, ...(existing.inbound ?? {}) },
  };
  writeJson(path, config);
  log(`  ${tag} write ${path} (agent_id=${agentId})`);
}

// ---- 2. hooks -----------------------------------------------------------
async function installHooks() {
  log("\n[2/5] hook scripts");
  ensureDir(hooksDir);
  for (const f of ["switchboard-publish.mjs", "switchboard-digest.mjs"]) {
    await download(`${base}/hooks/${f}`, join(hooksDir, f));
  }
}

// ---- 3. settings.json hook wiring --------------------------------------
function wireSettings() {
  log("\n[3/5] settings.json hook wiring");
  const path = join(claudeDir, "settings.json");
  const cfg = readJson(path) || {};
  backup(path);

  const pub = `node "${fwd(join(hooksDir, "switchboard-publish.mjs"))}"`;
  const dig = `node "${fwd(join(hooksDir, "switchboard-digest.mjs"))}"`;
  const hooks = (cfg.hooks ??= {});

  const has = (list, cmd) =>
    (list || []).some((g) => (g.hooks || []).some((h) => h.command === cmd));

  const add = (event, cmd, matcher) => {
    const list = (hooks[event] ??= []);
    if (has(list, cmd)) { log(`  • ${event} already wired`); return; }
    const group = { hooks: [{ type: "command", command: cmd }] };
    if (matcher !== undefined) group.matcher = matcher;
    list.push(group);
    log(`  ${tag} add ${event} -> ${cmd.includes("publish") ? "publish" : "digest"}`);
  };

  add("SessionStart", dig);
  add("UserPromptSubmit", dig);
  add("PostToolUse", pub, "");
  add("Stop", pub);

  writeJson(path, cfg);
}

// ---- 4. MCP server entry -----------------------------------------------
function wireMcp() {
  log("\n[4/5] MCP server entry");
  const path = join(home, ".claude.json");
  const entry = { type: "http", url: `${base}/mcp`, headers: { Authorization: `Bearer ${token}` } };
  if (existsSync(path)) {
    const cfg = readJson(path);
    if (cfg === null) {
      // exists but unparseable — never risk clobbering the live config; print the command.
      log("  ! ~/.claude.json exists but couldn't be parsed — add the server manually:");
      log(`    claude mcp add-json switchboard '${JSON.stringify(entry)}'`);
      return;
    }
    if (cfg.mcpServers?.switchboard) { log("  • switchboard MCP entry already present"); return; }
    backup(path);
    (cfg.mcpServers ??= {}).switchboard = entry;
    writeJson(path, cfg);
    log(`  ${tag} add mcpServers.switchboard -> ${base}/mcp`);
  } else {
    // missing — safe to create fresh.
    writeJson(path, { mcpServers: { switchboard: entry } });
    log(`  ${tag} create ~/.claude.json with mcpServers.switchboard -> ${base}/mcp`);
  }
}

// ---- 5. daemon (Linux) --------------------------------------------------
async function installDaemon() {
  if (!withDaemon) return;
  log("\n[5/5] headless responder daemon");
  if (isWin) { log("  ! --with-daemon is Linux-only (systemd user service); skipping."); return; }

  const daemonDest = join(claudeDir, "claude-agent-daemon.py");
  await download(`${base}/install/daemon/claude-agent-daemon.py`, daemonDest);

  const unitDir = join(home, ".config", "systemd", "user");
  ensureDir(unitDir);
  await download(`${base}/install/daemon/claude-code-agent.service`, join(unitDir, "claude-code-agent.service"));

  if (dryRun) {
    log("  [dry-run] would run: systemctl --user daemon-reload && systemctl --user enable --now claude-code-agent");
  } else {
    try {
      execSync("systemctl --user daemon-reload", { stdio: "inherit" });
      execSync("systemctl --user enable --now claude-code-agent", { stdio: "inherit" });
      log("  → daemon enabled and started");
    } catch {
      log("  ! could not start via systemd — start manually: python3 ~/.claude/claude-agent-daemon.py");
    }
  }
  log("  WARNING: the daemon needs the Claude CLI authenticated on this host,");
  log("           or every reply bounces 'Not logged in'. Run `claude` then /login,");
  log("           or set ANTHROPIC_API_KEY in the systemd unit.");
}

// ---- run ----------------------------------------------------------------
(async () => {
  log(`Switchboard agent install${dryRun ? " (dry-run)" : ""}`);
  log(`  agent_id : ${agentId}`);
  log(`  base     : ${base}`);
  log(`  home     : ${home}`);
  writeConfig();
  await installHooks();
  wireSettings();
  wireMcp();
  await installDaemon();
  log(`\n✓ Done.${dryRun ? " (nothing was written — dry-run)" : ""}`);
  if (!dryRun) log("  Restart your Claude Code session (or start a new one) to load the hooks.");
})().catch((e) => { console.error("\n✗ Install failed:", e.message); process.exit(1); });
