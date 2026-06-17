# Phase 12 Plan: Hourly Context Management

**Requirement:** CTX-01

## Build
`channel/run-channel-session.py`: after init, every `CHANNEL_COMPACT_INTERVAL_SEC` (default
3600, 0=off) write `/compact\r` to the pty master and log `=== injected /compact ===`.
Unit sets `CHANNEL_COMPACT_INTERVAL_SEC=3600`; commented `RuntimeMaxSec=3900` rotation fallback.

## Verify (success criteria)
1. With a 90s test interval (drop-in), the harness injects `/compact` without manual action;
   `injected /compact` marker + a compaction indicator appear in session.log. (crit 1)
2. After compaction the unit is still `active` and a bus DM to `Billy` still gets a reply —
   responder did not drop off the bus. (crit 3)
3. (rotation fallback documented + proven via Phase 11 restart — crit 2 covered by that path.)
4. Logs show the cadence event with no crash. (crit 4)

Then remove the test drop-in → effective interval back to 3600 for production.

## Pass
Compaction fires on cadence headless, session stays alive + responsive, no crash.
