// Live verification against a deployed mcp-switchboard. Two clients, real-time round-trip.
// Usage: SWITCHBOARD_URL=http://192.168.7.50:3108/mcp SWITCHBOARD_MCP_TOKEN=... node test/live.mjs
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";

const URL_ = process.env.SWITCHBOARD_URL ?? "http://192.168.7.50:3108/mcp";
const TOKEN = process.env.SWITCHBOARD_MCP_TOKEN;
if (!TOKEN) { console.error("Set SWITCHBOARD_MCP_TOKEN"); process.exit(1); }

let failed = false;
const assert = (c, m) => { if (!c) { failed = true; console.error("  ✗ " + m); } else console.log("  ✓ " + m); };
const mk = async (name) => {
  const t = new StreamableHTTPClientTransport(new URL(URL_), { requestInit: { headers: { Authorization: `Bearer ${TOKEN}` } } });
  const c = new Client({ name, version: "0" });
  await c.connect(t);
  return c;
};
const call = (c, n, a = {}) => c.callTool({ name: n, arguments: a }).then((r) => JSON.parse(r.content[0].text));

try {
  console.log("target:", URL_);
  const recv = await mk("live-receiver");
  const send = await mk("live-sender");
  await call(recv, "register_agent", { agent_id: "live-receiver", name: "Live Receiver" });
  await call(send, "register_agent", { agent_id: "live-sender", name: "Live Sender" });

  const stamp = Date.now();
  const waitP = call(recv, "wait_for_message", { agent_id: "live-receiver", timeout_seconds: 10 });
  await new Promise((r) => setTimeout(r, 200));
  await call(send, "send_message", { from: "live-sender", to: "live-receiver", content: `live-ping ${stamp}` });
  const got = await waitP;
  const latency = Date.now() - stamp;
  assert(!got.timed_out && got.messages[0]?.content === `live-ping ${stamp}`, "live message delivered via long-poll");
  assert(latency < 1500, `round-trip over the network in <1.5s (was ${latency}ms)`);

  await call(send, "set_status", { agent_id: "live-sender", activity: "verifying deploy" });
  const act = await call(recv, "get_activity", {});
  assert(act.agents.some((a) => a.id === "live-sender" && a.online), "presence + activity snapshot live");

  await recv.close();
  await send.close();
} catch (e) {
  failed = true;
  console.error("live test threw:", e);
}
console.log(failed ? "\nLIVE: FAIL" : "\nLIVE: PASS");
process.exit(failed ? 1 : 0);
