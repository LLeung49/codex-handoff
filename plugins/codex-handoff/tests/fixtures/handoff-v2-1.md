# Handoff: quota guard release check

## User checkpoint

- Trigger: five-hour quota is low; the current task stopped before release validation.
- Breakpoint: review the already-verified guard change and ask for release authorization.
- Verified but not accepted: unit tests passed at the recorded revision.
- Incomplete main line: release documentation and user acceptance remain.
- User decision now: accept the verified guard behavior or authorize the release task.

## Task contract

- Objective: publish the approved quota-guard behavior.
- Scope: package metadata, documentation, and validation only.
- Non-goals: changing quota thresholds or adding new hooks.
- Stop condition: user acceptance or a scoped follow-up decision.

## Delivery and acceptance ledger

| Item | State | Evidence | User review action |
| --- | --- | --- | --- |
| quota guard | verified | `tests/test_context_guard.py` passed | Confirm the displayed block message |
| public release | not started | none | Authorize the release task |

## Next action and boundary

- Prerequisite: user chooses acceptance or release authorization.
- Recommended action: update the approved release metadata only.
- Do not expand: do not redesign quota behavior.

## Minimal reading package

### L1: read now
- `README.md` — Why now: public behavior; Authority: repository; Freshness: HEAD.
- `plugins/codex-handoff/.codex-plugin/plugin.json` — Why now: release version; Authority: plugin manifest; Freshness: HEAD.
- `plugins/codex-handoff/tests/test_context_guard.py` — Why now: verification evidence; Authority: test suite; Freshness: HEAD.

### L2: read conditionally
- `docs/release-policy.md` — Trigger: release scope is disputed; Answers: approved release boundaries; Authority: approved policy; Freshness: unknown.
- `docs/old-design.md` — Trigger: a prior decision is questioned; Answers: rejected alternatives; Authority: archived design; Freshness: historical.

## Decision/risk notes

- `follow-up candidate`: improve the handoff schema after this release; not authorized.
- Uncertainty: no user acceptance has been recorded.

## Trace metadata

- Revision: `example`; Branch: `main`; Dirty state: unknown; Expected base: `example`.

## Continuation contract

Read L0 and L1, report alignment and gaps, then wait for scoped user authorization.
