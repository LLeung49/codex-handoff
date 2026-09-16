# codex-handoff

`codex-handoff` is a Codex-only plugin for deliberately moving work out of a
long-running session before automatic context compaction or a low five-hour
Coding Plan quota makes a useful handoff less likely.

It preserves project facts in a vendor-neutral Markdown handoff. You decide
whether and where to start the fresh session; the plugin never switches
sessions automatically.

## Install

Install this repository as a local Codex plugin, then enable its hooks and
skills in the Codex environment. The plugin manifest points to the `skills/`
skill root.

## Trust the hooks

Review and trust the hooks before enabling them. The synchronous
`UserPromptSubmit` hook reads only bounded rollout telemetry and fails open on
unreadable or malformed data. The `PreCompact` hook warns only for automatic
compaction. Neither hook starts a session, runs `handoff-prepare`, or edits
project files.

## Deliberate new-session workflow

When prompted, run `handoff-prepare` to write a handoff document, review it,
and choose when and where to start a fresh Codex session. In that new session,
run `handoff-continue` to read the handoff and receive a briefing. A handoff is
context, not authorization: it does not authorize edits, commands, or its
listed next step without your explicit direction.

See [`docs/superpowers/specs/2026-09-16-codex-handoff-v1.md`](docs/superpowers/specs/2026-09-16-codex-handoff-v1.md)
for the frozen V1 specification.

## Validate locally

Run the automated tests from the plugin root:

```bash
python3 -m unittest discover -s tests -v
```

The following stdin smoke test uses an isolated rollout transcript and plugin
data directory. It demonstrates a soft warning, a first strong block followed
by an allowed repeat, automatic-compaction advice, and fail-open handling of
malformed input:

```bash
SMOKE_DIR="$(mktemp -d)"
ROLLOUT="$SMOKE_DIR/rollout.jsonl"
MARKERS="$SMOKE_DIR/markers"

printf '%s\n' \
  '{"type":"token_count","rate_limits":{"primary":{"window_minutes":300,"used_percent":75,"resets_at":101}}}' \
  > "$ROLLOUT"
printf '{"session_id":"soft","transcript_path":"%s"}\n' "$ROLLOUT" \
  | PLUGIN_DATA="$MARKERS" python3 ./hooks/context_guard.py

printf '%s\n' \
  '{"type":"token_count","rate_limits":{"primary":{"window_minutes":300,"used_percent":86,"resets_at":202}}}' \
  > "$ROLLOUT"
printf '{"session_id":"strong","transcript_path":"%s"}\n' "$ROLLOUT" \
  | PLUGIN_DATA="$MARKERS" python3 ./hooks/context_guard.py
printf '{"session_id":"strong","transcript_path":"%s"}\n' "$ROLLOUT" \
  | PLUGIN_DATA="$MARKERS" python3 ./hooks/context_guard.py

printf '{"trigger":"auto"}\n' \
  | PLUGIN_DATA="$MARKERS" python3 ./hooks/context_guard.py
printf 'not json\n' | PLUGIN_DATA="$MARKERS" python3 ./hooks/context_guard.py
```

In order, the decisions are `allow` (with a soft handoff suggestion), `block`,
`allow`, `allow` (with automatic-compaction advice), and `allow`.
