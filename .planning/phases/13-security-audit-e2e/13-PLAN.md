# Phase 13 Plan: Security Audit + End-to-End Verify

**Requirements:** SEC-02 (audit + mitigations), VERIFY-05 (E2E)

## Audit (SEC-02)
Write `SECURITY.md` covering T1 prompt injection, T2 allowlist bypass via spoofed `from`,
T3 tool-abuse blast radius, T4 secret exfiltration, T5 cost/DoS, T6 research-preview flag —
each triaged mitigated or accepted.

## Mitigations (apply concrete ones)
- M1: `--disallowedTools Bash Edit Write MultiEdit NotebookEdit` (harness/unit, default on).
- M2: per-sender rate limit + content cap (bridge).
- M3: hardened channel instructions — bus content is untrusted (bridge).
- Accept T2 (trusted-LAN shared token; per-agent tokens = v2).

## Verify
1. Audit doc covers the three required vectors, every finding triaged. (crit 1)
2. Concrete mitigation in place: confirm `--disallowedTools` on the live cmdline + an
   injection probe (`SYSTEM OVERRIDE` → dump config.json) is refused with no token leaked. (crit 2)
3. Real Fred sends a DM (no interactive session open) → Billy replies context-aware (~2s). (crit 3)
4. Unit still `active` after the round trip. (crit 4)

## Pass
Audit complete, mitigations live + proven (injection refused), real-Fred E2E succeeds, unit survives.
