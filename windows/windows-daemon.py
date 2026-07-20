#!/usr/bin/env python3
"""
Windows always-on "Claude" presence daemon for mcp-switchboard.

Keeps the "Claude" agent registered and visible on the bus even when no
interactive Claude Code session is open. On an inbound DM it does two things:
  1. Fires a Windows toast notification so the operator sees the message.
  2. Auto-replies headlessly via `claude --print` (Billy-style stateless responder).

YIELD DESIGN — inbox-drain collision prevention
-----------------------------------------------
The interactive Claude Code session drains the same "Claude" inbox via the
/sync hooks (switchboard-publish.mjs, switchboard-digest.mjs). The bus cursor
is monotonic; whoever drains first wins — no redelivery. To avoid stealing
each other's messages, this daemon is a FALLBACK that yields whenever a live
session is active:

  • The hooks write the current epoch-ms to ~/.switchboard/interactive.lock
    on every PostToolUse/Stop/SessionStart/UserPromptSubmit.
  • This daemon checks lock age before consuming: fresh (< INTERACTIVE_LOCK_TTL)
    → session owns the inbox → heartbeat only.  Stale → daemon consumes.

CRITICAL: the daemon uses get_messages(peek=True) + ack(), NOT wait_for_message.
wait_for_message drains the inbox unconditionally inside the bus (bus.js:263)
before any lock-check can happen, making it unsafe for yielding. peek → re-check
lock → ack(up_to_id=m.id) BEFORE the LLM call ensures atomic, exactly-once
hand-off even if a session opens mid-reply.

Config: shares ~/.switchboard/config.json with the interactive hooks.
  Required fields: base (bus URL), the bearer credential (field name: token), agent_id.
  Optional: name, allowlist (comma-separated trusted sender ids). See windows/README.md.
Env overrides: SWITCHBOARD_BASE, SWITCHBOARD_MCP_TOKEN, SWITCHBOARD_AGENT_ID,
  SWITCHBOARD_AGENT_NAME, CLAUDE_BIN, SWITCHBOARD_ALLOWED_SENDERS,
  CHANNEL_DISALLOWED_TOOLS, SWITCHBOARD_RATE_MAX, SWITCHBOARD_RATE_WINDOW_MS,
  INTERACTIVE_LOCK_TTL_SEC, POLL_IDLE_SEC, POLL_ACTIVE_SEC,
  HEARTBEAT_SEC, REPLY_TIMEOUT_SEC

SECURITY: fail-closed allowlist; --strict-mcp-config prevents MCP server loading
(avoids the docker-MCP-leak and switchboard-recursion risk); tool denylist blocks
shell/file/network from untrusted bus content on this real workstation.

Run headless:  pythonw windows-daemon.py
Debug:         python  windows-daemon.py --foreground
Install task:  .\\install-task.ps1
"""

import argparse
import json
import logging
import logging.handlers
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONFIG_PATH = Path(os.path.expanduser("~/.switchboard/config.json"))
LOCK_PATH   = Path(os.path.expanduser("~/.switchboard/interactive.lock"))
LOG_PATH    = Path(os.path.expanduser("~/.switchboard/windows-daemon.log"))


