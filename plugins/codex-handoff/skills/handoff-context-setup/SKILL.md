---
name: handoff-context-setup
description: Use when the user explicitly requests initial project context setup or a refresh of the durable context index.
---

# Set Up Project Context

Prepare one small, link-based context index. It records durable verified facts;
it neither invents a roadmap nor authorizes implementation. Current task progress
lives in the newest immutable handoff, not in a second status document.

## Proposal Before Persistence

1. Perform read-only discovery of repository instructions, existing context
   documents, and the current task's named specifications, plans, and evidence.
   Do not scan all historical specs or branches. Do not treat old plans as active
   merely because they exist or are linked.
2. Present the exact source paths, their authority and freshness, known conflicts,
   and the proposed output path: `docs/agent-context.md`. Show a concise draft
   in the conversation; for an existing file, show the proposed changes.
3. Wait for explicit user approval of that proposal before creating or materially
   rewriting the index. Invoking setup alone is not approval of an unseen
   proposal. Before approval, do not persist drafts, create directories, or edit
   any project files.
4. After approval, write the approved index and report its path and unresolved
   gaps. Material changes to the approved proposal require renewed approval.

## Context Index Shape

Keep `docs/agent-context.md` concise, with these sections:

1. Project purpose and durable operating context, grounded in verified sources.
2. A source-of-truth hierarchy: repository instructions, product/design docs,
   approved active specs/plans, and applicable issue/PR tracker links.
3. Required reading order: at most eight sources for a normal task. Choose only
   current, necessary sources; link to details instead of duplicating specs.
4. Stable engineering constraints and explicit non-goals, each linked to authority.
5. Approved work boundaries, deferred work, and work requiring a user decision.
6. Freshness: last verified commit/revision and known gaps. Mark unknown facts as
   unknown; a link alone does not prove a document is current or approved.

## Status-page compatibility

V2.1 does not create or refresh `docs/project-status.md`. Do not default-read
that page either: an existing status page is read only when a selected handoff
lists it in L1 or L2 with its reason or trigger. Do not delete, migrate, or
rewrite an existing status page. Referenced specifications, tests, commits, and
user decisions remain the source of truth; the newest immutable handoff carries
current task state for review.

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
