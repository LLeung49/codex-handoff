# codex-handoff V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver `codex-handoff` V2: a deliberate, reviewable context package for handoffs plus a quota guard that stops a supported local-tool loop after a tool observes a 3%-or-less Coding Plan quota, without discarding that tool's result.

**Architecture:** Keep the standard-library Python hook as the sole quota component. Refactor it into event-specific decisions for `UserPromptSubmit`, `PreCompact`, `PostToolUse`, and `PreToolUse`. Durable Markdown gives a project context index and user status page; an immutable `.handoff/` snapshot binds one task to its verified evidence. Skills remain explicitly invoked and never turn context into permission.

**Tech Stack:** Python 3 standard library, `unittest`, JSON, Markdown, Codex plugin manifest and hook configuration.

**Spec:** `docs/superpowers/specs/2026-09-17-codex-handoff-v2-design.md`

## Global Constraints

- Preserve all V1 behavior: five-hour soft nudge at 25% through greater than 3%, one five-hour block at 3% or below, one weekly block at 3% or below, auto-`PreCompact` warning, subagent bypass, bounded-tail parsing, and fail-open behavior.
- Maintain a separate marker namespace for each quota window. Strong quota deduplication is keyed by session, reset time, warning level, and window.
- The tool-loop latch is keyed by `(session_id, turn_id, resets_at, "tool-stop", quota_window)`; it applies only to later supported local tool calls in that same turn.
- `PostToolUse` must not emit `continue: false`, `decision: block`, or any output form that replaces a completed tool result. It may add feedback and create a latch.
- `PreToolUse` enforces only an existing same-turn latch. It does not independently read quota or deny a fresh user handoff turn.
- A post-tool strong event must also claim the normal strong-warning marker so the next user message can run `$handoff-prepare` instead of being needlessly blocked again.
- If hook payload, rollout telemetry, marker storage, or a required ID is absent or invalid, allow the event. Never create a marker from invalid or expired telemetry.
- Supported local Codex tools are guarded best-effort only. Hosted tools, special paths that bypass hooks, and model-only work are documented limitations, not hidden guarantees.
- `handoff-continue` remains read-only and stops after alignment. A handoff, context index, status page, or artifact list never authorizes commands, edits, verification, commits, pushes, or a suggested next step.
- Do not create a daemon, supervisor, dashboard, automatic session switcher, automatic durable-document rewrite, or unsolicited `.gitignore` change.

---

## File Structure

- `plugins/codex-handoff/hooks/context_guard.py`: bounded rollout reader, quota classification, marker/latch storage, event router, and event-specific output formatter.
- `plugins/codex-handoff/hooks/hooks.json`: synchronous registrations for all four lifecycle events.
- `plugins/codex-handoff/tests/test_context_guard.py`: unit and JSON-contract tests for parser, V1 decisions, tool-loop behavior, configuration, and skill/document contracts.
- `plugins/codex-handoff/skills/handoff-context-setup/SKILL.md`: explicit two-phase proposal/approval workflow for durable context documents.
- `plugins/codex-handoff/skills/handoff-prepare/SKILL.md`: immutable session snapshot protocol.
- `plugins/codex-handoff/skills/handoff-continue/SKILL.md`: bounded read-only context alignment protocol.
- `README.md` and `plugins/codex-handoff/README.md`: public installation, behavior, limitations, validation, and migration guidance.
- `CHANGELOG.md` and `plugins/codex-handoff/.codex-plugin/plugin.json`: V2 release record and plugin version.

## Task 1: Establish event-aware decision and storage primitives

**Files:**
- Modify: `plugins/codex-handoff/hooks/context_guard.py`
- Modify: `plugins/codex-handoff/tests/test_context_guard.py`

**Interfaces:**
- Preserve `latest_primary_rate_limit()`, `latest_secondary_rate_limit()`, and `quota_warning()` unchanged in behavior.
- Add `handle_user_prompt(payload: dict, data_dir: Path) -> dict` and `handle_precompact(payload: dict, data_dir: Path) -> dict`.
- Add marker helpers that can atomically claim and test both quota-warning keys and turn-latch keys without exposing user identifiers in filenames.
- Keep `handle_event(payload, data_dir)` as the event router for the command entry point and existing callers.

- [ ] **Step 1: Write failing tests for event routing and scoped marker keys**

Add tests that assert all of the following before changing hook code:

