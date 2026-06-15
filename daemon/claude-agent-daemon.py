#!/usr/bin/env python3
"""
Switchboard headless responder daemon.

Registers this host as an agent on the switchboard, polls for inbound messages,
and answers each one by piping it to `claude --print` (non-interactive). Lets a
CLOSED Claude session still respond to the bus — the wake-when-asleep path.

Config is shared with the Claude Code hooks: it reads ~/.switchboard/config.json
  { "base": "http://host:3108", "token": "...", "agent_id": "billy",
    "name": "Billy" (optional) }
Environment variables override the file (handy for systemd units):
  SWITCHBOARD_BASE, SWITCHBOARD_MCP_TOKEN, SWITCHBOARD_AGENT_ID,
  SWITCHBOARD_AGENT_NAME, CLAUDE_BIN

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

POLL_INTERVAL = 3        # seconds between get_messages polls
HEARTBEAT_INTERVAL = 30  # seconds between heartbeats

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

    return {
        "base": base.rstrip("/"),
        "url": base.rstrip("/") + "/mcp",
        "token": token,
        "agent_id": agent_id,
        "name": name,
        "claude_bin": os.environ.get("CLAUDE_BIN", os.path.expanduser("~/.local/bin/claude")),
    }


CFG = load_config()


def mcp_call(method: str, params: dict) -> dict:
    """Send a single JSON-RPC call to the switchboard and return the result."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CFG['token']}",
        "Accept": "application/json, text/event-stream",
    }
    resp = requests.post(CFG["url"], json=payload, headers=headers, timeout=10)
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


def tool_call(name: str, arguments: dict) -> dict:
    return mcp_call("tools/call", {"name": name, "arguments": arguments})


def register():
    result = tool_call("register_agent", {"agent_id": CFG["agent_id"], "name": CFG["name"]})
    log.info("Registered: %s", result)


def heartbeat():
    tool_call("heartbeat", {"agent_id": CFG["agent_id"]})


def get_messages(cursor: Optional[str]) -> tuple[list, Optional[str]]:
    args: dict = {"agent_id": CFG["agent_id"], "limit": 10}
    if cursor:
        args["cursor"] = cursor
    result = tool_call("get_messages", args)
    return result.get("messages", []), result.get("cursor")


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
    log.info("Message from %s (id=%s): %s", sender, msg_id, content[:120])

    try:
        result = subprocess.run(
            [CFG["claude_bin"], "--print", "--no-session-persistence", "--bare", content],
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
    register()

    cursor: Optional[str] = None
    last_heartbeat = time.monotonic()

    # Prime cursor so we don't replay old messages on startup
    _, cursor = get_messages(cursor)
    log.info("Ready. Polling for messages every %ds.", POLL_INTERVAL)

    while True:
        now = time.monotonic()

        # Heartbeat
        if now - last_heartbeat >= HEARTBEAT_INTERVAL:
            try:
                heartbeat()
                last_heartbeat = now
            except Exception as exc:  # noqa: BLE001
                log.warning("Heartbeat failed: %s", exc)

        # Poll for messages
        try:
            messages, new_cursor = get_messages(cursor)
            if new_cursor:
                cursor = new_cursor
            for msg in messages:
                try:
                    process_message(msg)
                except Exception as exc:  # noqa: BLE001
                    log.error("Failed to process message %s: %s", msg.get("id"), exc)
        except Exception as exc:  # noqa: BLE001
            log.warning("Poll failed: %s", exc)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
