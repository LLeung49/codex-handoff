---
name: handoff-prepare
description: Use when deliberately preserving the verified state of a project before moving work to a fresh session or when a handoff is needed before context compaction.
---

# Prepare a Project Handoff

Create one concise, vendor-neutral Markdown handoff for a later session. A
handoff records facts; it is not a command to act on them.

## Protocol

1. Collect only project facts verified in the current session. Do not guess,
   infer, or turn a proposed plan into completed work.
2. Create `.handoff/<UTC timestamp>-<slug>.md` in the project. Use a compact,
   descriptive slug and a UTC timestamp that keeps files chronologically
   sortable.
3. Include only applicable sections, in this order:
   - Goal
   - Current state (done, in progress, remaining)
   - Changes (path and rationale)
   - Decisions
   - Verified and unverified work
   - Gotchas and failed approaches
   - Git state
   - Open questions
   - Suggested next steps
4. Omit empty sections rather than adding placeholders. Mark uncertainties as
   unverified instead of filling gaps with assumptions.
5. Report the handoff path and the manual workflow: start a fresh session when
   the user chooses, then run `$handoff-continue` with the file if desired.

## Boundaries

Write only the handoff document. Do not create, resume, or switch sessions.
Do not imply that the document authorizes future edits, commands, verification,
or its suggested next steps.
