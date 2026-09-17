# codex-handoff

`codex-handoff` is a Codex plugin for deliberately preparing a handoff before
automatic context compaction or a nearly exhausted Coding Plan quota makes
continued work less useful.

It writes vendor-neutral Markdown handoffs. You decide whether and where to
start a fresh session; it never starts or switches sessions automatically.

## Install from a clone

Use Codex CLI to add this repository as a local Marketplace, then install its
plugin:

```bash
git clone https://github.com/LLeung49/codex-handoff.git
cd codex-handoff
codex plugin marketplace add "$PWD"
codex plugin add codex-handoff@codex-handoff
codex plugin list
```

The final command must report `codex-handoff@codex-handoff` as `installed,
enabled`. Start a **new Codex task** after installing; a new task is the
reliable boundary for loading new skills and hooks.

## First live check

In that new task, send this non-destructive request:

```text
Use handoff-continue only to explain whether a handoff document authorizes commands. Do not read or change files.
```

If Codex asks to trust `python3 "$PLUGIN_ROOT/hooks/context_guard.py"`, inspect and approve
it. This is the plugin's only executable hook. It reads bounded local rollout
telemetry and fails open on unreadable or malformed data; it does not upload
telemetry, edit project files, run a handoff skill, or switch sessions.

A successful first check means Codex recognizes `handoff-continue` and answers
that a handoff document alone does not authorize commands or edits. When more
than 25% of the five-hour quota remains, the guard intentionally stays silent.

## Expected quota behavior

- From 25% down to more than 3% remaining, it gives one soft handoff nudge.
- At 3% remaining or below, it blocks one prompt per session and quota reset
  window so you can preserve a final turn for handoff.
- At 3% remaining or below for the weekly quota, it also blocks one prompt per
  session and weekly reset window. The weekly quota has no soft-warning tier.
- `PreCompact(auto)` gives a strong warning before automatic compaction, but
  does not block compaction.

These outcomes depend on live account telemetry and should be observed during
normal work, not forced in an active account. If both windows are at the 3%
threshold, the plugin returns one block that names both conditions.

## Use the handoff skills

When prompted or when you choose to switch tasks, run `handoff-prepare` to
write and review a handoff in `.handoff/`. In the fresh task, run
`handoff-continue` to read that document and receive a briefing. A handoff is
context, not authorization: you must explicitly authorize any edits, commands,
or next steps.

## Develop or update the plugin

After changing plugin code in `plugins/codex-handoff`, validate it and update
the cachebuster before reinstalling:

```bash
cd plugins/codex-handoff
python3 -m unittest discover -s tests -v
python3 "$HOME/.codex/skills/.system/plugin-creator/scripts/update_plugin_cachebuster.py" .
codex plugin add codex-handoff@codex-handoff
```

For the plugin and skill validators, follow the commands in the plugin source
README: [`plugins/codex-handoff/README.md`](plugins/codex-handoff/README.md).

## V1 specification

The frozen V1 behavior is documented in
[`docs/superpowers/specs/2026-09-16-codex-handoff-v1.md`](docs/superpowers/specs/2026-09-16-codex-handoff-v1.md).
