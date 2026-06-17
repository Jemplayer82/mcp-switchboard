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

master, slave = os.openpty()
fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 200, 0, 0))

env = dict(os.environ)
env["PATH"] = os.path.expanduser("~/.local/bin") + ":" + env.get("PATH", "")
env["TERM"] = "xterm-256color"

p = subprocess.Popen(
    [CLAUDE, "--dangerously-load-development-channels", "server:switchboard-channel",
     "--dangerously-skip-permissions"],
    stdin=slave, stdout=slave, stderr=slave, cwd=WORKDIR, env=env,
    preexec_fn=os.setsid, close_fds=True,
)
os.close(slave)

start = time.time()
sent = 0
with open(LOG, "ab", buffering=0) as log:
    log.write(("\n=== session start %s ===\n" % time.strftime("%Y-%m-%dT%H:%M:%S")).encode())
    while p.poll() is None:
        el = time.time() - start
        if sent == 0 and el > 3:
            os.write(master, b"\r"); sent = 1          # confirm dev-channels dialog
        elif sent == 1 and el > 8:
            os.write(master, b"\r"); sent = 2
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
