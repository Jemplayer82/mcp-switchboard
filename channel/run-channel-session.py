#!/usr/bin/env python3
# Production pty harness for the headless switchboard channel responder.
# Runs interactive `claude --dangerously-load-development-channels
# server:switchboard-channel --dangerously-skip-permissions` in a properly-sized
# pty (channels only fire turns in interactive mode), auto-confirms the
# dev-channels warning dialog, holds stdin open so the session never EOF-exits,
# mirrors the TUI to a log, and exits with the child's status so systemd
# (Restart=always) respawns it.
import os, pty, fcntl, termios, struct, subprocess, select, time, sys

WORKDIR = os.environ.get("CHANNEL_WORKDIR", os.path.expanduser("~/switchboard-channel"))
LOG = os.environ.get("CHANNEL_LOG", os.path.join(WORKDIR, "session.log"))
CLAUDE = os.environ.get("CLAUDE_BIN", os.path.expanduser("~/.local/bin/claude"))
# Hourly context bounding: inject `/compact` into the live session every N seconds
# (0 disables). Keeps continuity via a summary rather than a full reset; systemd restart
# remains the fallback if /compact ever wedges the session.
COMPACT_INTERVAL = int(os.environ.get("CHANNEL_COMPACT_INTERVAL_SEC", "3600"))
# M1 (security): restrict the responder's tool surface so injected (untrusted) bus content
# can't run shell, write files, read local secrets, OR exfiltrate over the network. The list
# must cover three classes: execution (Bash), file mutation (Edit/Write/MultiEdit/NotebookEdit),
# and — critically — file READ + network egress (Read/Glob/Grep/WebFetch/WebSearch/Task), since
# the session runs with --dangerously-skip-permissions: an unblocked Read would let injection
# dump ~/.claude/.credentials.json or ~/.switchboard/config.json straight to the reply tool.
# Space-separated; empty string = no restriction (full tools — only if you trust every
# allowlisted sender completely and want Billy to actuate). NOTE: this is a denylist, so any
# NEW tool a future Claude version adds is permitted by default — re-audit on CLI upgrades.
DISALLOWED_TOOLS = os.environ.get(
    "CHANNEL_DISALLOWED_TOOLS",
    "Bash Edit Write MultiEdit NotebookEdit Read Glob Grep WebFetch WebSearch Task",
).split()

master, slave = os.openpty()
fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 200, 0, 0))

env = dict(os.environ)
env["PATH"] = os.path.expanduser("~/.local/bin") + ":" + env.get("PATH", "")
env["TERM"] = "xterm-256color"

cmd = [CLAUDE, "--dangerously-load-development-channels", "server:switchboard-channel",
       "--dangerously-skip-permissions",
       # lock MCP to channel bridge only (strict ignores ~/.claude.json) so untrusted
       # bus content cannot reach schwab/home-assistant/portainer/proxmox/github tools
       "--strict-mcp-config", "--mcp-config", os.path.join(WORKDIR, ".mcp.json")]
if DISALLOWED_TOOLS:
    cmd += ["--disallowedTools", *DISALLOWED_TOOLS]

p = subprocess.Popen(
    cmd,
    stdin=slave, stdout=slave, stderr=slave, cwd=WORKDIR, env=env,
    preexec_fn=os.setsid, close_fds=True,
)
os.close(slave)

start = time.time()
sent = 0
last_compact = None
with open(LOG, "ab", buffering=0) as log:
    log.write(("\n=== session start %s ===\n" % time.strftime("%Y-%m-%dT%H:%M:%S")).encode())
    while p.poll() is None:
        el = time.time() - start
        if sent == 0 and el > 3:
            os.write(master, b"\r"); sent = 1          # confirm dev-channels dialog
        elif sent == 1 and el > 8:
            os.write(master, b"\r"); sent = 2          # session initialized
        elif sent == 2 and COMPACT_INTERVAL > 0:
            now = time.time()
            if last_compact is None:
                last_compact = now                      # start the compaction clock post-init
            elif now - last_compact >= COMPACT_INTERVAL:
                os.write(master, b"/compact\r")
                log.write(("\n=== injected /compact %s ===\n" % time.strftime("%Y-%m-%dT%H:%M:%S")).encode())
                last_compact = now
        r, _, _ = select.select([master], [], [], 1.0)
        if master in r:
            try:
                data = os.read(master, 8192)
            except OSError:
                break
            if not data:
                break
            log.write(data)

sys.exit(p.returncode if p.returncode is not None else 1)
