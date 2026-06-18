#!/usr/bin/env python3
"""
Switchboard headless responder daemon.

Registers this host as an agent on the switchboard, waits for inbound messages
via long-poll (sub-second delivery), and answers each one by piping it to
`claude --print` (non-interactive). Lets a CLOSED Claude session still respond
to the bus — the wake-when-asleep path.

Config is shared with the Claude Code hooks: it reads ~/.switchboard/config.json
  { "base": "http://host:3108", "token": "...", "agent_id": "billy",
    "name": "Billy" (optional), "allowlist": "Claude,Fred" (required to respond) }
Environment variables override the file (handy for systemd units):
  SWITCHBOARD_BASE, SWITCHBOARD_MCP_TOKEN, SWITCHBOARD_AGENT_ID,
  SWITCHBOARD_AGENT_NAME, CLAUDE_BIN, SWITCHBOARD_ALLOWED_SENDERS,
  CHANNEL_DISALLOWED_TOOLS, SWITCHBOARD_RATE_MAX, SWITCHBOARD_RATE_WINDOW_MS

SECURITY: this daemon pipes UNTRUSTED bus content into the Claude CLI. It is
fail-closed — with no allowlist it drops every message. Set SWITCHBOARD_ALLOWED_SENDERS
(or config "allowlist") to the agent ids you trust. The tool surface is restricted by
default (CHANNEL_DISALLOWED_TOOLS) so a prompt-injection can't run shell or read secrets.

PREREQUISITE: the Claude CLI on this host must be authenticated, or every reply
bounces "Not logged in · Please run /login". Authenticate once interactively
(`claude` then /login) or set ANTHROPIC_API_KEY in this process's environment.
"""

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import requests

