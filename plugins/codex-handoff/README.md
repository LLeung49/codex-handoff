# codex-handoff plugin source

For public installation, hook trust, first use, and update steps, see the
[repository README](../../README.md). This directory is the plugin source
selected by the repository Marketplace.

## Local validation

`codex-handoff` is a Codex-only plugin for deliberately moving work out of a
long-running session before automatic context compaction or a low Coding Plan
quota makes a useful handoff less likely.

For the five-hour quota, it gives one soft nudge from 15% down to above 3% remaining,
then applies one protective block at 3% remaining or below. This leaves room
to use nearly the whole window while preserving a final turn for handoff.

For the weekly quota, it has no soft-warning tier: it applies one independent
protective block at 3% remaining or below. Each window deduplicates against
its own reset time; if both reach the threshold together, Codex receives one
block that reports both conditions.

It preserves project facts in a vendor-neutral Markdown handoff. You decide
whether and where to start the fresh session; the plugin never switches
sessions automatically.

## V2.1 progressive handoff context and migration

V1 handoffs still work unchanged. V2.1 makes a new handoff a compact user
checkpoint: it distinguishes implemented, verified, and user-accepted delivery,
then uses a progressive reading package. L1 has at most 3 read-now sources;
L2 has at most 5 conditional sources and is not read during initial alignment.

Run `$handoff-context-setup` when you want a read-only proposal for the optional
durable `docs/agent-context.md` index. It does not create or refresh
`docs/project-status.md`, and handoff workflows do not default-read that page.
Use `$handoff-prepare` for one immutable checkpoint and `$handoff-continue` in
a fresh task for its L0/L1 briefing and up-to-three targeted questions.

The plugin's data markers are opaque, local, zero-content dedupe/latch files.
They are not project `.handoff/` documents and contain no handoff content.

## V2 quota guard limits

At the strong threshold, `PostToolUse` keeps a completed tool result available
and records a same-turn latch. A subsequent supported local tool can be denied
by `PreToolUse` with a handoff message. This guard is best effort: it cannot
observe every model action, and hosted or special tool paths may bypass it.
Invoke `$handoff-prepare` deliberately when you need a handoff; the guard does
not switch sessions automatically.

For safe live validation, run synthetic hook tests first. Then, only when
normal work naturally reaches the threshold, observe one harmless supported
local tool; do not consume quota just to force the case.

## Deliberate new-session workflow

When prompted, run `$handoff-prepare` to write a handoff document, review it,
and choose when and where to start a fresh Codex session. In that new session,
run `$handoff-continue` to read the handoff and receive a briefing. A handoff is
context, not authorization: it does not authorize edits, commands, or its
listed next step without your explicit direction.

## Validate locally

Run these commands from the plugin root. The hook and unit tests use only the
Python standard library. The Codex plugin and skill validators additionally
require PyYAML. Create an isolated, ignored environment with the bundled Codex
workspace Python (Python 3.12 on this machine):

```bash
BUNDLED_PYTHON="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
"$BUNDLED_PYTHON" -m venv work/validator-venv
work/validator-venv/bin/python -m pip install 'PyYAML==6.0.3'

VALIDATOR_PYTHON="$PWD/work/validator-venv/bin/python"
SYSTEM_SKILLS="${CODEX_HOME:-$HOME/.codex}/skills/.system"
"$VALIDATOR_PYTHON" -m unittest discover -s tests -v
"$VALIDATOR_PYTHON" "$SYSTEM_SKILLS/plugin-creator/scripts/validate_plugin.py" .
"$VALIDATOR_PYTHON" "$SYSTEM_SKILLS/skill-creator/scripts/quick_validate.py" skills/handoff-context-setup
"$VALIDATOR_PYTHON" "$SYSTEM_SKILLS/skill-creator/scripts/quick_validate.py" skills/handoff-prepare
"$VALIDATOR_PYTHON" "$SYSTEM_SKILLS/skill-creator/scripts/quick_validate.py" skills/handoff-continue
```

The PyYAML installation requires access to your configured Python package
index on first setup. If your Codex runtime or system skills live elsewhere,
adjust `BUNDLED_PYTHON` or `SYSTEM_SKILLS` to their installed locations. A local
Python 3.10+ can also create the environment. All five validation commands
must exit successfully; the validators print `Plugin validation passed` and
`Skill is valid!` for each skill.

The following stdin smoke test uses an isolated rollout transcript and plugin
data directory. It demonstrates a soft warning, a first strong block followed
by an allowed repeat, automatic-compaction advice, and fail-open handling of
malformed input and expired telemetry. Reset timestamps are generated relative
to the current time, and the records use the real Codex `event_msg` envelope:

```bash
SMOKE_DIR="$(mktemp -d)"
ROLLOUT="$SMOKE_DIR/rollout.jsonl"
MARKERS="$SMOKE_DIR/markers"
RESET_AT=$(( $(date +%s) + 18000 ))

printf '{"type":"event_msg","payload":{"type":"token_count","rate_limits":{"primary":{"window_minutes":300,"used_percent":85,"resets_at":%s}}}}\n' "$RESET_AT" \
  > "$ROLLOUT"
printf '{"session_id":"soft","transcript_path":"%s"}\n' "$ROLLOUT" \
  | PLUGIN_DATA="$MARKERS" "$VALIDATOR_PYTHON" ./hooks/context_guard.py

printf '{"type":"event_msg","payload":{"type":"token_count","rate_limits":{"primary":{"window_minutes":300,"used_percent":86,"resets_at":%s}}}}\n' "$RESET_AT" \
  > "$ROLLOUT"
printf '{"session_id":"strong","transcript_path":"%s"}\n' "$ROLLOUT" \
  | PLUGIN_DATA="$MARKERS" "$VALIDATOR_PYTHON" ./hooks/context_guard.py
printf '{"session_id":"strong","transcript_path":"%s"}\n' "$ROLLOUT" \
  | PLUGIN_DATA="$MARKERS" "$VALIDATOR_PYTHON" ./hooks/context_guard.py

printf '{"trigger":"auto"}\n' \
  | PLUGIN_DATA="$MARKERS" "$VALIDATOR_PYTHON" ./hooks/context_guard.py
printf 'not json\n' | PLUGIN_DATA="$MARKERS" "$VALIDATOR_PYTHON" ./hooks/context_guard.py

EXPIRED_AT=$(( $(date +%s) - 1 ))
printf '{"type":"event_msg","payload":{"type":"token_count","rate_limits":{"primary":{"window_minutes":300,"used_percent":86,"resets_at":%s}}}}\n' "$EXPIRED_AT" \
  > "$ROLLOUT"
printf '{"session_id":"expired","transcript_path":"%s"}\n' "$ROLLOUT" \
  | PLUGIN_DATA="$SMOKE_DIR/expired-markers" "$VALIDATOR_PYTHON" ./hooks/context_guard.py
test ! -e "$SMOKE_DIR/expired-markers"
```

In order, the decisions are `allow` (with a soft handoff suggestion), `block`,
`allow`, `allow` (with automatic-compaction advice), `allow`, and `allow`.
The final check confirms expired telemetry creates no marker directory.
