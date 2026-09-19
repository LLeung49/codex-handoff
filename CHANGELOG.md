# Changelog

## v0.2.1

- Start the five-hour soft handoff nudge at 15% remaining rather than 25%; its
  one-time protective block remains at 3% remaining or below.
- Make each new handoff a concise user checkpoint with delivery/acceptance
  states, bounded L1/L2 reading, and an append-only clarification supplement.
- Stop creating, refreshing, or default-reading `docs/project-status.md`;
  optional `docs/agent-context.md` remains the durable context index.

## v0.2.0

- Add the opt-in `$handoff-context-setup` workflow for durable project context;
  V1 handoffs remain supported.
- Preserve completed `PostToolUse` results at the strong threshold, then deny
  later supported local tools in that same turn through `PreToolUse`.
- Document the guard's best-effort limits, including hosted and special tool
  paths that may bypass it, and the safe validation sequence.
- Clarify that local opaque marker and latch files are not `.handoff/` documents.

## v0.1.1

- Fix `UserPromptSubmit` output so ordinary allow decisions emit no invalid JSON.
- Resolve hook commands through `PLUGIN_ROOT` so they work from any task directory.
- Add a one-time protective block when the weekly Coding Plan window has 3% or less remaining.
- Keep the existing five-hour soft nudge from 25% to more than 3% remaining and its one-time 3% protective block.

## v0.1.0

- Initial public release of the Codex handoff plugin and its vendor-neutral handoff skills.