```python
def test_router_keeps_v1_prompt_semantics():
    decision = handle_event(prompt_payload(..., used_percent=97), marker_dir)
    self.assertEqual(decision["decision"], "block")

def test_turn_latch_key_is_turn_specific():
    claim_turn_latch(marker_dir, "s", "turn-a", RESET, "five-hour")
    self.assertTrue(turn_latch_exists(marker_dir, "s", "turn-a", RESET, "five-hour"))
    self.assertFalse(turn_latch_exists(marker_dir, "s", "turn-b", RESET, "five-hour"))

def test_missing_turn_or_session_never_creates_a_latch():
    self.assertEqual(handle_post_tool_use({"turn_id": "t"}, marker_dir), ALLOW)
    self.assertFalse(marker_dir.exists())
```

- [ ] **Step 2: Run the focused tests and confirm they fail for the intended missing interfaces**

Run:

```bash
cd plugins/codex-handoff
python3 -m unittest tests.test_context_guard.DecisionTests -v
```

Expected: failures refer to the new event-specific/latch interfaces, not to a changed V1 quota boundary.

- [ ] **Step 3: Refactor the decision layer without changing parser behavior**

Split the current generic `handle_event()` body into explicit handlers. Keep a small router based on `hook_event_name`; retain a safe backward-compatible default for direct V1 test payloads that omit the event name. Generalize the hashed marker helper instead of inventing a second storage mechanism:

```python
def _marker_path(data_dir: Path, *key_parts: object) -> Path: ...
def _claim_marker(data_dir: Path, *key_parts: object) -> bool: ...
def _marker_exists(data_dir: Path, *key_parts: object) -> bool: ...
```

Keep the documented warning keys as `(session_id, resets_at, warning_level, window)` and latch keys as `(session_id, turn_id, resets_at, "tool-stop", window)`; their differing arity prevents collisions. Preserve atomic exclusive creation and `0600` permissions. All exceptions return `ALLOW`.

- [ ] **Step 4: Run parser, V1 decision, and new primitive tests**

Run:

```bash
python3 -m unittest tests.test_context_guard.TelemetryTests tests.test_context_guard.DecisionTests -v
```

Expected: PASS, including existing tests for malformed tails, expired resets, soft-warning deduplication, five-hour strong blocks, and weekly strong blocks.

- [ ] **Step 5: Commit the isolated refactor**

```bash
git add plugins/codex-handoff/hooks/context_guard.py plugins/codex-handoff/tests/test_context_guard.py
git commit -m "refactor: route handoff guard by hook event"
```

## Task 2: Detect quota exhaustion after a completed local tool

**Files:**
- Modify: `plugins/codex-handoff/hooks/context_guard.py`
- Modify: `plugins/codex-handoff/tests/test_context_guard.py`

**Interfaces:**
- Add `handle_post_tool_use(payload: dict, data_dir: Path) -> dict`.
- It returns an internal non-blocking advisory decision, for example `{ "decision": "allow", "reason": ..., "tool_stop": True }`, only after it has seen a valid, unexpired strong quota snapshot and has claimed a new turn latch.
- It must claim the normal strong warning marker for every strong quota window it observes, even though it never returns a prompt block.

- [ ] **Step 1: Write failing post-tool behavior tests**

Create helpers that write a direct `event_msg` token-count rollout and include `session_id`, `turn_id`, `transcript_path`, and `hook_event_name: "PostToolUse"`. Test:

1. Five-hour `used_percent: 97` creates a five-hour latch and supplies a handoff message.
2. Weekly `used_percent: 97` creates a weekly latch and supplies the weekly message.
3. When both are strong, both latches are claimed and the message names both conditions.
4. A healthy snapshot, expired reset, invalid latest snapshot, missing `turn_id`, subagent payload, unreadable rollout, and marker-storage exception all fail open with no latch.
5. After a post-tool detection, a matching `UserPromptSubmit` in the same session/reset allows: the post-tool path has already consumed the strong-warning marker.

- [ ] **Step 2: Run only the new post-tool tests**

Run:

```bash
python3 -m unittest tests.test_context_guard.ToolLoopTests.test_post_tool_use -v
```

Expected: FAIL because post-tool behavior is not implemented yet.

- [ ] **Step 3: Implement detection that preserves completed results**

Reuse the current `primary` and `secondary` snapshot selection and the existing quota threshold classifier. For each valid strong snapshot:

