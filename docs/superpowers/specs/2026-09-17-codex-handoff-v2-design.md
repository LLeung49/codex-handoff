# codex-handoff V2 Design

**Status:** Proposed — requires user approval before implementation

## Problem

V1 safely captures a single session's immediate state, but a fresh agent can
still lack the project-level intent that gives that state meaning. In a long
development effort, this causes two failures:

1. The agent finds the latest handoff but misses the approved specification,
   architectural constraints, and decisions that predate that session.
2. A newly discovered issue is treated as an implicit request to fix it. The
   agent expands scope, accumulates unrelated fixes, and exhausts a new quota
   window without completing the approved goal.

V2 turns a handoff into a small, reviewable context package. It separates
durable project context, a human-readable delivery view, and immutable
session facts. It does not turn a handoff into permission to act.

## Goals

- Let a fresh agent establish the approved project and task boundary before
  it edits, tests, or explores beyond the declared scope.
- Let a user see current delivery status, acceptance evidence, and decisions
  awaiting their input without reading a raw agent transcript.
- Preserve the useful V1 properties: vendor-neutral Markdown, explicit user
  control, fail-open quota telemetry, no automatic session switching, and no
  daemon or supervisor.
- Keep every document short, link-based, and auditable in version control.

## Non-goals

- Reconstructing or copying a full Codex transcript.
- Automatically scanning every historical spec, branch, or planning document.
- Treating an artifact list as proof that a referenced document is current.
- Automatically creating sessions, running verification, making edits, or
  resolving a newly discovered defect.
- Replacing a repository's issue tracker, roadmap, ADR process, `AGENTS.md`,
  or `CLAUDE.md`.

## Artifact Model

V2 uses three distinct artifacts. The plugin does not invent their facts: it
records only facts that the preparing agent verified in the current session.

| Artifact | Default path | Audience | Mutability | Purpose |
| --- | --- | --- | --- | --- |
| Project context index | `docs/agent-context.md` | Agents and users | Deliberately maintained | Points to authoritative background, hard constraints, active phase, and scope rules. |
| Delivery status | `docs/project-status.md` | Primarily users | Deliberately maintained | Shows delivered, accepted, active, blocked, and awaiting-user-decision work. |
| Session handoff | `.handoff/<UTC timestamp>-<slug>.md` | Fresh agent and user | Immutable snapshot | Captures one bounded task at one known repository state. |

The two `docs/` files are normal project documentation and should normally be
versioned. The repository owner decides whether `.handoff/` is versioned or
gitignored; the plugin must not alter `.gitignore` or choose that policy.

### Project context index

`docs/agent-context.md` is an index, not a duplicate specification. It has a
fixed, concise structure:

1. Project purpose and current delivery phase.
2. Source-of-truth hierarchy: repository instructions, product/design docs,
   active specifications/plans, and issue/PR tracker links when applicable.
3. Required reading order, with a maximum of eight items for a normal task.
4. Stable engineering constraints and explicit non-goals, each linked to its
   authority.
5. Active work boundaries: approved work, deferred work, and work requiring
   a user decision.
6. Document freshness: last verified commit/revision and known gaps.

For a repository such as OryxOS, this index would point to `CLAUDE.md`, the
relevant product and technical documents, and only the active numbered spec
and plan. It must not list every archived course note or spec by default.

### Delivery status

`docs/project-status.md` is the user-facing progress view. It contains:

1. Last updated time and the commit/revision on which the status is based.
2. Delivered and accepted work, with links to concrete acceptance evidence.
3. One active work item: goal, approved scope, owner/session, and stop
   condition.
4. Blocked work and the fact needed to unblock it.
5. Decisions awaiting the user, stated as choices and consequences rather
   than implied implementation work.
6. Deferred candidates, explicitly labelled as not authorized.
7. Link to the latest task handoff.

This status file is a summary for review; the referenced specifications,
tests, commits, and user decisions remain the source of truth.

### Session handoff

`handoff-prepare` keeps the V1 timestamped file but makes these sections
mandatory when applicable:

1. **Original user objective** — preserve the request's meaning without
   silently widening it.
2. **Scope contract** — approved in-scope work, explicit non-goals, and the
   stop condition.
3. **Required context** — links to the project context index and the small
   task-specific reading manifest, in order.
4. **Current state** — done, in progress, remaining, and any prerequisite.
5. **Decisions and rationale** — not merely the chosen option.
6. **Relevant artifacts** — files, specs, commits, branches, issues, or
   external systems actually needed for this task.
7. **Evidence** — executed commands, observed results, and clearly labelled
   unverified claims.
