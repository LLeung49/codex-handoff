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
3. Use the section headings below verbatim and in order. The first three are the
   compact **L0** for first-turn alignment; later sections are on-demand detail.
   Do not use a fixed word limit: retain facts needed to decide the immediate
   action, and link instead of copying background. Omit an empty section only
   after stating an explicit unknown or unresolved gap where it affects that
   action.

### User checkpoint

Keep this short enough to scan first. State the handoff trigger, exact current
breakpoint, the most important verified facts, verified-but-not-yet-accepted
delivery, one active incomplete line, and decisions needed from the user now.
Put an immediate blocker here, not only in a later risk list. Separate a
recorded observation from the current state when the latter is unknown.

### Task contract

State the original objective, approved scope, explicit non-goals, and stop
condition. Preserve the user's meaning; do not infer a broader roadmap.

### Next action and boundary

Name the prerequisite, **one atomic next action**, its expected report or
acceptance evidence, and what must not be opportunistically expanded. Do not
combine a check with a conditional implementation or launch: after reporting
the check, ask for the next scoped decision. A suggestion remains a proposal
until the user authorizes it. If a plan decision is unnecessary but operational
authorization is still needed, say so.

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

For an active process, queue, migration, or long-running batch, record a
**timestamped snapshot** with process/batch identity, observation source,
progress, failures, and relevant resource guardrail. Say "current status is
unknown" after that observation; a recorded PID is not proof it remains live.
The next agent revalidates status before monitoring, restarting, or changing
course, and must not start a duplicate runner from the handoff alone. A verified
progress snapshot does not make an unfinished batch `verified` as a delivery
item; keep the batch `in progress` and describe the snapshot as evidence.

### Minimal reading package

Use progressive disclosure. Use the `### L1: next-action sources` and
`### L2: read conditionally` subheadings verbatim when present. Prefer exact
section links over copied prose or logs.

- **L1: next-action sources** — at most 3 sources. Each source states the
  authorized-action trigger, exact question, authority, and freshness. This is
  not an instruction to load them during initial alignment.
- **L2: read conditionally** — at most 5 sources. Each source states the
  trigger that makes it relevant, the exact question it answers, its authority,
  and freshness. L2 is not permission for automatic reading in initial
  alignment.

Do not put long history, logs, or old specifications in L1 merely because they
are available. Do not cite the handoff itself as an L1 source. Background goals
and design decisions can be cited in L2 and read only when the task calls for
them. Do not hide a fact that blocks the immediate next action in L2 to make
the document shorter. For untracked, ignored, temporary, or machine-local
evidence, mark the link **local-only/untracked** and possibly unavailable to a
fresh agent; keep the minimum decision-critical numbers and uncertainty in L0
so a missing artifact does not erase the checkpoint. Do not copy large logs or
commit them merely to make a reference portable.

### Decision/risk notes

Include only decisions, failed attempts, uncertainties, or known issues that
change the next action. Normally use at most 5 short bullets. Classify any issue
as `blocking`, `follow-up candidate`, or `out of scope`; classification never
authorizes a fix. A normal need for user authorization is an action gate, not
itself a `blocking` defect.

### Scope escalation

- `blocking`: directly prevents an approved acceptance criterion. Record
  evidence that ties it to that criterion and the smallest scoped fix;
  execution still requires approval. A newly found issue does not become
  blocking just because it is nearby or severe-looking.
- `follow-up candidate`: real but non-blocking. Record it and ask whether the
  user authorizes a separate task.
- `out of scope`: unrelated, speculative, or improvement without an approved
  acceptance need. Do not investigate or fix; record only if useful.

No classification grants authorization.

### Trace metadata

Record handoff time, revision, branch, dirty state, and expected base. Mark
unavailable or unverified values rather than guessing. Link to command output
or artifacts; do not paste them. Distinguish committed, dirty, and untracked
evidence; a local-only link may not survive a new machine or checkout.

### Continuation contract

Require a fresh agent to read repo instructions and L0 first, report bounded
alignment and gaps, and wait for scoped work authorization. Do not
automatically read L1 or L2. The user chooses when to start a fresh session
and invoke `$handoff-continue` with this path.

## Clarification supplement

If the original session still has capacity and a fresh agent has a material
question, do not rewrite the parent handoff. Create a new timestamped
clarification supplement at
`.handoff/clarifications/<UTC timestamp>-<slug>.md`; this keeps it out of
automatic parent-handoff selection. It names the parent handoff, each question,
answer, evidence, and uncertainty. The original agent may provide known facts,
evidence, boundaries, or uncertainty only; it must not resume implementation,
run new verification, or expand scope. A fresh agent reads a supplement only
when the user identifies or approves it. If a later handoff refers to a prior
supplement, carry forward only decision-relevant items with their source and
status: `resolved` with evidence, `blocking` only when tied to an approved
acceptance criterion, `pending` clarification, or `separate` proposed work.
Do not copy a whole supplement as a mandatory runbook or convert its proposals
into approvals.

## Boundaries

Do not change `.gitignore`; the repository owner chooses the handoff policy.
Do not use checkpoint preparation to silently expand the task, invent evidence,
or replace an explicit user decision. Do not imply that the handoff, supplement,
or a suggested next action authorizes verification, edits, commits, pushes,
session changes, or future work. These are behavior boundaries, not host-tool
restrictions: use the normal capabilities supplied by the active environment
when the user separately authorizes work.
