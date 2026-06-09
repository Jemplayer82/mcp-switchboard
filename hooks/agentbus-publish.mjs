// Claude Code PostToolUse/Stop hook → auto-publishes this agent's activity to the bus.
// Fire-and-forget, fast timeout, silent on any failure (never blocks the session).
// Install via settings.json; reads ~/.agentbus/config.json for { base, token, agent_id }.
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const quit = () => process.exit(0);
let cfg;
try {
  cfg = JSON.parse(readFileSync(join(homedir(), ".agentbus", "config.json"), "utf8"));
} catch {
  quit(); // no config → no-op
}

let input = "";
process.stdin.on("data", (c) => (input += c));
process.stdin.on("end", async () => {
  let payload = {};
  try { payload = JSON.parse(input); } catch {}
  const event = payload.hook_event_name || "";
  const tool = payload.tool_name || "";
  let activity, detail;
  if (event === "Stop") {
    activity = "idle (finished turn)";
  } else {
    activity = tool ? `using ${tool}` : "working";
    const fp = payload.tool_input?.file_path || payload.tool_input?.path;
    if (fp) detail = String(fp);
  }
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 1500);
  try {
    await fetch(`${cfg.base}/status`, {
      method: "POST",
      headers: { "content-type": "application/json", Authorization: `Bearer ${cfg.token}` },
      body: JSON.stringify({ agent_id: cfg.agent_id, activity, detail }),
      signal: ctrl.signal,
    });
  } catch {} finally {
    clearTimeout(timer);
    quit();
  }
});