def load_config() -> dict:
    """Merge ~/.switchboard/config.json with environment overrides."""
    cfg: dict = {}
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        pass  # rely on env vars
    except Exception as exc:
        print(f"[warn] Could not parse {CONFIG_PATH}: {exc} — relying on env", file=sys.stderr)

    base     = os.environ.get("SWITCHBOARD_BASE")     or cfg.get("base")
    token    = os.environ.get("SWITCHBOARD_MCP_TOKEN") or cfg.get("token")  # pragma: allowlist secret
    agent_id = os.environ.get("SWITCHBOARD_AGENT_ID") or cfg.get("agent_id")
    name     = os.environ.get("SWITCHBOARD_AGENT_NAME") or cfg.get("name") or agent_id

    missing = [k for k, v in {"base": base, "token": token, "agent_id": agent_id}.items() if not v]  # pragma: allowlist secret
    if missing:
        print(f"[error] Missing required config: {', '.join(missing)}. Set in {CONFIG_PATH} or via env.", file=sys.stderr)
        sys.exit(1)

    # Sender allowlist — accepts "Fred,Billy", a JSON array, or "*" (allow all token holders).
    # Empty string / missing key = fail-closed (nothing passes).
    # Falsy check (not `is None`): an env var present-but-empty (e.g. a template placeholder
    # left blank) must still fall back to config.json's allowlist, not shadow it silently.
    raw_allow = os.environ.get("SWITCHBOARD_ALLOWED_SENDERS")
    if not raw_allow:
        raw_allow = cfg.get("allowlist", "")
    if raw_allow == "*" or raw_allow == ["*"]:
        allowlist: set = {"*"}  # sentinel: allow all
    elif isinstance(raw_allow, list):
        allowlist = {str(s).strip() for s in raw_allow if str(s).strip()}
    else:
        allowlist = {s.strip() for s in str(raw_allow).split(",") if s.strip()}

    disallowed = os.environ.get(
        "CHANNEL_DISALLOWED_TOOLS",
        "Bash Edit Write MultiEdit NotebookEdit Read Glob Grep WebFetch WebSearch Task",
    ).split()

    # Resolve claude binary once at startup. On Windows, `claude` is usually
    # `claude.cmd`. subprocess.run with a list doesn't find .cmd without shell=True
    # (which we avoid). Wrap .cmd/.bat callers with ["cmd", "/c", ...] so content
    # after "--" is still a fixed argument, not a shell string.
    claude_bin_env = os.environ.get("CLAUDE_BIN")
    if claude_bin_env:
        raw_bin = claude_bin_env
    else:
        # Try claude first (PATH), fall back to claude.cmd
        raw_bin = shutil.which("claude") or shutil.which("claude.cmd") or "claude"
    if raw_bin.lower().endswith((".cmd", ".bat")):
        claude_prefix = ["cmd", "/c", raw_bin]
    else:
        claude_prefix = [raw_bin]

    # Legacy/alias agent IDs to also register and drain.
    # Messages sent to any alias reach this daemon. Defaults to ["claude-code"]
    # so old callers that still target "claude-code" are not dropped.
    raw_aliases = cfg.get("aliases", ["claude-code"])
    if isinstance(raw_aliases, str):
        raw_aliases = [a.strip() for a in raw_aliases.split(",") if a.strip()]
    aliases = [a for a in raw_aliases if a and a != agent_id]

    return {
        "base":          base.rstrip("/"),
        "url":           base.rstrip("/") + "/mcp",
        "token":         token,  # pragma: allowlist secret
        "agent_id":      agent_id,
        "aliases":       aliases,
        "name":          name,
        "claude_prefix": claude_prefix,
        "allowlist":     allowlist,
        "disallowed_tools": disallowed,
        "rate_max":      int(os.environ.get("SWITCHBOARD_RATE_MAX", "20")),
        "rate_window_sec": float(os.environ.get("SWITCHBOARD_RATE_WINDOW_MS", "60000")) / 1000.0,
        # Yield / timing
        "lock_ttl_sec":      float(os.environ.get("INTERACTIVE_LOCK_TTL_SEC", "90")),
        "poll_idle_sec":     float(os.environ.get("POLL_IDLE_SEC", "5")),
        "poll_active_sec":   float(os.environ.get("POLL_ACTIVE_SEC", "1")),
        "heartbeat_sec":     float(os.environ.get("HEARTBEAT_SEC", "30")),
        "reply_timeout_sec": float(os.environ.get("REPLY_TIMEOUT_SEC", "180")),
    }


CFG = load_config()
log = logging.getLogger("switchboard-windows")

# ---------------------------------------------------------------------------
# HTTP / MCP (stdlib urllib — no pip required)
# ---------------------------------------------------------------------------

def _http_post(url: str, body: dict, http_timeout: int = 10) -> str:
    data = json.dumps(body).encode("utf-8")
    req  = urllib.request.Request(
        url, data=data, method="POST",
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {CFG['token']}",  # pragma: allowlist secret
            "Accept":        "application/json, text/event-stream",
        },
    )
    with urllib.request.urlopen(req, timeout=http_timeout) as resp:
        return resp.read().decode("utf-8")


