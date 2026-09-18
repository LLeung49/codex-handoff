# codex-handoff

> Preserve the verified state of a long-running Codex task, then continue deliberately.

<p align="center">
  <img src="assets/codex-handoff-bridge.png" alt="A verified handoff carried from a low-quota workspace to a fresh one" width="100%">
</p>

`codex-handoff` is a Codex plugin for the moment when a task still matters
but its current context or Coding Plan quota is becoming a poor place to keep
working. It helps preserve a small, reviewable handoff package; **you** decide
whether to open a fresh task. It never switches sessions automatically.

## 🚀 Install

Register this public repository as a Codex marketplace, then install the
plugin. No clone is needed:

```bash
codex plugin marketplace add LLeung49/codex-handoff --ref main
codex plugin add codex-handoff@codex-handoff
codex plugin list
```

Confirm that `codex-handoff@codex-handoff` is installed and enabled, then
start a **new Codex task**. A new task is the reliable boundary for loading
new hooks and skills.

To update an existing installation:

```bash
codex plugin remove codex-handoff@codex-handoff
codex plugin add codex-handoff@codex-handoff
codex plugin list
```

Keep the marketplace registration unless you explicitly want to remove it:

```bash
codex plugin marketplace remove codex-handoff
```

## Why codex-handoff?

| Problem | What the plugin protects | What remains your choice |
| --- | --- | --- |
| A task approaches a quota or context boundary | Verified task state can be captured before a fresh task starts | Whether, when, and where to continue |
| A new agent lacks the original scope and decisions | A handoff links the goal, evidence, relevant artifacts, and boundaries | The next authorized action |
| Tool loops keep expanding after quota becomes scarce | The completed tool result is preserved; later supported local tools in that turn can be stopped | Whether to run `$handoff-prepare` |

The plugin is deliberately narrow: no daemon, no supervisor, no automatic
session creation, and no automatic switching.

## How it works

```text
normal task work
      │
      ├─ UserPromptSubmit: one protective prompt block at a strong quota threshold
      ├─ PostToolUse: preserve a completed local-tool result and set a same-turn latch
      └─ PreCompact(auto): give a strong handoff warning
      │
      ▼
$handoff-prepare
      │  writes a vendor-neutral, project-local Markdown snapshot
      ▼
fresh Codex task
      │
      ▼
$handoff-continue
      │  aligns on context, scope, evidence, and open decisions — then stops
      ▼
you authorize the next scoped action
```

The illustration above represents the intended behavior: carry verified work
across the boundary instead of treating the next task as a blank slate.

## Skills

### 1. `$handoff-context-setup`

Use this once per repository when durable project context would help.

It first performs read-only discovery and proposes the exact sources and
content for:

- `docs/agent-context.md` — source hierarchy, constraints, active scope, and reading order
- `docs/project-status.md` — delivered work, active item, blockers, and decisions awaiting you

It waits for explicit approval before creating or materially rewriting either
document.

### 2. `$handoff-prepare`

Use this when you choose to preserve the current task.

It writes one immutable `.handoff/<UTC timestamp>-<slug>.md` snapshot with
the original objective, scope contract, required context, current state,
decision rationale, evidence, issue triage, git state, and continuation
contract. A handoff captures facts; it does not authorize future work.

### 3. `$handoff-continue`

Use this in a fresh task.

It reads repository instructions, the optional context index, the selected
handoff, and only the handoff's listed task artifacts. It then gives a
context-alignment report and stops. It does not run commands, edit files, test,
commit, push, or begin the suggested next step without your explicit direction.

## Quota guard

| Signal | Behavior |
| --- | --- |
| Five-hour quota: 25% to more than 3% remaining | One soft `$handoff-prepare` nudge |
| Five-hour quota: 3% or less remaining | One protective prompt block per session and reset window |
| Weekly quota: 3% or less remaining | One independent protective prompt block per session and reset window |
| A supported local tool observes either strong threshold | Its result remains available; the plugin supplies handoff context and latches that turn |
| Later supported local tool in the same latched turn | `PreToolUse` can deny it before execution |
| Automatic compaction | A strong non-blocking warning |

The guard is **best effort**. It does not observe every model action, and
hosted or special tool paths may bypass local hooks. Do not exhaust quota
to test it. When normal work naturally reaches 3% or less, a safe observation
is to request two harmless local commands; either the prompt guard blocks
before work begins, or the first completed tool result is retained and the
second supported local tool is denied.

Plugin data markers are opaque, local, zero-content dedupe/latch files. They
are not project `.handoff/` documents and do not contain handoff content.

## First check

In a new Codex task, send:

```text
Use $handoff-context-setup only to inspect this repository and propose the context-document sources. Do not create or change files. Stop after the proposal.
```

The expected result is a proposal only—no durable document writes. If Codex
asks to trust the plugin hook, inspect that it is only:

```text
python3 "$PLUGIN_ROOT/hooks/context_guard.py"
```

That hook reads a bounded local telemetry tail, fails open on unreadable or
malformed data, and does not upload telemetry, edit project files, invoke
skills, or switch tasks.

## Development notes

Clone the repository only when you want to modify or validate the plugin:

```bash
git clone https://github.com/LLeung49/codex-handoff.git
cd codex-handoff/plugins/codex-handoff
python3 -m unittest discover -s tests -v
```

For complete plugin and skill validation commands, see
[the plugin source README](plugins/codex-handoff/README.md). The V1 and V2
design records remain available under [docs/superpowers/specs](docs/superpowers/specs/).
