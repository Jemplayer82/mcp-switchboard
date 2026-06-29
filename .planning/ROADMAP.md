# Roadmap: mcp-switchboard

## Milestones

- ✅ **v1.0 Bus Core + Deploy + Wire** — Phases 1–5 (built & verified; VERIFY-02 deferred)
- 📋 **v1.1 Supergateway + Playwright Scraper** — Phases 6–8 (deferred, unstarted)
- ✅ **v1.2 Headless Full-Context Channel Responder** — Phases 9–13 (shipped 2026-06-17)
- ✅ **v1.3 Windows always-on presence daemon** — feat/windows-headless-daemon (shipped 2026-06-29)

Full per-milestone phase detail, success criteria, and requirements are archived under
`.planning/milestones/` (`v{X.Y}-ROADMAP.md`, `v{X.Y}-REQUIREMENTS.md`, `v{X.Y}-MILESTONE-AUDIT.md`).

## Phases

<details>
<summary>✅ v1.0 Bus Core + Deploy + Wire (Phases 1–5) — built & verified</summary>

- [x] Phase 1: Bus Core
- [x] Phase 2: Presence, Wake & Awareness
- [x] Phase 3: Ship to mcp-shared
- [x] Phase 4: Wire Clients & Awareness Hooks
- [x] Phase 5: End-to-End Verify (VERIFY-02 Hermes round-trip deferred)

</details>

<details>
<summary>📋 v1.1 Supergateway + Playwright Scraper (Phases 6–8) — DEFERRED (unstarted)</summary>

- [ ] Phase 6: Gateway Stand-Up + Switchboard Redeploy
- [ ] Phase 7: Playwright Scraper Behind Gateway
- [ ] Phase 8: Client Rewire + End-to-End Verify

</details>

<details>
<summary>✅ v1.2 Headless Full-Context Channel Responder (Phases 9–13) — SHIPPED 2026-06-17</summary>

- [x] Phase 9: Headless Channel Spike (Go/No-Go Gate) — PASSED
- [x] Phase 10: switchboard-channel MCP Bridge
- [x] Phase 11: Persistent Deploy + Inbox-Collision Resolution (Billy live; cold daemon retired)
- [x] Phase 12: Hourly Context Management (in-session /compact)
- [x] Phase 13: Security Audit + End-to-End Verify (real-Fred E2E)

</details>
