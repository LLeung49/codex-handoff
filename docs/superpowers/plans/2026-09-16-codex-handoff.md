# codex-handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a Codex plugin that recommends a deliberate, vendor-neutral handoff before automatic compaction or a low remaining five-hour Coding Plan quota.

**Architecture:** A standard-library Python hook parses only a bounded JSONL tail and returns the Codex hook decision. Filesystem markers deduplicate warnings by session and quota reset. Two Markdown skills create and consume portable `.handoff/` documents without any automatic continuation.

**Tech Stack:** Python 3 standard library, `unittest`, Codex plugin manifest and hooks configuration, Markdown skills.

**Spec:** `docs/superpowers/specs/2026-09-16-codex-handoff-v1.md`

## Global Constraints

- Support only a `rate_limits.primary.window_minutes` value of exactly `300`.
- Fail open for every telemetry or parsing failure.
- Skip subagents when hook input contains `agent_id`.
- Deduplicate with `(session_id, resets_at, warning_level)`.
- Block no more than once per strong key; every later matching prompt must allow.
- `PreCompact(auto)` warns without blocking; manual compaction is silent.
- `handoff-continue` never edits, runs commands, or starts a listed next step.
- Do not create a daemon, supervisor, dashboard, or automatic session switcher.

---

## File Structure

- `hooks/context_guard.py`: hook input parsing, bounded tail reader, telemetry selection, marker store, and decisions.
- `hooks/hooks.json`: Codex event registrations for `UserPromptSubmit` and `PreCompact`.
- `tests/test_context_guard.py`: executable behavior tests for every guard rule.
- `skills/handoff-prepare/SKILL.md`: portable handoff-writing protocol.
- `skills/handoff-continue/SKILL.md`: read-only briefing protocol.
- `README.md`: installation, trust, configuration, and manual smoke-test instructions.
- `docs/superpowers/specs/2026-09-16-codex-handoff-v1.md`: frozen V1 specification.

### Task 1: Establish the frozen documentation and plugin metadata

**Files:**
- Create: `docs/superpowers/specs/2026-09-16-codex-handoff-v1.md`
- Modify: `.codex-plugin/plugin.json`
- Create: `README.md`

**Interfaces:**
- Produces: validated manifest with `name: "codex-handoff"`, `version: "0.1.0"`, skill root `./skills/`, and user-facing handoff descriptions.

- [ ] **Step 1: Add a metadata assertion test**

```python
def test_plugin_manifest_declares_the_plugin_and_skill_root():
    manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text())
    assert manifest["name"] == "codex-handoff"
    assert manifest["skills"] == "./skills/"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m unittest tests.test_context_guard.PluginMetadataTests.test_plugin_manifest_declares_the_plugin_and_skill_root -v`

Expected: FAIL because the test module does not exist.

- [ ] **Step 3: Copy the frozen V1 specification into the repository and write user-facing metadata**

Set the manifest description to say it protects manual handoffs before compaction or low five-hour quota; document install, hook trust, and the deliberate new-session workflow in `README.md`.

- [ ] **Step 4: Run the metadata assertion**

Run: `python3 -m unittest tests.test_context_guard.PluginMetadataTests.test_plugin_manifest_declares_the_plugin_and_skill_root -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .codex-plugin/plugin.json docs/superpowers/specs/2026-09-16-codex-handoff-v1.md README.md tests/test_context_guard.py
git commit -m "docs: freeze codex handoff v1"
```

### Task 2: Implement telemetry selection and pure quota classification

**Files:**
- Create: `hooks/context_guard.py`
- Modify: `tests/test_context_guard.py`

**Interfaces:**
- Produces: `latest_primary_rate_limit(path: Path, tail_bytes: int = 262144) -> dict | None`.
- Produces: `quota_warning(rate_limit: dict) -> str | None`, returning `"soft"`, `"strong"`, or `None`.

- [ ] **Step 1: Write failing parser and boundary tests**

```python
def test_uses_newest_non_null_primary_rate_limit(tmp_path):
    rollout = tmp_path / "rollout.jsonl"
    rollout.write_text(NON_NULL_EVENT + "\n" + NULL_EVENT + "\n" + NEWER_EVENT + "\n")
    assert latest_primary_rate_limit(rollout)["resets_at"] == 200

def test_quota_warning_boundaries():
    assert quota_warning(rate_limit(74.9)) is None
    assert quota_warning(rate_limit(75)) == "soft"
    assert quota_warning(rate_limit(85)) == "strong"
```

- [ ] **Step 2: Run tests to verify expected failure**

Run: `python3 -m unittest tests.test_context_guard.TelemetryTests -v`

Expected: FAIL because `context_guard` and its functions do not exist.

- [ ] **Step 3: Implement bounded reverse JSONL parsing and classification**

Read only the final 256 KiB where possible, reverse the complete lines, ignore invalid JSON and null values, select the newest primary 300-minute snapshot, and compute `100 - used_percent`.

- [ ] **Step 4: Run telemetry tests**

