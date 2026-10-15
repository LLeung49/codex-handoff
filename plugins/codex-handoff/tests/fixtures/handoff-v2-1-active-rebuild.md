# Handoff: active staging rebuild (synthetic regression case)

## User checkpoint

- Trigger: quota guard paused a long-running staging rebuild monitoring task.
- Observed at `2026-10-14T17:42:52Z`: batch `market-full-qmt-20261014`, PID 19304, 2,657/6,958 completed and 23 failed, according to the runner progress record. The process was alive at that observation; current status unknown.
- The expected-universe gate is verified but not accepted. Audit hardening is dirty with 7 passing and 1 failing test. No production cutover has been accepted.
- Immediate blocker: before further monitoring, confirm this is still the same batch; do not infer liveness from the old PID.
- Decision now: no new data-handling design choice; scoped authorization is still needed for a status check.

## Task contract

- Objective: complete the approved staging rebuild and evidence review before proposing a separate production cutover.
- Current scope: observe the existing batch and report progress or failure.
- Non-goals: a second runner, audit repair, production cutover, or downstream migration.
- Stop condition: report the current verified state and ask for the next decision.

## Next action and boundary

- Prerequisite: user authorizes one read-only status check.
- One action: verify the batch identity, process, checkpoint, failures, and remaining disk; report the observation without restarting anything.
- Boundary: do not start a new rebuild, fix the 23 failures, edit audit code, or cut over as part of this check.

## Delivery and acceptance ledger

| Item | State | Evidence | User review action |
| --- | --- | --- | --- |
| Expected-universe gate | verified | recorded test result in parent task | Review evidence before acceptance |
| Staging rebuild | in progress | `2026-10-14T17:42:52Z` progress record for `market-full-qmt-20261014`; current state unknown | Authorize current-state check |
| Audit hardening | in progress | dirty change; 7 pass, 1 fail at handoff | Decide whether to open a separate repair task |

## Minimal reading package

### L1: next-action sources
- `.worktrees/recovery/reports/progress.json` — Trigger: status check authorized; Answers: latest batch progress; Authority: runner output; Freshness: local-only/untracked, recheck on read.

### L2: read conditionally
- `docs/rebuild-design.md` — Trigger: a rebuild design decision is disputed; Answers: approved rebuild boundaries; Authority: design record; Freshness: historical.
- `.worktrees/recovery/reports/failed-codes.json` — Trigger: user authorizes failure triage; Answers: which codes failed; Authority: runner output; Freshness: local-only/untracked, recheck on read.

## Decision/risk notes

- Prior safety supplement: expected-universe gate `resolved` with recorded test evidence; audit hardening `pending` because one test fails; cutover preflight `separate` because cutover is not in this task. Source: `clarifications/20261014T142032Z-safety.md` (user-approved only; not auto-loaded).
- Uncertainty: current batch status is unknown; the old progress observation cannot justify a restart or cutover.

## Trace metadata

- Handoff time: `2026-10-14T17:44:24Z`; branch: `recovery`; revision/expected base: unverified.
- Dirty: audit hardening is uncommitted. Reports are untracked and machine-local; they might not exist in another checkout. Decision-critical numbers are preserved in L0.

## Continuation contract

Read repository instructions and L0 first. Do not automatically read L1 or L2. Report the snapshot as historical, ask for the single status-check authorization, then revalidate batch identity before monitoring. This handoff grants no operational permission.
