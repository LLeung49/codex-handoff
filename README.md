# codex-handoff

`codex-handoff` is a Codex plugin for deliberately preparing a handoff before
automatic context compaction or a nearly exhausted Coding Plan quota makes
continued work less useful.

It writes vendor-neutral Markdown handoffs. You decide whether and where to
start a fresh session; it never switches sessions automatically.

## Install from GitHub

Register this public GitHub repository as a Codex marketplace, then install
the plugin. You do not need to clone the repository:

```bash
codex plugin marketplace add LLeung49/codex-handoff --ref main
codex plugin add codex-handoff@codex-handoff
codex plugin list
```

The final command must report `codex-handoff@codex-handoff` as `installed,
enabled`. Start a **new Codex task** after installing; a new task is the
reliable boundary for loading new skills and hooks.

The marketplace registration is a one-time setup per machine. Once registered,
the install command is simply `codex plugin add codex-handoff@codex-handoff`.

## Reinstall or uninstall

If you installed an earlier copy locally, or want to refresh the installed
plugin after a release, remove the installed copy and install it again from
the registered GitHub marketplace:

```bash
codex plugin remove codex-handoff@codex-handoff
codex plugin add codex-handoff@codex-handoff
codex plugin list
```

You normally keep the marketplace registration: it lets you reinstall and
receive future releases without cloning the repository. If you want to remove
both the plugin and this marketplace from the machine, run the following only
after the plugin removal above:

```bash
codex plugin marketplace remove codex-handoff
```

Removing the marketplace does not remove other plugins, but you will need to
register the GitHub marketplace again before installing `codex-handoff` later.
Start a **new Codex task** after installing or reinstalling so Codex loads the
current skills and hooks.

## Develop from a clone

Clone the repository only when you want to inspect, modify, or validate the
plugin source locally.

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

## V2 skills and migration

V1 handoffs continue to work. V2 adds optional durable project context: use
`$handoff-context-setup` only when you want to propose and, after explicit
approval, create durable context documents. It does not create them as a
side effect of a handoff. Use `$handoff-prepare` to make one immutable handoff
snapshot, and `$handoff-continue` in a new task to receive a briefing from it.

The plugin's local data markers are opaque, local, zero-content dedupe and
latch files. They are not project `.handoff/` documents and do not contain
your handoff content.

## Expected quota behavior and limits

- From 25% down to more than 3% remaining, it gives one soft handoff nudge.
- At 3% remaining or below, `PostToolUse` preserves the completed tool result
  and sets a same-turn handoff latch. `PreToolUse` can then deny a later
  supported local tool in that turn with a handoff message.
- The same result-preserving behavior applies when the weekly quota reaches
  3% or below. The weekly quota has no soft-warning tier.
- `PreCompact(auto)` gives a strong warning before automatic compaction, but
  does not block compaction.

The guard is best effort: it cannot observe every model action, and hosted or
special tool paths may bypass it. Invoke `$handoff-prepare` deliberately when
you need a handoff; do not rely on the guard to start one or to switch tasks.

For safe live validation, run the synthetic hook tests first. Then, only if
normal work naturally reaches the 3% threshold, observe one harmless supported
local tool: its completed tool result is preserved and a later supported local
tool in that turn is denied. Do not exhaust quota just to force this check.

## Use the handoff skills

When prompted or when you choose to switch tasks, run `$handoff-prepare` to
write and review a handoff in `.handoff/`. In the fresh task, run
`$handoff-continue` to read that document and receive a briefing. A handoff is
context, not authorization: you must explicitly authorize any edits, commands,
or next steps. Durable V2 documents remain opt-in through
`$handoff-context-setup`.

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
