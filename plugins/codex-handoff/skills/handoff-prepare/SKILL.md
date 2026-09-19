---
name: handoff-prepare
description: Use when deliberately preserving a concise, verified project checkpoint before moving work to a fresh session or when a handoff is needed before context compaction.
---

# Prepare a Project Handoff

Create one immutable, concise, vendor-neutral Markdown checkpoint for a later
session. A handoff records facts; it is not permission to act on them. It is a
navigation page, not a replay of repository history or chat history.

## Protocol

1. Read `docs/agent-context.md` when it exists and only the task-specific facts
   verified in the current session. That index is optional and stable; current
   task state belongs in this handoff. It does not create or refresh
   `docs/project-status.md`, and does not default-read that page.
2. Create `.handoff/<UTC timestamp>-<slug>.md` using a sortable UTC timestamp
   and descriptive slug. Never overwrite an existing handoff; choose a unique
   timestamp/slug on collision. Do not rewrite older snapshots.
3. Write the following sections in order. Omit an empty section only after
   stating an explicit unknown or unresolved gap where it affects the next step.

### User checkpoint

Keep this short enough to scan first. State the handoff trigger, exact current
breakpoint, the most important verified facts, verified-but-not-yet-accepted
delivery, one active incomplete line, and decisions needed from the user now.

### Task contract

State the original objective, approved scope, explicit non-goals, and stop
condition. Preserve the user's meaning; do not infer a broader roadmap.

### Delivery and acceptance ledger

Use compact rows: item, state, one evidence reference, and a concrete user
review action. Use exactly one state per item:

- `implemented`: a change exists but has not been verified;
- `verified`: a recorded command, observation, commit, screenshot, or other
  evidence supports the claim;
- `accepted`: the user explicitly accepted the result, with the source of that
  acceptance recorded;
- `in progress`: work stopped within this item;
- `not started`: an approved item has not begun; or
- `blocked`: name the missing fact or decision.

Passing tests can establish `verified`; they never establish `accepted` alone.
Do not invent acceptance.

### Next action and boundary

Name the prerequisite, one recommended scoped action, and what must not be
opportunistically expanded. A suggestion remains a proposal until the user
authorizes it.

### Minimal reading package

Use progressive disclosure. Prefer exact section links over copied prose or
logs.

- **L1: read now** — at most 3 sources. Each source states why it is necessary
  now, its authority, and freshness.
- **L2: read conditionally** — at most 5 sources. Each source states the
  trigger that makes it relevant, the exact question it answers, its authority,
  and freshness. L2 is not permission for automatic reading in initial
  alignment.

Do not put long history, logs, or old specifications in L1 merely because they
are available. Do not hide a fact that blocks the immediate next action in L2
to make the document shorter.

### Decision/risk notes

Include only decisions, failed attempts, uncertainties, or known issues that
change the next action. Normally use at most 5 short bullets. Classify any issue
as `blocking`, `follow-up candidate`, or `out of scope`; classification never
authorizes a fix.

### Scope escalation

- `blocking`: directly prevents an approved acceptance criterion. Record
  evidence and the smallest scoped fix; execution still requires approval.
- `follow-up candidate`: real but non-blocking. Record it and ask whether the
  user authorizes a separate task.
- `out of scope`: unrelated, speculative, or improvement without an approved
  acceptance need. Do not investigate or fix; record only if useful.

No classification grants authorization.

### Trace metadata

Record handoff time, revision, branch, dirty state, and expected base. Mark
unavailable or unverified values rather than guessing. Link to command output
or artifacts; do not paste them.

### Continuation contract

Require a fresh agent to report its L0/L1 alignment, scope, evidence, gaps, and
user decisions before scoped work authorization. The user chooses when to start
a fresh session and invoke `$handoff-continue` with this path.

## Clarification supplement

If the original session still has capacity and a fresh agent has a material
question, do not rewrite the parent handoff. Create a new timestamped
clarification supplement that names the parent handoff, each question, answer,
evidence, and uncertainty. The original agent may provide known facts,
evidence, boundaries, or uncertainty only; it must not resume implementation,
run new verification, or expand scope. A fresh agent reads a supplement only
when the user identifies or approves it.

## Boundaries

Do not change `.gitignore`; the repository owner chooses the handoff policy.
Do not edit source code or repository instructions, create, resume, or switch
sessions. Do not imply that the handoff, supplement, or a suggested next action
authorizes commands, verification, edits, commits, pushes, or future work.