CONFIG_PATH = Path(os.path.expanduser("~/.switchboard/config.json"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("switchboard-daemon")


def load_config() -> dict:
    """Merge ~/.switchboard/config.json with environment overrides."""
    cfg: dict = {}
    try:
        cfg = json.loads(CONFIG_PATH.read_text())
    except FileNotFoundError:
        log.warning("No config at %s — relying on environment only.", CONFIG_PATH)
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not parse %s: %s — relying on environment.", CONFIG_PATH, exc)

    base = os.environ.get("SWITCHBOARD_BASE") or cfg.get("base")
    token = os.environ.get("SWITCHBOARD_MCP_TOKEN") or cfg.get("token")
    agent_id = os.environ.get("SWITCHBOARD_AGENT_ID") or cfg.get("agent_id")
    name = os.environ.get("SWITCHBOARD_AGENT_NAME") or cfg.get("name") or agent_id

    missing = [k for k, v in {"base": base, "token": token, "agent_id": agent_id}.items() if not v]
    if missing:
        log.error("Missing required config: %s. Set them in %s or via env.", ", ".join(missing), CONFIG_PATH)
        sys.exit(1)

    # Sender allowlist (fail-closed): the daemon pipes UNTRUSTED bus content into an LLM, so
    # only senders on this list are processed. Empty => drop everything (set it deliberately).
    # Accepts a comma-string (env / config "allowlist") or a JSON array in config.
    raw_allow = os.environ.get("SWITCHBOARD_ALLOWED_SENDERS")
    if raw_allow is None:
        raw_allow = cfg.get("allowlist", "")
    if isinstance(raw_allow, list):
        allowlist = {str(s).strip() for s in raw_allow if str(s).strip()}
    else:
        allowlist = {s.strip() for s in str(raw_allow).split(",") if s.strip()}

    # Tool restriction passed to `claude --print` so a successful prompt-injection can't run
    # shell, mutate/read files, or exfiltrate over the network. Empty string disables it.
    disallowed = os.environ.get(
        "CHANNEL_DISALLOWED_TOOLS",
        "Bash Edit Write MultiEdit NotebookEdit Read Glob Grep WebFetch WebSearch Task",
    ).split()

    return {
        "base": base.rstrip("/"),
        "url": base.rstrip("/") + "/mcp",
        "token": token,
        "agent_id": agent_id,
        "name": name,
        "claude_bin": os.environ.get("CLAUDE_BIN", os.path.expanduser("~/.local/bin/claude")),
        "allowlist": allowlist,
        "disallowed_tools": disallowed,
        "rate_max": int(os.environ.get("SWITCHBOARD_RATE_MAX", "20")),
        "rate_window_sec": float(os.environ.get("SWITCHBOARD_RATE_WINDOW_MS", "60000")) / 1000.0,
    }


CFG = load_config()

_rate: dict = {}  # sender -> [timestamps within the window]


def rate_ok(sender: str) -> bool:
    """Per-sender sliding-window rate limit (cost/DoS guard — each message is an LLM call)."""
    now = time.time()
    window = CFG["rate_window_sec"]
    arr = [t for t in _rate.get(sender, []) if now - t < window]
    if len(arr) >= CFG["rate_max"]:
        _rate[sender] = arr
        return False
    arr.append(now)
    _rate[sender] = arr
    return True


def mcp_call(method: str, params: dict, http_timeout: int = 10) -> dict:
    """Send a single JSON-RPC call to the switchboard and return the result."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CFG['token']}",
        "Accept": "application/json, text/event-stream",
    }
    resp = requests.post(CFG["url"], json=payload, headers=headers, timeout=http_timeout)
    resp.raise_for_status()

    # Response is SSE: "event: message\ndata: {...}\n\n"
    text = resp.text.strip()
    for line in text.splitlines():
        if line.startswith("data:"):
            data = json.loads(line[len("data:"):].strip())
            if "error" in data:
                raise RuntimeError(f"MCP error: {data['error']}")
            result = data.get("result", {})
            # tools/call wraps result in content[0].text
            if "content" in result and result["content"]:
                return json.loads(result["content"][0]["text"])
            return result
    raise RuntimeError(f"Unexpected MCP response: {text!r}")


def tool_call(name: str, arguments: dict, http_timeout: int = 10) -> dict:
    return mcp_call("tools/call", {"name": name, "arguments": arguments}, http_timeout=http_timeout)


def register():
    result = tool_call("register_agent", {"agent_id": CFG["agent_id"], "name": CFG["name"]})
    log.info("Registered: %s", result)


def wait_for_message() -> list[dict]:
    """Block up to 25s for a message. Returns immediately when one arrives."""
    result = tool_call(
        "wait_for_message",
        {"agent_id": CFG["agent_id"], "timeout_seconds": 25},
        http_timeout=30,  # must exceed the MCP-level timeout
    )
    return result.get("messages", [])


def send_reply(to: str, content: str, thread_id: Optional[str] = None,
               reply_to: Optional[int] = None):
    args: dict = {"from": CFG["agent_id"], "to": to, "content": content, "type": "result"}
    if thread_id:
        args["thread_id"] = thread_id
    if reply_to is not None:
        args["reply_to"] = reply_to
    tool_call("send_message", args)


def process_message(msg: dict):
    content = msg.get("content", "")
    sender = msg.get("from", "unknown")
    msg_id = msg.get("id")
    thread_id = msg.get("thread_id")

    # Fail-closed allowlist: only process bus content from explicitly trusted senders.
    if sender not in CFG["allowlist"]:
        if not CFG["allowlist"]:
            log.warning("Dropped message %s: no allowlist configured (fail-closed). "
                        "Set SWITCHBOARD_ALLOWED_SENDERS to enable responses.", msg_id)
        else:
            log.warning("Dropped message %s from non-allowlisted sender %r", msg_id, sender)
        return
    if not rate_ok(sender):
        log.warning("Rate-limited message %s from %r (>%s per %ss)",
                    msg_id, sender, CFG["rate_max"], CFG["rate_window_sec"])
        return

    log.info("Message from %s (id=%s): %s", sender, msg_id, content[:120])

    tool_args = ["--disallowedTools", *CFG["disallowed_tools"]] if CFG["disallowed_tools"] else []
    try:
        # `--` terminates option parsing so attacker-controlled `content` starting with `-`
        # is treated as the prompt, never as CLI flags (e.g. --mcp-config / --dangerously-*).
        result = subprocess.run(
            [CFG["claude_bin"], "--print", "--no-session-persistence", *tool_args, "--", content],
            capture_output=True,
            text=True,
            timeout=300,
            env={**os.environ, "HOME": os.path.expanduser("~")},
        )
        reply = result.stdout.strip() or result.stderr.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        reply = "Error: request timed out after 5 minutes."
    except Exception as exc:  # noqa: BLE001
        reply = f"Error: {exc}"

    send_reply(sender, reply, thread_id=thread_id, reply_to=msg_id)
    log.info("Replied to %s", sender)


def main():
    log.info("Switchboard daemon starting (agent_id=%s, base=%s)", CFG["agent_id"], CFG["base"])
    if CFG["allowlist"]:
        log.info("Allowlisted senders: %s", ", ".join(sorted(CFG["allowlist"])))
    else:
        log.warning("No allowlist configured — fail-closed, ALL messages will be dropped. "
                    "Set SWITCHBOARD_ALLOWED_SENDERS to enable responses.")
    register()
    log.info("Ready. Listening for messages (long-poll, sub-second delivery).")

    while True:
        try:
            messages = wait_for_message()
            for msg in messages:
                try:
                    process_message(msg)
                except Exception as exc:  # noqa: BLE001
                    log.error("Failed to process message %s: %s", msg.get("id"), exc)
        except Exception as exc:  # noqa: BLE001
            log.warning("Poll error: %s — retrying in 5s", exc)
            time.sleep(5)


if __name__ == "__main__":
    main()