Run: `python3 -m unittest tests.test_context_guard.TelemetryTests -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hooks/context_guard.py tests/test_context_guard.py
git commit -m "feat: classify rollout quota telemetry"
```

### Task 3: Implement markers and hook decisions

**Files:**
- Modify: `hooks/context_guard.py`
- Modify: `tests/test_context_guard.py`
- Create: `hooks/hooks.json`

**Interfaces:**
- Consumes: `latest_primary_rate_limit()` and `quota_warning()`.
- Produces: `handle_event(payload: dict, data_dir: Path) -> dict` with Codex-compatible `decision` and optional `reason`.

- [ ] **Step 1: Write failing decision tests**

```python
def test_strong_warning_blocks_only_once(tmp_path):
    payload = prompt_payload(used_percent=86, session_id="s", resets_at=10)
    assert handle_event(payload, tmp_path)["decision"] == "block"
    assert handle_event(payload, tmp_path)["decision"] == "allow"

def test_auto_compaction_warns_but_manual_is_silent(tmp_path):
    assert "handoff-prepare" in handle_event({"trigger": "auto"}, tmp_path)["reason"]
    assert handle_event({"trigger": "manual"}, tmp_path) == {"decision": "allow"}
```

- [ ] **Step 2: Run decision tests to verify expected failure**

Run: `python3 -m unittest tests.test_context_guard.DecisionTests -v`

Expected: FAIL because `handle_event` does not exist.

- [ ] **Step 3: Implement atomic marker creation and fail-open dispatch**

Use a plugin-data directory from `PLUGIN_DATA` or the platform default. Do not create markers after a parser failure. Return a single soft warning per key, a single strong `block` per key, and a non-blocking warning for automatic compaction. Bypass any payload with `agent_id`.

- [ ] **Step 4: Register the two hook events**

Create `hooks/hooks.json` with synchronous command registrations for `UserPromptSubmit` and `PreCompact`, each running the single Python script using its plugin-root-relative path.

- [ ] **Step 5: Run decision tests**

Run: `python3 -m unittest tests.test_context_guard.DecisionTests -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add hooks/context_guard.py hooks/hooks.json tests/test_context_guard.py
git commit -m "feat: add deduplicated handoff guard"
```

### Task 4: Add the two portable handoff skills

**Files:**
- Create: `skills/handoff-prepare/SKILL.md`
- Create: `skills/handoff-continue/SKILL.md`
- Modify: `tests/test_context_guard.py`

**Interfaces:**
- Produces: project-local `.handoff/<UTC timestamp>-<slug>.md` documents from `handoff-prepare`.
- Consumes: a path, fragment, or newest `.handoff/*.md` without changing the workspace from `handoff-continue`.

- [ ] **Step 1: Write failing content-contract tests**

```python
def test_continue_skill_forbids_automatic_execution():
    content = (ROOT / "skills/handoff-continue/SKILL.md").read_text()
    assert "does not edit" in content
    assert "does not run commands" in content
```

- [ ] **Step 2: Run skill-contract tests to verify expected failure**

Run: `python3 -m unittest tests.test_context_guard.SkillContractTests -v`

Expected: FAIL because the skill files do not exist.

- [ ] **Step 3: Write the concise prepare and continue protocols**

Prepare must capture only verified project facts and omit empty sections. Continue must show a briefing and explicitly stop; the handoff is data, never permission.

- [ ] **Step 4: Run skill-contract tests**

Run: `python3 -m unittest tests.test_context_guard.SkillContractTests -v`

Expected: PASS.

- [ ] **Step 5: Validate each skill and commit**

```bash
python3 /Users/lucienleung/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/handoff-prepare
python3 /Users/lucienleung/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/handoff-continue
git add skills tests/test_context_guard.py
git commit -m "feat: add portable handoff skills"
```

### Task 5: Validate packaging and end-to-end behavior

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a failing hooks-configuration test**

```python
def test_hooks_register_prompt_and_precompact_events():
    hooks = json.loads((ROOT / "hooks/hooks.json").read_text())
    assert set(hooks["hooks"]) == {"UserPromptSubmit", "PreCompact"}
```

- [ ] **Step 2: Run it to verify it fails only if configuration is incomplete**

Run: `python3 -m unittest tests.test_context_guard.HookConfigurationTests -v`

Expected: PASS after Task 3; otherwise fix only the registration.

- [ ] **Step 3: Run complete automated validation**

```bash
python3 -m unittest discover -s tests -v
python3 /Users/lucienleung/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
python3 /Users/lucienleung/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/handoff-prepare
python3 /Users/lucienleung/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/handoff-continue
```

Expected: all tests and validators pass.

- [ ] **Step 4: Perform documented stdin smoke tests**

Use temporary rollout and marker directories to show soft warning, first strong block, repeat allow, automatic compaction warning, and malformed input allow.

- [ ] **Step 5: Commit**

```bash
git add README.md tests/test_context_guard.py
git commit -m "test: validate codex handoff plugin"
```