def _parse_sse(text: str) -> dict:
    """Parse SSE 'data: {...}' response and unwrap tools/call content[0].text."""
    for line in text.strip().splitlines():
        if line.startswith("data:"):
            data = json.loads(line[len("data:"):].strip())
            if "error" in data:
                raise RuntimeError(f"MCP error: {data['error']}")
            result = data.get("result", {})
            if "content" in result and result["content"]:
                return json.loads(result["content"][0]["text"])
            return result
    raise RuntimeError(f"Unexpected MCP response: {text!r}")


def mcp_call(method: str, params: dict, http_timeout: int = 10) -> dict:
    text = _http_post(CFG["url"], {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, http_timeout)
    return _parse_sse(text)


def tool_call(name: str, arguments: dict, http_timeout: int = 10) -> dict:
    return mcp_call("tools/call", {"name": name, "arguments": arguments}, http_timeout=http_timeout)


# ---------------------------------------------------------------------------
# Bus operations
# ---------------------------------------------------------------------------

def register() -> None:
    result = tool_call("register_agent", {"agent_id": CFG["agent_id"], "name": CFG["name"]})
    log.info("Registered: %s", result)
    for alias in CFG["aliases"]:
        try:
            tool_call("register_agent", {"agent_id": alias, "name": CFG["name"]})
            log.info("Registered alias: %s", alias)
        except Exception as exc:
            log.warning("Could not register alias %s: %s", alias, exc)


def do_heartbeat() -> None:
    for aid in [CFG["agent_id"]] + CFG["aliases"]:
        try:
            tool_call("heartbeat", {"agent_id": aid}, http_timeout=5)
            log.debug("Heartbeat ok: %s", aid)
        except Exception as exc:
            log.debug("Heartbeat failed for %s (non-fatal): %s", aid, exc)


def peek_inbox() -> list[dict]:
    """Read DMs from primary + alias inboxes without advancing cursors.
    Each returned message has a synthetic '_inbox_id' key indicating which
    agent_id cursor to ack when claiming it."""
    all_msgs: list[dict] = []
    for aid in [CFG["agent_id"]] + CFG["aliases"]:
        try:
            result = tool_call(
                "get_messages",
                {"agent_id": aid, "peek": True, "drain": False},
                http_timeout=10,
            )
            for m in result.get("messages", []):
                if m.get("to") == aid:
                    m["_inbox_id"] = aid
                    all_msgs.append(m)
        except Exception as exc:
            log.warning("peek_inbox failed for %s: %s", aid, exc)
    return all_msgs


def claim(up_to_id: int, inbox_id: Optional[str] = None) -> None:
    """Advance the @dm cursor for inbox_id (defaults to primary agent_id)."""
    aid = inbox_id or CFG["agent_id"]
    tool_call("ack", {"agent_id": aid, "up_to_id": up_to_id}, http_timeout=5)


def send_reply(to: str, content: str, thread_id: Optional[str] = None,
               reply_to: Optional[int] = None) -> None:
    args: dict = {"from": CFG["agent_id"], "to": to, "content": content, "type": "result"}
    if thread_id:
        args["thread_id"] = thread_id
    if reply_to is not None:
        args["reply_to"] = reply_to
    tool_call("send_message", args)

# ---------------------------------------------------------------------------
# Interactive-session lock (yield mechanism)
# ---------------------------------------------------------------------------

def lock_fresh() -> bool:
    """True if a live interactive session has touched the lock recently."""
    try:
        age = time.time() - float(LOCK_PATH.read_text(encoding="utf-8").strip()) / 1000.0
        return age < CFG["lock_ttl_sec"]
    except Exception:
        return False  # missing/corrupt lock → no session active

# ---------------------------------------------------------------------------
# Toast notification
# ---------------------------------------------------------------------------

# WinRT toast via PowerShell piped on stdin — attacker content never reaches
# the command line. The built-in PowerShell AppUserModelID requires no app
# registration. Click is a no-op.
_PS_TOAST = r"""
$ErrorActionPreference='SilentlyContinue'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null
[Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType=WindowsRuntime] | Out-Null
$xml = @'
<toast><visual><binding template="ToastGeneric">
<text>Switchboard DM from __SENDER__</text>
<text>__SNIPPET__</text>
</binding></visual></toast>
'@
# Single-quoted here-string: PowerShell performs NO variable/subexpression expansion.
# Python .replace() on __SENDER__/__SNIPPET__ runs before the script reaches PowerShell,
# so all dynamic content is already inline as literal text. This blocks $(calc.exe)-style
# injection — TW3 mitigation.
$doc = [Windows.Data.Xml.Dom.XmlDocument]::new(); $doc.LoadXml($xml)
$toast = [Windows.UI.Notifications.ToastNotification]::new($doc)
$appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe' # pragma: allowlist secret
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
"""

def _xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;")
             .replace("'", "&apos;"))