1. claim `(session_id, resets_at, "strong", window)`;
2. claim `(session_id, turn_id, resets_at, "tool-stop", window)`;
3. only emit a new advisory when at least one latch was newly claimed.

Do not branch on tool result contents; its successful completion is already authoritative. Do not use an older snapshot when a later relevant snapshot is invalid or null. Do not persist a latch at soft-warning levels.

- [ ] **Step 4: Run the post-tool and regression tests**

Run:

```bash
python3 -m unittest tests.test_context_guard.ToolLoopTests tests.test_context_guard.DecisionTests -v
```

Expected: PASS. The established V1 one-time behavior must remain unchanged.

- [ ] **Step 5: Commit**

```bash
git add plugins/codex-handoff/hooks/context_guard.py plugins/codex-handoff/tests/test_context_guard.py
git commit -m "feat: detect quota exhaustion after local tools"
```

## Task 3: Enforce the same-turn tool-loop latch and wire valid hook outputs

**Files:**
- Modify: `plugins/codex-handoff/hooks/context_guard.py`
- Modify: `plugins/codex-handoff/hooks/hooks.json`
- Modify: `plugins/codex-handoff/tests/test_context_guard.py`

**Interfaces:**
- Add `handle_pre_tool_use(payload: dict, data_dir: Path) -> dict`.
- Change `format_hook_output(payload: dict, decision: dict) -> dict | None` to be event-aware.
- Register `PreToolUse` and `PostToolUse` with the existing synchronous Python command, while preserving `UserPromptSubmit` and `PreCompact`.

- [ ] **Step 1: Write failing contract tests before implementation**

Use strict object comparisons, not only substring checks:

```python
def test_pre_tool_denies_only_same_turn_latch(self):
    claim_turn_latch(marker_dir, "s", "t1", RESET, "five-hour")
    output = format_hook_output(
        {"hook_event_name": "PreToolUse", "session_id": "s", "turn_id": "t1"},
        handle_pre_tool_use(...),
    )
    self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
    self.assertEqual(handle_pre_tool_use(payload_for("t2"), marker_dir), ALLOW)

def test_post_tool_message_does_not_replace_result(self):
    output = format_hook_output(post_tool_payload, post_decision)
    self.assertNotIn("decision", output)
    self.assertNotIn("continue", output)
    self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "PostToolUse")
```

Also assert that `hooks.json` registers exactly `UserPromptSubmit`, `PreCompact`, `PostToolUse`, and `PreToolUse`, each using `$PLUGIN_ROOT/hooks/context_guard.py`.

- [ ] **Step 2: Run focused output/configuration tests and confirm expected failure**

Run:

```bash
python3 -m unittest tests.test_context_guard.ToolLoopOutputTests tests.test_context_guard.HookConfigurationTests -v
```

Expected: FAIL because the old formatter only emits prompt-compatible output and the two events are absent.

- [ ] **Step 3: Implement event-specific Codex output**

Produce these shapes:

```python
# PostToolUse: original completed tool result remains available.
{
    "systemMessage": message,
    "hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": message,
    },
}

# PreToolUse: reject a later supported local tool before execution.
{
    "systemMessage": message,
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": message,
    },
}
```

For `UserPromptSubmit`, retain `{ "decision": "block", "reason": message }`; soft prompts and auto compaction remain non-blocking `systemMessage` output. Emit no JSON for a plain allow. Keep all hook commands synchronous and use an all-tool matcher supported by Codex hook configuration.

- [ ] **Step 4: Run the hook behavior suite**

Run:

```bash
python3 -m unittest tests.test_context_guard.ToolLoopTests tests.test_context_guard.ToolLoopOutputTests tests.test_context_guard.HookConfigurationTests -v
```

Expected: PASS. In particular, a post-tool advisory is not a hidden `continue: false`, and a different/new turn is not denied.

- [ ] **Step 5: Commit**

```bash
git add plugins/codex-handoff/hooks/context_guard.py plugins/codex-handoff/hooks/hooks.json plugins/codex-handoff/tests/test_context_guard.py
git commit -m "feat: stop latched local tool loops"
```

## Task 4: Build the V2 context-package skills and their executable contracts

**Files:**
- Create: `plugins/codex-handoff/skills/handoff-context-setup/SKILL.md`
- Modify: `plugins/codex-handoff/skills/handoff-prepare/SKILL.md`
- Modify: `plugins/codex-handoff/skills/handoff-continue/SKILL.md`
- Modify: `plugins/codex-handoff/tests/test_context_guard.py`

