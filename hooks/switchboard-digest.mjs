// Claude Code SessionStart/UserPromptSubmit hook → injects a digest of OTHER agents'
// recent activity into context, so this agent stays aware without the user relaying.
// Robust: fast timeout, silent no-op on any failure. Reads ~/.switchboard/config.json.
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const quit = () => process.exit(0);
let cfg;
try {
  cfg = JSON.parse(readFileSync(join(homedir(), ".switchboard", "config.json"), "utf8"));
} catch {
  quit();
}

let input = "";
process.stdin.on("data", (c) => (input += c));
process.stdin.on("end", async () => {
  let payload = {};
  try { payload = JSON.parse(input); } catch {}
  const event = payload.hook_event_name || "UserPromptSubmit";
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 1500);
  try {
    const r = await fetch(`${cfg.base}/activity?limit=20`, {
      headers: { Authorization: `Bearer ${cfg.token}` },
      signal: ctrl.signal,
    });
    const data = await r.json();
    const others = (data.agents || []).filter((a) => a.id !== cfg.agent_id);
    const online = others.filter((a) => a.online);
    if (!others.length) quit();
    const lines = others.map((a) => {
      const act = a.last_activity ? `: ${a.last_activity}` : "";
      return `  - ${a.id} (${a.online ? "online" : "offline"})${act}`;
    });
    const recent = (data.feed || [])
      .filter((m) => m.from !== cfg.agent_id)
      .slice(-8)
      .map((m) => { try { return `  - ${m.from}: ${JSON.parse(m.content).activity}`; } catch { return `  - ${m.from}: ${m.content}`; } });
    const ctx =
      `Agent bus status (${online.length}/${others.length} other agents online):\n` +
      lines.join("\n") +
      (recent.length ? `\nRecent activity:\n${recent.join("\n")}` : "");
    process.stdout.write(JSON.stringify({ hookSpecificOutput: { hookEventName: event, additionalContext: ctx } }));
  } catch {} finally {
    clearTimeout(timer);
    quit();
  }
});
