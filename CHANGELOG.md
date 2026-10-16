# Changelog

## v0.3.5

- Expand `PLUGIN_ROOT` with PowerShell syntax in every Windows hook command.
  Version 0.3.4 used cmd.exe syntax even though Codex executes the Windows
  override through PowerShell, leaving the variable literal and preventing the
  Python script from starting.
- Execute the Windows regression test explicitly through
  `powershell.exe -NoProfile -NonInteractive -Command` instead of relying on
  Python's platform-default shell.
- Add a real macOS process test for the existing POSIX hook command, including
  an unrelated working directory and a space-containing plugin path.

## v0.3.4

- Launch Windows hooks directly with `python` instead of nesting the command in
  `cmd.exe /s /c`, which could preserve quotes around the absolute plugin path
  and make Python resolve it relative to the session working directory.
- Add a Windows-only process test for a plugin path containing spaces, a
  repository-free installed-package test, and Linux/macOS/Windows CI.
- Make the shipped test suite use explicit UTF-8 reads and skip the POSIX-only
  permission check on Windows.
- Standardize machine-facing hook prompts and the resume command on ASCII
  English; reply `continue` to resume paused work.

## v0.3.3

- Raise the one-time five-hour and weekly protective block threshold from 5%
  to 6% remaining; the five-hour soft nudge now ends above 6%.
- Refresh the public README and illustrations to show the user's explicit
  choice, L0-first progressive reading, and optional clarification.

## v0.3.2

- Read hook input as UTF-8 JSON bytes instead of using the Windows Python pipe
  code page. This fixes localized input being misread on Windows; ASCII handoff
  commands were unaffected.

## v0.3.1

- Adjust the one-time protective block threshold from 3% to 5% remaining quota, while keeping the soft warning tier starting at 15%.
- Allow `$codex-handoff:handoff-prepare` and its natural language variants as safe-exit commands that immediately unlock pending blocks.
- Ensure choosing `continue` permanently suppresses further blocks and tool stops in the active session until quota is fully exhausted.

## v0.3.0

- Stop only the active tool loop that first reaches the strong quota warning;
  later turns in the same reset window no longer create a fresh latch.
- After a protective stop, require the user's explicit choice:
  `$handoff-prepare` saves a checkpoint and `continue` resumes the paused task.
- Make handoff skills capability-neutral: they guide progressive context reading
  and authorization boundaries without rejecting normal host read mechanisms.

## v0.2.3

- Correct Windows plugin-root expansion by running the `commandWindows` hook
  through `cmd.exe` and `%PLUGIN_ROOT%`. The previous `$PLUGIN_ROOT` spelling
  was POSIX-only and resolved to an invalid script path on Windows.

## v0.2.2

- Run the hook with `python` on Windows through Codex's `commandWindows`
  override, while retaining `python3` on macOS and Linux. This prevents the
  Microsoft Store `python3.exe` alias from failing when a working `python.exe`
  is on `PATH`.

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