**Interfaces:**
- `handoff-context-setup` performs read-only discovery, proposes exact sources and a draft shape, then waits for explicit approval before creating or materially rewriting `docs/agent-context.md` and `docs/project-status.md`.
- `handoff-prepare` creates one immutable `.handoff/<UTC timestamp>-<slug>.md`; it updates `docs/project-status.md` only when the user explicitly requested a status refresh in the same prompt.
- `handoff-continue` reads a bounded source order and returns a context-alignment report, then stops.

- [ ] **Step 1: Add failing content-contract tests**

Assert explicit, user-visible phrases rather than relying on prose interpretation:

```python
def test_context_setup_requires_approval_before_writing():
    content = read_skill("handoff-context-setup")
    self.assertIn("read-only discovery", content)
    self.assertIn("explicit user approval", content)
    self.assertIn("docs/agent-context.md", content)
    self.assertIn("docs/project-status.md", content)

def test_prepare_requires_scope_and_evidence():
    content = read_skill("handoff-prepare")
    self.assertIn("Original user objective", content)
    self.assertIn("Scope contract", content)
    self.assertIn("Evidence", content)
    self.assertIn("Known issues triage", content)

def test_continue_stops_after_alignment():
    content = read_skill("handoff-continue")
    self.assertIn("context-alignment report", content)
    self.assertIn("does not run commands", content)
    self.assertIn("ends after", content)
```

- [ ] **Step 2: Run the skill contract tests**

Run:

```bash
python3 -m unittest tests.test_context_guard.SkillContractTests -v
```

Expected: FAIL until the V2 skills and expanded sections exist.

- [ ] **Step 3: Write the three skills with narrow, auditable boundaries**

Implement the design's exact distinctions:

- The durable context index is link-based, reads at most eight normal-task sources, names authority/freshness, and never declares old plans active by implication.
- The status page separates delivered/accepted work, one active item, blocked work, user decisions, and deferred candidates.
- The session handoff includes objective, scope/stop condition, reading manifest, decisions with rationale, evidence/unverified claims, issue triage, git state, and continuation contract.
- `handoff-continue` reads repository instructions, context index, handoff, then only listed task artifacts; it reports missing/ambiguous sources and waits for a scoped user authorization.
- Scope escalation classifies a finding as blocking, follow-up candidate, or out of scope. Only a directly acceptance-blocking issue can be proposed as the smallest scoped fix; no category silently grants new work.

- [ ] **Step 4: Validate all skills and run contract tests**

Run:

```bash
python3 -m unittest tests.test_context_guard.SkillContractTests -v
VALIDATOR_PYTHON=work/validator-venv/bin/python
SYSTEM_SKILLS=/Users/lucienleung/.codex/skills/.system
"$VALIDATOR_PYTHON" "$SYSTEM_SKILLS/skill-creator/scripts/quick_validate.py" skills/handoff-context-setup
"$VALIDATOR_PYTHON" "$SYSTEM_SKILLS/skill-creator/scripts/quick_validate.py" skills/handoff-prepare
"$VALIDATOR_PYTHON" "$SYSTEM_SKILLS/skill-creator/scripts/quick_validate.py" skills/handoff-continue
```

Expected: all content-contract tests pass and each validator prints `Skill is valid!`. If the isolated validator environment is absent, create it as documented in the plugin source README before running validators.

- [ ] **Step 5: Commit**

```bash
git add plugins/codex-handoff/skills plugins/codex-handoff/tests/test_context_guard.py
git commit -m "feat: add v2 handoff context package"
```

## Task 5: Document V2 behavior, update packaging, and add migration guidance

**Files:**
- Modify: `README.md`
- Modify: `plugins/codex-handoff/README.md`
- Modify: `CHANGELOG.md`
- Modify: `plugins/codex-handoff/.codex-plugin/plugin.json`
- Modify: `plugins/codex-handoff/tests/test_context_guard.py`

**Interfaces:**
- Release version begins `0.2.0+codex.`.
- Public documentation gives both the standard marketplace install/reinstall path and safe V2 limitations.

- [ ] **Step 1: Write failing documentation and version tests**

Add assertions that the root README documents all three skills, the `PostToolUse`/`PreToolUse` best-effort guard, no automatic session switching, tool-result preservation, and the hosted-tool limitation. Assert the manifest version begins `0.2.0+codex.`.

- [ ] **Step 2: Run the metadata tests**

Run:

```bash
python3 -m unittest tests.test_context_guard.PluginMetadataTests -v
```

Expected: FAIL because the release version and V2 public instructions are not yet present.

- [ ] **Step 3: Write migration-safe user documentation**

Update both READMEs and changelog to explain:

1. V1 handoffs still work; V2 durable docs are opt-in through `$handoff-context-setup`.
2. Installing/reinstalling from the registered GitHub marketplace needs no clone and requires a new Codex task afterward.
3. At a strong threshold, a tool that already finished keeps its result; subsequent supported local tools in that same turn are denied with a handoff message.
4. The guard cannot observe every model action or hosted/special tool path, so users should still invoke `$handoff-prepare` deliberately.
5. Plugin data markers are opaque, local, zero-content dedupe/latch files; they are not project `.handoff/` documents.
6. A safe live-validation sequence: synthetic hook tests first, then one normal-work observation only when quota naturally reaches the threshold.

Set the semantic version to `0.2.0`, then run the existing cachebuster updater to append a fresh `+codex.<timestamp>` suffix. Do not alter user-specific identity fields unless the project owner asks.

- [ ] **Step 4: Run metadata tests and the plugin validator**

Run:

```bash
python3 -m unittest tests.test_context_guard.PluginMetadataTests -v
work/validator-venv/bin/python /Users/lucienleung/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
```

Expected: PASS and `Plugin validation passed`.

- [ ] **Step 5: Commit**

```bash
git add README.md CHANGELOG.md plugins/codex-handoff/README.md plugins/codex-handoff/.codex-plugin/plugin.json plugins/codex-handoff/tests/test_context_guard.py
git commit -m "docs: document codex handoff v2"
```

## Task 6: Verify the release candidate and prepare a reviewable handoff

**Files:**
- Modify only if evidence exposes a real defect: files scoped by the failed test.
- Create: `.handoff/<UTC timestamp>-v2-release-candidate.md` only if a user explicitly asks to prepare a handoff during this task.

- [ ] **Step 1: Run the complete automated suite from the plugin root**

Run:

```bash
cd plugins/codex-handoff
python3 -m unittest discover -s tests -v
work/validator-venv/bin/python /Users/lucienleung/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
for skill in handoff-context-setup handoff-prepare handoff-continue; do
  work/validator-venv/bin/python /Users/lucienleung/.codex/skills/.system/skill-creator/scripts/quick_validate.py "skills/$skill"
done
```

Expected: every test and validator passes. If a test fails, diagnose its concrete cause before editing; do not weaken a test to make the release pass.

- [ ] **Step 2: Add and execute deterministic stdin smoke cases**

Use a temporary rollout and `PLUGIN_DATA` directory, without consuming account quota, to prove these observable JSON contracts:

| Case | Expected result |
| --- | --- |
| five-hour 25% remaining, `UserPromptSubmit` | one non-blocking soft message, then silence |
| five-hour or weekly 3% remaining, `UserPromptSubmit` | one `decision:block`, then plain allow |
| auto `PreCompact` | non-blocking strong message |
| strong `PostToolUse` | `PostToolUse` additional context, no `continue` or `decision:block`, latch exists |
| same-turn `PreToolUse` | `permissionDecision: deny` |
| next-turn `PreToolUse` | plain allow |
| malformed payload, expired reset, missing IDs | no output or allow; no marker/latch |

- [ ] **Step 3: Perform a controlled installation check**

After the repository is committed and pushed by explicit user authorization, reinstall through the public marketplace commands from the README and open a new Codex task. Verify that all three skills appear and that the hook trust prompt identifies only `python3 "$PLUGIN_ROOT/hooks/context_guard.py"`.

Do not try to exhaust quota to force a live test. If a normal task naturally reaches 3% or below and the user authorizes observation, perform at most one harmless supported local tool action and confirm: completed result visible, handoff message visible, later supported local tool denied, fresh user request can invoke `$handoff-prepare`.

- [ ] **Step 4: Review the diff and working tree**

Run:

```bash
git diff --check
git status --short
git log --oneline --decorate -6
```

Expected: no whitespace errors; no accidental secrets, rollout transcripts, local plugin marker files, virtual environments, or `.DS_Store` files are staged.

- [ ] **Step 5: Ask for code review and report release readiness**

Request review of the final diff. Report automated evidence separately from any optional live observation. Do not claim the hook is an absolute stop mechanism; report its supported-tool, same-turn scope and documented bypasses.