def toast(sender: str, snippet: str) -> None:
    """Fire a Windows toast; non-fatal on any failure."""
    try:
        body = (_PS_TOAST
                .replace("__SENDER__", _xml_escape(sender[:80]))
                .replace("__SNIPPET__", _xml_escape(snippet[:120])))
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", "-"],
            input=body, text=True, timeout=10, capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        log.info("Toast fired for DM from %s", sender)
    except Exception as exc:
        log.warning("Toast failed (non-fatal): %s", exc)

# ---------------------------------------------------------------------------
# Auto-reply via claude --print
# ---------------------------------------------------------------------------

def run_claude(content: str) -> str:
    """Spawn a headless, answer-only claude --print and return its stdout."""
    tool_args = ["--disallowedTools", *CFG["disallowed_tools"]] if CFG["disallowed_tools"] else []
    cmd = [
        *CFG["claude_prefix"],
        "--print",
        "--no-session-persistence",
        "--strict-mcp-config",   # load zero MCP servers (avoids recursion + docker-MCP-leak)
        *tool_args,
        "--",                    # end of option parsing; content can't be mistaken for a flag
        content,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=CFG["reply_timeout_sec"],
            env={**os.environ, "HOME": os.path.expanduser("~")},
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"request timed out after {int(CFG['reply_timeout_sec'])}s") from None
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc

    if result.returncode != 0:
        # A nonzero exit means claude itself failed (auth, crash, etc.) — the
        # stderr/stdout text is a subprocess failure, not a considered reply.
        # Raising (instead of returning it as text) stops the daemon from
        # forwarding raw CLI errors to the sender as if they were an answer.
        raise RuntimeError(
            (result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}")[:300]
        )
    return result.stdout.strip() or "(no output)"

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

_rate: dict = {}


def rate_ok(sender: str) -> bool:
    now    = time.time()
    window = CFG["rate_window_sec"]
    arr    = [t for t in _rate.get(sender, []) if now - t < window]
    if len(arr) >= CFG["rate_max"]:
        _rate[sender] = arr
        return False
    arr.append(now)
    _rate[sender] = arr
    return True

# ---------------------------------------------------------------------------
# Message handler
# ---------------------------------------------------------------------------

