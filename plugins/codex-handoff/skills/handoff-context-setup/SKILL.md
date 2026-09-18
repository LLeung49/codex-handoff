---
name: handoff-context-setup
description: Use when the user explicitly requests initial project context setup or a refresh of the durable context index and delivery status.
---

# Set Up Project Context

Prepare a small, link-based context package. A document records verified facts;
it neither invents a roadmap nor authorizes implementation.

## Proposal Before Persistence

1. Perform read-only discovery of repository instructions, existing context
   documents, and the current task's named specifications, plans, and evidence.
   Do not scan all historical specs or branches. Do not treat old plans as active
   merely because they exist or are linked.
2. Present the exact source paths, their authority and freshness, known conflicts,
   and the proposed output paths: `docs/agent-context.md` and
   `docs/project-status.md`. Show a concise draft of both documents in the
   conversation; for existing files, show the proposed changes.
3. Wait for explicit user approval of that proposal before creating or materially
   rewriting either file. Invoking setup alone is not approval of an unseen
   proposal. Before approval, do not persist drafts, create directories, or edit
   any project files. If approval covers only part, write only that part.
4. After approval, write the approved documents and report paths and unresolved
   gaps. Material changes to the approved proposal require renewed approval.

## Context Index Shape

Keep `docs/agent-context.md` concise, with these sections:

1. Project purpose and current delivery phase, grounded in verified sources.
2. A source-of-truth hierarchy: repository instructions, product/design docs,
   approved active specs/plans, and applicable issue/PR tracker links.
3. Required reading order: at most eight sources for a normal task. Choose only
   current, necessary sources; link to details instead of duplicating specs.
4. Stable engineering constraints and explicit non-goals, each linked to authority.
5. Approved work boundaries, deferred work, and work requiring a user decision.
6. Freshness: last verified commit/revision and known gaps. Mark unknown facts as
   unknown; a link alone does not prove a document is current or approved.

## Delivery Status Shape

Keep `docs/project-status.md` user-facing, with these sections:

1. Last updated time and the commit/revision underlying this status.
2. Delivered and accepted work, distinguishing delivery from user acceptance,
   with links to concrete acceptance evidence.
3. One active work item: goal, approved scope, owner/session, and stop condition.
   If none is approved or several compete, report that gap for user selection.
4. Blocked work and the fact needed to unblock it.
5. Decisions awaiting the user: choices and consequences, not implied assignments.
6. Deferred candidates, explicitly labelled not authorized.
7. Link to the latest task handoff, or state that none is available.

Referenced specifications, tests, commits, and user decisions remain the source
of truth; this page is a summary for review.

## Scope Escalation

Classify newly found issues before any action:

- `blocking`: directly prevents an approved acceptance criterion. Show evidence
  and propose the smallest scoped fix; execution must stay within an approved task.
- `follow-up candidate`: real but non-blocking. Record in the proposal and ask
  whether the user authorizes a separate task.
- `out of scope`: unrelated, speculative, or improvement without an approved
  acceptance need. Do not investigate or fix; record only if useful.

No classification grants authorization. Setup never performs the proposed fix.
Do not change `AGENTS.md`, `CLAUDE.md`, source code, or `.gitignore`; the owner
decides whether handoffs are versioned. Do not create, resume, or switch sessions.
