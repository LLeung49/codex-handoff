# codex-handoff

> Preserve the verified state of a long-running Codex task, then continue deliberately.

`codex-handoff` is a Codex plugin for the moment when a task still matters
but its current context or Coding Plan quota is becoming a poor place to keep
working. It helps preserve a small, reviewable handoff package; **you** decide
whether to open a fresh task. It never switches sessions automatically.

Most people should never need it: if your Coding Plan quota comfortably covers
your work, there is nothing to hand off. It exists for long-running tasks that
outlive a five-hour window. Copying a transcript or pointing a new agent at a
spec preserves raw material, not a bounded shared state; the next agent can
drift, repeat work, miss priorities, and burn through its own quota rebuilding
context. Waiting for the next window can still carry that same context cost.

<p align="center">
  <img src="assets/codex-handoff-00-origin-story.png" alt="额度充足时一个小黑完成大任务；额度有限时多个小黑先封装标准交接单，再由下一位继续" width="100%">
</p>

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
| A long task outlives a quota or context window | Verified task state can be captured before a fresh task starts | Whether, when, and where to continue |
| A new agent lacks the original scope and decisions | A handoff links the goal, evidence, relevant artifacts, and boundaries | The next authorized action |
| Tool loops keep expanding after quota becomes scarce | The completed tool result is preserved; later supported local tools in that turn can be stopped | Whether to run `$handoff-prepare` |
| A new window would otherwise begin by rebuilding context | A small, reviewable snapshot replaces an unbounded transcript replay | Whether to run `$handoff-prepare` |

The plugin is deliberately narrow: no daemon, no supervisor, no automatic
session creation, and no automatic switching.

<p align="center">
  <img src="assets/codex-handoff-01-carry-forward.png" alt="小黑将目标、证据和边界带往新会话" width="100%">
</p>

It carries verified task state across the boundary instead of asking a fresh
agent to reconstruct the task from a blank slate.

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

The carry-forward illustration represents the intended behavior: carry verified work
across the boundary instead of treating the next task as a blank slate.

<p align="center">
  <img src="assets/codex-handoff-02-handoff-envelope.png" alt="小黑将目标、证据和边界封入 handoff，并等待下一位 agent 获得授权" width="100%">
</p>

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

<p align="center">
  <img src="assets/codex-handoff-03-quota-guard.png" alt="小黑保存已完成结果，并在额度低时停止后续工具调用" width="100%">
</p>

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
