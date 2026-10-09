#!/usr/bin/env python3
"""Switchboard waker: nudge idle Claude sessions when switchboard mail arrives for them.

Run by switchboard-waker.timer (systemd user unit). Each run:
  1. Reads new bus history once (since_id, no cursor side-effects) and keeps each direct
     message to a mapped agent id as "pending" for that agent (so each message counts once).
  2. Drops pending messages the agent has already read (peek:true, limit 1 gives its first
     unread id), then sends ONE short nudge per agent to the mapped local Claude session
     (coalesced, rate-limited) naming the ids, threads and senders, so the session starts a
     turn and reads its mail with get_messages.

Delivery uses the supported cross-session path: a headless `claude -p` run whose only
tools are SendMessage and ListAgents (no MCP servers, all hooks disabled so it cannot
drain or post to the switchboard). It runs in the target session's permission-mode class
so the message is delivered rather than held for approval. Delivery status is read from
the SendMessage tool result itself, not from the model's summary.

Config:  ~/.config/switchboard-waker/sessions.json  (see waker/README.md); the bus URL and
         token come from ~/.switchboard/config.json (same file the hooks use) by default
State:   ~/.local/state/switchboard-waker/state.json
Log:     journalctl --user -u switchboard-waker
Flags:   --dry-run (no nudges, no state writes), --agent ID (only that mapping)
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()
CONFIG = Path(os.environ.get("SWITCHBOARD_WAKER_CONFIG", HOME / ".config/switchboard-waker/sessions.json"))
STATE_DIR = HOME / ".local/state/switchboard-waker"
STATE = STATE_DIR / "state.json"
HOOK_CONFIG = HOME / ".switchboard/config.json"  # shared with the hooks; supplies base + token
DEFAULTS = {
    "switchboard_url": None,  # default: <base from ~/.switchboard/config.json>/mcp
    "token_env": "SWITCHBOARD_MCP_TOKEN",
    "claude_bin": shutil.which("claude") or "claude",
    "sender_cwd": str(HOME),  # must be a folder Claude Code already trusts
    "sender_model": "haiku",
    "min_interval_min": 10,
    "max_nudges_per_hour": 4,
}
SAFE = re.compile(r"[^A-Za-z0-9._:@#/ -]")


def log(msg: str) -> None:
    print(msg, flush=True)


def clean(value, limit: int = 60) -> str:
    """Bus-supplied strings go into a prompt: keep them short and inert."""
    return SAFE.sub("", str(value or ""))[:limit] or "?"


def load_token(env_name: str, hook_cfg: dict) -> str:
    token = hook_cfg.get("token") or os.environ.get(env_name, "")
    if not token:
        for conf in (HOME / ".config/environment.d").glob("*switchboard*.conf"):
            for line in conf.read_text().splitlines():
                if line.startswith(f"{env_name}="):
                    token = line.split("=", 1)[1].strip().strip('"')
    return token


def bus_call(cfg: dict, token: str, arguments: dict):
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "get_messages", "arguments": arguments}}
    # Token goes via a curl config on stdin so it never shows up in argv / ps.
    proc = subprocess.run(
        ["curl", "-s", "-m", "20", "-K", "-", "-X", "POST", cfg["switchboard_url"],
         "-H", "Content-Type: application/json", "-H", "Accept: application/json, text/event-stream",
         "-d", json.dumps(body)],
        input=f'header = "Authorization: Bearer {token}"\n', capture_output=True, text=True)
    raw = proc.stdout
    data = next((l[5:].strip() for l in raw.splitlines() if l.startswith("data:")), raw.strip())
    try:
        result = json.loads(data).get("result", {})
        return json.loads("".join(c.get("text", "") for c in result.get("content", [])))
    except (ValueError, AttributeError):
        raise RuntimeError(f"switchboard call failed (curl rc={proc.returncode}): {data[:200]}")


def history(cfg: dict, token: str, since_id: int) -> list[dict]:
    """Bus-wide history after since_id. History reads never move anyone's read cursor."""
    return bus_call(cfg, token, {"agent_id": "switchboard-waker", "since_id": since_id, "limit": 200})["messages"]


def first_unread(cfg: dict, token: str, agent_id: str) -> int | None:
    """Lowest unread id for agent_id (peek, cursor untouched); None = inbox fully read."""
    msgs = bus_call(cfg, token, {"agent_id": agent_id, "peek": True, "limit": 1})["messages"]
    return msgs[0]["id"] if msgs else None


