---
name: handoff-prepare
description: Use when deliberately preserving the verified state of a project before moving work to a fresh session or when a handoff is needed before context compaction.
---

# Prepare a Project Handoff

Create one immutable, concise, vendor-neutral Markdown snapshot for a later
session. A handoff records facts; it is not a command to act on them.

## Protocol

1. Read `docs/agent-context.md` when present. Collect project facts verified in
   the current session and only the task-specific references needed next.
   If either durable document is absent (`docs/agent-context.md` or
   `docs/project-status.md`), report the missing optional artifact and offer
   `$handoff-context-setup`; do not create it as a handoff side effect.
2. Create `.handoff/<UTC timestamp>-<slug>.md` using a sortable UTC timestamp
   and descriptive slug. Never overwrite an existing handoff; choose a unique
   timestamp/slug on collision. Do not rewrite older snapshots.
3. Include these sections in order whenever the information exists:
   - **Original user objective**: preserve the request's meaning.
   - **Scope contract**: approved work, explicit non-goals, and stop condition.
   - **Required context**: link to the index and an ordered, bounded reading
     manifest of task-specific sources, their authority, and known freshness.
     Keep normal-task reading to at most eight sources; do not copy or catalogue
     history or treat an old plan as active without approval evidence.
   - **Current state**: done, in progress, remaining, and prerequisites.
   - **Decisions and rationale**: choices and why they were made.
   - **Relevant artifacts**: necessary files, specs, commits, branches, issues,
     or external systems; include changed paths and rationale.
   - **Evidence**: executed commands, observed results, and explicitly labelled
     unverified claims. Record failed approaches and uncertainties as such.
   - **Known issues triage**: classification, evidence, and owner for each issue.
   - **Git state**: revision, branch, dirty state, and expected base; mark
     unavailable or unverified values rather than guessing.
   - **Continuation contract**: require a context-alignment report of sources,
     scope, evidence, blockers, and user decisions before scoped work authorization.
4. Omit empty sections; explicitly label known gaps and uncertain claims.
   Link to durable sources for long explanations. Do not turn proposals into
   completed work or run new verification just to populate the handoff.
5. Report the path. The user chooses when to start a fresh session and invoke
   `$handoff-continue` with that file.

## Status Refresh Gate

Update an existing `docs/project-status.md` only when the user explicitly requests
a status refresh in the same prompt as this handoff. Otherwise write only the
handoff. A prior request, linked plan, or finding is not that same-prompt request.
When authorized, preserve the status structure: update time/revision; delivered
and accepted work with evidence; one active goal/scope/owner/stop condition;
blockers; user decisions; deferred candidates labelled not authorized; latest
handoff link. Do not invent acceptance, replace unrelated entries, or expand work.

## Scope Escalation

- `blocking`: directly prevents an approved acceptance criterion. Record evidence
  and the smallest scoped fix; execution must remain within an approved task.
- `follow-up candidate`: real but non-blocking. Record it in the handoff and ask
  whether the user authorizes a separate task.
- `out of scope`: unrelated, speculative, or improvement without an approved
  acceptance need. Do not investigate or fix; record only if useful.

No classification grants authorization. Preparing a handoff never performs a fix.

## Boundaries

Do not change `.gitignore`; the repository owner chooses the handoff policy.
Do not edit source code or repository instructions, create, resume, or switch sessions.
Do not imply that the document authorizes future edits, commands, verification,
or its suggested next steps.