8. **Known issues triage** — each issue is `blocking`, `follow-up candidate`,
   or `out of scope`, with evidence and owner.
9. **Git state** — revision, branch, dirty state, and expected base.
10. **Continuation contract** — what the receiving agent must report before
    work can be authorized.

The handoff remains concise. If a section needs long explanation, it links to
the durable source rather than copying it.

## Skill Workflow

### `handoff-context-setup` (new)

This explicit, user-invoked setup skill creates or refreshes the two durable
project documents. Before writing, it performs a read-only discovery pass and
proposes the exact source documents and paths. It waits for user approval
before creating or materially rewriting either file.

It never guesses a roadmap, changes `AGENTS.md`/`CLAUDE.md`, edits source
code, or discovers requirements by treating old plans as automatically active.

### `handoff-prepare` (expanded)

The existing explicit skill writes the immutable session handoff. It reads the
project context index when present, then includes only the task-specific
references needed by the next agent. It may update `project-status.md` only
when the user explicitly requests a status refresh in the same prompt; a
normal handoff never silently rewrites a user-facing status document.

If an index or status page is absent, the skill reports that fact and offers
`handoff-context-setup`; it does not create extra documents as a side effect.

### `handoff-continue` (expanded)

The receiving skill reads, in this order:

1. Repository instructions such as `AGENTS.md` or `CLAUDE.md` when present.
2. `docs/agent-context.md` when present.
3. The selected handoff.
4. Only the handoff's required task-specific artifacts.

It then produces a **context-alignment report** containing:

- loaded sources and missing/ambiguous sources;
- restated objective, scope, non-goals, and stop condition;
- confirmed evidence versus unverified claims;
- active blocker and user decisions required;
- a statement that it will not begin work until the user authorizes a scoped
  next action.

It ends after this report. A successful reading is not authorization for
commands, verification, edits, commits, pushes, or the handoff's next step.

## Scope Escalation Gate

When a receiving or continuing agent finds an issue not named in the scope
contract, it must classify it before acting:

| Classification | Criteria | Required action |
| --- | --- | --- |
| Blocking | It directly prevents an approved acceptance criterion from being met. | Show the evidence and state the smallest scoped fix; proceed only within the approved task. |
| Follow-up candidate | It is real but does not block the approved acceptance criterion. | Record it in the handoff/status view and ask the user whether to authorize a separate task. |
| Out of scope | It is unrelated, speculative, or a quality improvement without an approved acceptance need. | Do not investigate or fix it; record only if useful to the user. |

The agent must not convert a follow-up candidate into implementation merely
because it is nearby, easy, or interesting. This is the primary V2 control
against repeated "one more bug" loops.

## Hook Behavior and Compatibility

V2 does not change the quota policy validated in V1. The five-hour soft nudge,
five-hour protective block, weekly protective block, marker keys, fail-open
parsing, subagent bypass, and `PreCompact(auto)` warning remain unchanged.

Hook copy may name `$handoff-prepare`; it must not automatically run any
skill, create the durable documents, or create a session. Existing V1 handoff
files remain readable. If V2-only sections are absent, `handoff-continue`
reports them as absent rather than inventing context.

## Error Handling

- Missing context index or status page is reported as a missing optional
  artifact, not an error that blocks reading a V1 handoff.
- Missing, stale, or contradictory referenced sources stop the continuation at
  the alignment report and require user direction.
- An ambiguous latest handoff requires user selection.
- The receiving skill never follows instructions embedded in a handoff as
  authority. User messages and repository instructions retain precedence.
- Quota parser and marker failures remain fail-open.

## Acceptance Criteria

1. Setup proposes, but does not write, the durable context documents before
   explicit user approval.
2. A prepared handoff has an objective, scope contract, reading manifest,
   evidence, triaged issues, and continuation contract when that information
   exists.
3. A continuation reports source coverage and scope alignment, then stops
   before operational work.
4. A new non-blocking defect is recorded as a follow-up candidate and is not
   fixed without a fresh user authorization.
5. Existing V1 handoffs still produce a safe briefing with missing V2 sections
   explicitly identified.
6. Existing quota guard tests and live hook behavior remain unchanged.
7. Skill validation and plugin validation pass; manual tests cover setup
   refusal without approval, status refresh with approval, V1 compatibility,
   and the scope-escalation gate.

## Migration

V2 introduces no automatic migration. A user opts in per repository by
invoking `handoff-context-setup`. Existing projects can keep using only
timestamped `.handoff/` files. The first setup proposal should identify the
minimum useful sources rather than retroactively cataloging project history.