def bus_head(cfg: dict, token: str) -> int:
    lo, hi = 0, 1
    while history(cfg, token, hi):
        lo, hi = hi, hi * 2
    while hi - lo > 1:  # invariant: messages exist after lo, none after hi
        mid = (lo + hi) // 2
        lo, hi = (mid, hi) if history(cfg, token, mid) else (lo, mid)
    return hi


def local_sessions(cfg: dict) -> list[dict]:
    out = subprocess.run([cfg["claude_bin"], "agents", "--json"], capture_output=True, text=True,
                         timeout=60, stdin=subprocess.DEVNULL, cwd=cfg["sender_cwd"]).stdout
    try:
        return json.loads(out or "[]")
    except ValueError:
        return []


def launch_mode(pid: int) -> str:
    try:
        argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    except OSError:
        return ""
    for i, arg in enumerate(argv):
        if arg == b"--permission-mode" and i + 1 < len(argv):
            return argv[i + 1].decode()
        if arg.startswith(b"--permission-mode="):
            return arg.split(b"=", 1)[1].decode()
        if arg == b"--dangerously-skip-permissions":
            return "bypassPermissions"
    return ""


def sender_mode(mapping: dict, session: dict) -> str:
    """Match the target's permission-mode class: bypass vs prompting."""
    if mapping.get("sender_mode"):
        return mapping["sender_mode"]
    return "bypassPermissions" if launch_mode(session.get("pid", 0)) == "bypassPermissions" else "auto"


def nudge_text(agent_id: str, msgs: list[dict]) -> str:
    first = msgs[0]
    if len(msgs) == 1:
        return (f"Switchboard: new message #{first['id']} for {clean(agent_id)} on thread "
                f"{clean(first.get('thread_id') or 'none')} from {clean(first.get('from'))}; "
                f"read it with get_messages (agent_id {clean(agent_id)}) and reply there.")
    senders = ", ".join(sorted({clean(m.get("from"), 30) for m in msgs}))[:120]
    threads = ", ".join(sorted({clean(m.get("thread_id") or "none", 40) for m in msgs}))[:160]
    return (f"Switchboard: {len(msgs)} unread messages (#{msgs[0]['id']}-#{msgs[-1]['id']}) for "
            f"{clean(agent_id)} from {senders} on threads {threads}; read them with get_messages "
            f"(agent_id {clean(agent_id)}) and reply there.")


