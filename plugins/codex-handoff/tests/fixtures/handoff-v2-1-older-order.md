# Handoff: older V2.1 layout compatibility (synthetic)

## User checkpoint

At 2026-10-14T17:42:52Z batch `market-full-qmt-20261014` was observed as PID 19304, 2,657/6,958 complete, 23 failed. Its present state is unknown. The next step is a current-state check, if authorized.

## Task contract

Current scope is monitoring the existing staging runner. Do not launch another runner or cut over production.

## Delivery and acceptance ledger

| Item | State | Evidence | User review |
| --- | --- | --- | --- |
| Staging rebuild | in progress | recorded snapshot | authorize fresh status check |

## Next action and boundary

Request authorization for one read-only status check of the same batch, then report the result. No restart or repair.

## Minimal reading package

### L1: read now
- `.worktrees/recovery/reports/progress.json` — historical runner report; local-only/untracked and potentially stale.

### L2: read conditionally
- `docs/rebuild-design.md` — Trigger: design dispute; Answers: approved boundaries; Authority: design record; Freshness: historical.

## Continuation contract

Read L0 and L1, then act on the next step.
