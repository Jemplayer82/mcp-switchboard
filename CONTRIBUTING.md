# Contributing to mcp-switchboard

Thanks for your interest in improving the switchboard. This is a small, focused
project — one centralized streamable-HTTP MCP server — so contributions that keep
it lean and single-purpose are the most welcome.

## `[ ground rules ]`

- **One container, one writer.** The design assumes exactly one running instance
  (in-process `EventEmitter` + single-writer SQLite). Don't add features that
  assume horizontal scale.
- **No new heavy dependencies.** No broker (Redis/Kafka), no ORM. Match the
  existing vanilla ES-module + `@modelcontextprotocol/sdk` style.
- **Never commit secrets.** `SWITCHBOARD_MCP_TOKEN` and any real tokens live in
  `.env` or the environment only — never in committed files.

## `[ workflow ]`

1. Fork and branch from `main`.
2. Make your change as a clear, atomic commit.
3. Run the server locally (`npm install && npm start`) and exercise the affected
   tools before opening a PR.
4. Open a pull request describing the change and how you verified it.

## `[ license ]`

By contributing, you agree that your contributions are licensed under the
[GNU Affero General Public License v3.0](./LICENSE), the same license as the project.