def deliver(cfg: dict, session_name: str, mode: str, text: str) -> tuple[str, str]:
    prompt = (
        "You relay one notice. Step 1: call ListAgents. Step 2: find the row whose name is exactly "
        f"{json.dumps(session_name)} and that is a running local session (interactive or background, "
        "not 'Remote Control · offline' and not 'cloud'). If several rows share that name, address it "
        "as the name followed by its [ref]. Step 3: call SendMessage once to that session with exactly "
        f"this message text and nothing else:\n{text}\n"
        "If no such row exists, do not send anything and reply NOT_FOUND. Otherwise reply DONE.")
    cmd = [cfg["claude_bin"], "-p", "--model", cfg["sender_model"], "--tools", "SendMessage,ListAgents",
           "--strict-mcp-config", "--settings", '{"disableAllHooks":true}', "--permission-mode", mode,
           "--no-session-persistence", "-n", "switchboard-waker", "--output-format", "stream-json",
           "--verbose", prompt]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, stdin=subprocess.DEVNULL,
                          cwd=cfg["sender_cwd"])
    send_ids, tool_result, final = set(), "", ""
    for line in proc.stdout.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        content = (ev.get("message") or {}).get("content")
        if isinstance(content, list):
            for block in content:
                if block.get("type") == "tool_use" and block.get("name") == "SendMessage":
                    send_ids.add(block.get("id"))
                if block.get("type") == "tool_result" and block.get("tool_use_id") in send_ids:
                    c = block.get("content")
                    tool_result = c if isinstance(c, str) else " ".join(x.get("text", "") for x in c or [])
        if ev.get("type") == "result":
            final = str(ev.get("result", ""))
    if not send_ids:
        return ("not_found" if "NOT_FOUND" in final else "error", final[:300] or proc.stderr[-300:])
    try:
        parsed = json.loads(tool_result)
    except ValueError:
        parsed = {}
    # success = in the target's inbox. If that session later holds it (permission-mode
    # mismatch), it shows there as a held message for Landon to approve.
    if parsed.get("success") is True:
        return "sent", str(parsed.get("message", ""))[:200]
    return "error", tool_result[:300]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--agent")
    args = ap.parse_args()

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock = open(STATE_DIR / "lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("another run in progress; exiting")
        return 0

    conf = json.loads(CONFIG.read_text())
    hook_cfg = json.loads(HOOK_CONFIG.read_text()) if HOOK_CONFIG.exists() else {}
    cfg = {**DEFAULTS, "token_env": hook_cfg.get("token_env", DEFAULTS["token_env"]), **conf.get("settings", {})}
    if not cfg["switchboard_url"]:
        if not hook_cfg.get("base"):
            log(f"set settings.switchboard_url in {CONFIG} or base in {HOOK_CONFIG}")
            return 1
        cfg["switchboard_url"] = hook_cfg["base"].rstrip("/") + "/mcp"
    token = load_token(cfg["token_env"], hook_cfg)
    if not token:
        log(f"no {cfg['token_env']} found; exiting")
        return 1
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    agents = state.setdefault("agents", {})
    mappings = [m for m in conf.get("mappings", [])
                if m.get("enabled", True) and (not args.agent or args.agent == m["agent_id"])]
    by_id = {m["agent_id"]: m for m in mappings}

    # 1. Scan new bus traffic once, collect direct messages to mapped agents.
    if "scan_id" not in state:
        state["scan_id"] = bus_head(cfg, token)  # install baseline: never replay a backlog
        log(f"baseline: scanning starts after #{state['scan_id']}")
    for _ in range(int(cfg.get("max_pages_per_run", 50))):
        page = history(cfg, token, state["scan_id"])
        if not page:
            break
        for m in page:
            to = m.get("to")
            if to in by_id and m.get("from") != to:
                agents.setdefault(to, {"pending": [], "nudges": []})["pending"].append(
                    {"id": m["id"], "from": m.get("from"), "thread_id": m.get("thread_id")})
        state["scan_id"] = max(m["id"] for m in page)

    # 2. Per agent: drop what it already read, then nudge (coalesced, rate-limited).
    sessions = None
    now = time.time()
    for agent_id, mapping in by_id.items():
        st = agents.setdefault(agent_id, {"pending": [], "nudges": []})
        if not st["pending"]:
            continue
        floor = first_unread(cfg, token, agent_id)
        st["pending"] = [m for m in st["pending"] if floor is not None and m["id"] >= floor]
        if not st["pending"]:
            continue
        fresh = st["pending"]
        interval = 60 * mapping.get("min_interval_min", cfg["min_interval_min"])
        per_hour = mapping.get("max_nudges_per_hour", cfg["max_nudges_per_hour"])
        st["nudges"] = [t for t in st["nudges"] if now - t < 3600]
        if st["nudges"] and now - st["nudges"][-1] < interval:
            log(f"[{agent_id}] {len(fresh)} pending, rate-limited (last nudge {int(now - st['nudges'][-1])}s ago)")
            continue
        if len(st["nudges"]) >= per_hour:
            log(f"[{agent_id}] {len(fresh)} pending, hourly cap {per_hour} reached")
            continue
        if sessions is None:
            sessions = local_sessions(cfg)
        name = mapping["session"]
        running = [s for s in sessions if s.get("name") == name]
        if not running:
            log(f"[{agent_id}] {len(fresh)} pending, but session {name!r} is not running locally; will retry")
            continue
        mode = sender_mode(mapping, running[0])
        text = nudge_text(agent_id, fresh)
        if args.dry_run:
            log(f"[{agent_id}] DRY RUN -> {name!r} (sender mode {mode}): {text}")
            continue
        status, detail = deliver(cfg, name, mode, text)
        log(f"[{agent_id}] nudge -> {name!r} mode={mode} status={status} ids={[m['id'] for m in fresh]} :: {detail}")
        st["nudges"].append(now)  # failed attempts are rate-limited too, then retried
        if status == "sent":
            # a held message waits for Landon in that session; still counts, so no repeat spam.
            st["pending"] = []

    if not args.dry_run:
        tmp = STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=1))
        tmp.replace(STATE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
