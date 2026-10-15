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

## Next action and boundary

- Prerequisite: user chooses acceptance or release authorization.
- One action if authorized: update the approved release metadata only, then report the diff for review.
- Do not expand: do not redesign quota behavior or publish automatically.

## Delivery and acceptance ledger

| Item | State | Evidence | User review action |
| --- | --- | --- | --- |
| quota guard | verified | `tests/test_context_guard.py` passed | Confirm the displayed block message |
| public release | not started | none | Authorize the release task |

## Minimal reading package

### L1: next-action sources
- `README.md` — Trigger: release metadata update authorized; Answers: current public behavior; Authority: repository; Freshness: HEAD.
- `plugins/codex-handoff/.codex-plugin/plugin.json` — Trigger: release metadata update authorized; Answers: current version; Authority: plugin manifest; Freshness: HEAD.
- `plugins/codex-handoff/tests/test_context_guard.py` — Trigger: guard evidence needed for acceptance; Answers: tested behavior; Authority: test suite; Freshness: HEAD.

### L2: read conditionally
- `docs/release-policy.md` — Trigger: release scope is disputed; Answers: approved release boundaries; Authority: approved policy; Freshness: unknown.
- `docs/old-design.md` — Trigger: a prior decision is questioned; Answers: rejected alternatives; Authority: archived design; Freshness: historical.

## Decision/risk notes

- `follow-up candidate`: improve the handoff schema after this release; not authorized.
- Uncertainty: no user acceptance has been recorded.

## Trace metadata

- Revision: `example`; Branch: `main`; Dirty state: unknown; Expected base: `example`.

## Continuation contract

Read repository instructions and L0, report alignment and gaps, then wait for scoped user authorization. Do not automatically read L1 or L2.
