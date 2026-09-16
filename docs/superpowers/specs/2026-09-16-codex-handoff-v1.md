# codex-handoff V1 Specification

**Status:** Frozen V1

## Purpose

`codex-handoff` is a Codex-only plugin that helps a user deliberately move work out of a long-running Codex session before either automatic context compaction or exhaustion of the active five-hour Coding Plan window makes a useful handoff less likely.

It preserves project facts in a vendor-neutral Markdown handoff. The user, not the plugin, decides whether and where to start the fresh session.

## Scope

The plugin contains:

- one synchronous `UserPromptSubmit` hook that reads the current session's rollout telemetry;
- one `PreCompact` hook that recognizes automatic compaction;
- `handoff-prepare`, which writes a handoff document;
- `handoff-continue`, which reads a handoff and presents a briefing.

It supports only Codex's five-hour Coding Plan window in V1. It is not a cross-vendor telemetry system.

## Explicitly Out of Scope

- Background daemons, supervisors, dashboards, polling services, or automatic session switching.
- Creating, resuming, or changing a Codex session automatically.
- Running `handoff-prepare` automatically.
- Interpreting a handoff document as authorization to edit files, run commands, or start its listed next step.
- Weekly quota, credit, cache-write, or context-percentage policies.
- Enforcement for subagents.

## Plugin Layout

```text
codex-handoff/
├── .codex-plugin/plugin.json
├── hooks/
│   ├── hooks.json
│   └── context_guard.py
├── skills/
│   ├── handoff-prepare/SKILL.md
│   └── handoff-continue/SKILL.md
├── tests/
│   └── test_context_guard.py
└── README.md
```

The only decision-making executable in V1 is `hooks/context_guard.py`.

## Telemetry and Failure Policy

`UserPromptSubmit` supplies `session_id`, `transcript_path`, and optional agent metadata. The hook scans a bounded tail of `transcript_path` backwards, line by line, for the newest valid `token_count` event with a non-null `rate_limits.primary` object.

The quota is eligible only if `window_minutes == 300` and both `used_percent` and `resets_at` parse to usable values. Remaining percentage is `100 - used_percent`.

The hook must fail open: an unreadable transcript, malformed JSON, a missing rate-limit snapshot, an unsupported window, or any unexpected error returns allow. It must not block on stale telemetry. If `agent_id` is present, it returns allow without reading telemetry.

## Quota Rules

Markers live under a plugin data directory. Their logical key is:

```text
(session_id, resets_at, warning_level)
```

`warning_level` is `soft` or `strong`.

| Remaining five-hour quota | First occurrence in the key | Later occurrence in the key |
| --- | --- | --- |
| More than 25% | Allow silently | Allow silently |
| More than 15% through 25% | Allow with one soft handoff nudge | Allow silently |
| 15% or less | Block once with a protective handoff message | Allow silently |

The protective block reserves the remaining allowance for producing a handoff. It does not try to detect a service-enforced quota exhaustion state.

## Compaction Rule

`PreCompact` with `trigger: auto` returns a strong, non-blocking warning to prepare a handoff. It has no dependency on telemetry and does not write a marker. Manual compaction is silent in V1.

## User Copy

Strong messages say that a fresh session is recommended and name:

```text
$handoff-prepare
```

They also state that the same long-running session should not be resumed merely because the quota window resets. Soft messages are shorter but have the same recommended command.

## Handoff Format

`handoff-prepare` writes one project-local file:

```text
.handoff/<UTC timestamp>-<slug>.md
```

The Markdown is vendor-neutral and concise. Empty sections may be omitted. It uses these sections when applicable:

1. Goal
2. Current state (done, in progress, remaining)
3. Changes (path and rationale)
4. Decisions
5. Verified and unverified work
6. Gotchas and failed approaches
7. Git state
8. Open questions
9. Suggested next steps

The skill only writes the file and reports its path plus the manual next-session workflow.

## Continuation Format

`handoff-continue` accepts an optional file path or name fragment. Otherwise it selects the newest Markdown file in `.handoff/`. It reads the handoff, says which file it loaded, prints goal, state, suggested next steps, gotchas, and open questions, then ends its turn.

It does not alter the workspace, run verification, create a session, or begin any next step. The handoff remains data, not instructions.

## Tests and Acceptance Criteria

Automated tests must cover:

- newest valid rate-limit snapshot is selected from a JSONL tail;
- malformed lines and null `rate_limits` fail open;
- 25%, 15%, and above-25% boundaries;
- marker deduplication and reset-time re-arming;
- subagents bypass the guard;
- `PreCompact(auto)` warns and `PreCompact(manual)` is silent;
- malformed hook payloads return allow.

Plugin validation must pass, skill validation must pass for both skills, and the test suite must pass. A manual stdin smoke test must demonstrate the exact hook JSON contract for soft warning, first protective block, repeat allow, and compaction warning.