def handle_message(msg: dict) -> None:
    """Claim, toast, reply for a single already-peeked message."""
    content   = msg.get("content", "")
    sender    = msg.get("from", "unknown")
    msg_id    = msg.get("id")
    thread_id = msg.get("thread_id")

    allow_all = "*" in CFG["allowlist"]
    if not allow_all and sender not in CFG["allowlist"]:
        if not CFG["allowlist"]:
            log.warning("Dropped message %s: no allowlist configured (fail-closed). "
                        "Set SWITCHBOARD_ALLOWED_SENDERS or allowlist=* to enable responses.", msg_id)
        else:
            log.warning("Dropped message %s from non-allowlisted sender %r", msg_id, sender)
        # Still claim it so the cursor advances and it doesn't re-appear every poll.
        if msg_id is not None:
            try: claim(msg_id, msg.get("_inbox_id"))
            except Exception: pass
        return

    if not rate_ok(sender):
        log.warning("Rate-limited message %s from %r (>%s per %ss)",
                    msg_id, sender, CFG["rate_max"], CFG["rate_window_sec"])
        return  # leave unclaimed; the session can pick it up if it comes alive

    inbox_id = msg.get("_inbox_id")
    log.info("Handling message from %s (id=%s inbox=%s): %.120s",
             sender, msg_id, inbox_id or CFG["agent_id"], content)

    # CLAIM before the slow LLM call — any session that opens afterward drains
    # only ids > msg_id and will not re-answer this message.
    if msg_id is not None:
        try:
            claim(msg_id, inbox_id)
            log.debug("Claimed message id=%s inbox=%s", msg_id, inbox_id)
        except Exception as exc:
            log.error("Failed to claim message %s: %s — skipping to avoid double-process", msg_id, exc)
            return

    toast(sender, content[:120])

    try:
        reply = run_claude(content)
    except Exception as exc:
        # claude itself failed (auth, crash, timeout) — do NOT forward that raw
        # failure to the sender as if it were a considered reply. That previously
        # caused a self-sustaining loop: sender asks a question -> claude --print
        # fails auth -> daemon sends the raw "401" text back -> sender tries to
        # "help debug" the fake error -> repeat. Log and stay silent instead; the
        # message is already claimed, so an interactive session won't re-answer it.
        log.error("run_claude failed for message %s from %s: %s — not replying", msg_id, sender, exc)
        return

    try:
        send_reply(sender, reply, thread_id=thread_id, reply_to=msg_id)
        log.info("Replied to %s (id=%s)", sender, msg_id)
    except Exception as exc:
        log.error("Failed to send reply to %s: %s", sender, exc)

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Windows switchboard presence daemon")
    parser.add_argument("--foreground", action="store_true",
                        help="Log to stdout instead of the rotating log file (for debugging)")
    args = parser.parse_args()

    # Logging setup
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    handler: logging.Handler
    if args.foreground:
        handler = logging.StreamHandler(sys.stdout)
    else:
        handler = logging.handlers.RotatingFileHandler(
            LOG_PATH, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[handler],
    )

    alias_str = ", ".join(CFG["aliases"]) if CFG["aliases"] else "none"
    log.info("Windows presence daemon starting (agent_id=%s, aliases=%s, base=%s)",
             CFG["agent_id"], alias_str, CFG["base"])
    if "*" in CFG["allowlist"]:
        log.info("Allowlist: * (all token holders accepted)")
    elif CFG["allowlist"]:
        log.info("Allowlisted senders: %s", ", ".join(sorted(CFG["allowlist"])))
    else:
        log.warning("No allowlist configured — fail-closed; ALL messages will be dropped. "
                    "Set SWITCHBOARD_ALLOWED_SENDERS=* or allowlist=* to enable responses.")
    log.info("Lock TTL=%ss | Poll idle=%ss active=%ss | Heartbeat=%ss",
             CFG["lock_ttl_sec"], CFG["poll_idle_sec"],
             CFG["poll_active_sec"], CFG["heartbeat_sec"])

    # Register once; the bus makes it idempotent.
    backoff = 5.0
    while True:
        try:
            register()
            break
        except Exception as exc:
            log.warning("Register failed: %s — retrying in %ss", exc, backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)

    log.info("Ready. Polling the bus (peek-poll + lock-yield).")
    backoff        = 5.0
    last_heartbeat = 0.0

    while True:
        now = time.time()

        # Heartbeat — keep presence green (<60s window) on every path, including yield.
        if now - last_heartbeat >= CFG["heartbeat_sec"]:
            do_heartbeat()
            last_heartbeat = time.time()

        try:
            # Yield if a live interactive session owns the inbox.
            if lock_fresh():
                log.debug("Lock fresh — interactive session active, yielding inbox")
                time.sleep(CFG["poll_idle_sec"])
                backoff = 5.0
                continue

            # Peek (no cursor advance) — DMs only.
            msgs = peek_inbox()
            if not msgs:
                time.sleep(CFG["poll_idle_sec"])
                backoff = 5.0
                continue

            # Re-check: a session may have opened between peek and now.
            if lock_fresh():
                log.debug("Lock freshened between peek and consume — yielding")
                time.sleep(CFG["poll_idle_sec"])
                continue

            for msg in msgs:
                try:
                    handle_message(msg)
                except Exception as exc:
                    log.error("handle_message failed for id=%s: %s", msg.get("id"), exc)

            backoff = 5.0
            time.sleep(CFG["poll_active_sec"])

        except Exception as exc:
            log.warning("Poll error: %s — retrying in %ss", exc, backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)


if __name__ == "__main__":
    main()
