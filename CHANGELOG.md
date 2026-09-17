# Changelog

## v0.1.1

- Fix `UserPromptSubmit` output so ordinary allow decisions emit no invalid JSON.
- Resolve hook commands through `PLUGIN_ROOT` so they work from any task directory.
- Add a one-time protective block when the weekly Coding Plan window has 3% or less remaining.
- Keep the existing five-hour soft nudge from 25% to more than 3% remaining and its one-time 3% protective block.

## v0.1.0

- Initial public release of the Codex handoff plugin and its vendor-neutral handoff skills.
