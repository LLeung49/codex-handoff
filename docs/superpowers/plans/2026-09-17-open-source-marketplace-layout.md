# Open-source Marketplace Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the repository into a self-contained Codex Marketplace that an open-source user can install after cloning it.

**Architecture:** The repository root becomes the Marketplace root. The existing plugin moves intact to `plugins/codex-handoff`, and a generated Marketplace manifest points to that directory. The current personal Marketplace entry remains only a local development convenience.

**Tech Stack:** Codex plugin manifests, JSON, Python standard-library tests, PyYAML-based Codex validators, Git.

**Spec:** `docs/superpowers/specs/2026-09-17-open-source-marketplace-layout-design.md`

## Global Constraints

- Preserve V1 behavior, including the 3% protective block threshold.
- Do not add daemons, telemetry uploads, or automatic session switching.
- Generate the repository Marketplace manifest with Codex's plugin scaffolder.
- Do not put author-specific absolute paths in public instructions.
- Validate the moved plugin, both skills, the full unit suite, and actual Marketplace installation.

---

### Task 1: Create the repository Marketplace layout

**Files:**

- Create: `.agents/plugins/marketplace.json`
- Create: `plugins/codex-handoff/`
- Move: `.codex-plugin/`, `hooks/`, `skills/`, `tests/`, `docs/`, `README.md`
- Test: `plugins/codex-handoff/tests/test_context_guard.py`

**Interfaces:**

- Consumes: Codex Marketplace source convention `./plugins/codex-handoff`.
- Produces: Marketplace name `codex-handoff` and plugin identifier `codex-handoff@codex-handoff`.

- [ ] **Step 1: Write the failing Marketplace metadata test**

Add this test, using `MARKETPLACE_ROOT` as the repository root:

```python
marketplace = json.loads((MARKETPLACE_ROOT / ".agents/plugins/marketplace.json").read_text())
entry = marketplace["plugins"][0]
self.assertEqual(marketplace["name"], "codex-handoff")
self.assertEqual(entry["name"], "codex-handoff")
self.assertEqual(entry["source"]["path"], "./plugins/codex-handoff")
```

- [ ] **Step 2: Run the test and confirm RED**

Run from the plugin root after the files move:

```bash
python3 -m unittest tests.test_context_guard.PluginMetadataTests -v
```

Expected: fail before the Marketplace manifest exists.

- [ ] **Step 3: Generate and populate the Marketplace layout**

Run the official generator:

```bash
python3 "$HOME/.codex/skills/.system/plugin-creator/scripts/create_basic_plugin.py" codex-handoff --path "$PWD/plugins" --marketplace-path "$PWD/.agents/plugins/marketplace.json" --marketplace-name codex-handoff --with-marketplace
```

Move the existing plugin tree into `plugins/codex-handoff`, replacing only
the generated stub manifest with the existing V1 manifest.

- [ ] **Step 4: Run the metadata test and confirm GREEN**

Run: `python3 -m unittest tests.test_context_guard.PluginMetadataTests -v`

Expected: pass.

- [ ] **Step 5: Commit the structural change**

Run: `git add .agents/plugins/marketplace.json plugins/codex-handoff && git commit -m "feat: package codex handoff as marketplace plugin"`

### Task 2: Write public installation documentation

**Files:**

- Create: `README.md`
- Modify: `plugins/codex-handoff/README.md`
- Modify: `plugins/codex-handoff/tests/test_context_guard.py`

**Interfaces:**

- Consumes: `codex-handoff@codex-handoff` from Task 1.
- Produces: clone-relative install, update, trust, and first live-check instructions.

- [ ] **Step 1: Write the failing public-documentation test**

```python
readme = (MARKETPLACE_ROOT / "README.md").read_text()
self.assertIn("codex plugin marketplace add", readme)
self.assertIn("codex plugin add codex-handoff@codex-handoff", readme)
self.assertNotIn("/Users/lucienleung", readme)
```

- [ ] **Step 2: Run the test and confirm RED**

Run: `python3 -m unittest tests.test_context_guard.PluginMetadataTests -v`

Expected: fail because the current README contains local development paths.

- [ ] **Step 3: Implement clone-relative installation guidance**

The root README explains cloning, adding the Marketplace, adding the plugin,
starting a new Codex task, approving the sole `context_guard.py` hook command,
and using `handoff-continue` without edits. The plugin README points users to
the root README. It also states that live quota warnings are observed during
normal use and not forced in an active account.

- [ ] **Step 4: Run the documentation test and confirm GREEN**

Run: `python3 -m unittest tests.test_context_guard.PluginMetadataTests -v`

Expected: pass.

- [ ] **Step 5: Commit the public documentation**

Run: `git add README.md plugins/codex-handoff/README.md plugins/codex-handoff/tests/test_context_guard.py && git commit -m "docs: add public marketplace installation guide"`

### Task 3: Verify distribution and local development installation

**Files:**

- Modify outside the repository: `/Users/lucienleung/plugins/codex-handoff` symbolic link only.

**Interfaces:**

- Consumes: personal identifier `codex-handoff@personal`; distribution identifier `codex-handoff@codex-handoff`.
- Produces: both local development and clone-style distribution installations.

- [ ] **Step 1: Repoint the exact development link**

Change only `~/plugins/codex-handoff` to point at
`<repository>/plugins/codex-handoff`. The personal marketplace JSON stays
unchanged because it already resolves `./plugins/codex-handoff`.

- [ ] **Step 2: Add and install the repository Marketplace**

```bash
codex plugin marketplace add "$PWD"
codex plugin add codex-handoff@codex-handoff
codex plugin list
```

Expected: `codex-handoff@codex-handoff` is `installed, enabled`.

- [ ] **Step 3: Run full static validation**

Run from `plugins/codex-handoff`:

```bash
python3 -m unittest discover -s tests -v
"$VALIDATOR_PYTHON" "$SYSTEM_SKILLS/plugin-creator/scripts/validate_plugin.py" .
"$VALIDATOR_PYTHON" "$SYSTEM_SKILLS/skill-creator/scripts/quick_validate.py" skills/handoff-prepare
"$VALIDATOR_PYTHON" "$SYSTEM_SKILLS/skill-creator/scripts/quick_validate.py" skills/handoff-continue
```

Expected: all commands pass.

- [ ] **Step 4: Commit repository changes and hand off the desktop check**

Run: `git add README.md .agents plugins/codex-handoff && git commit -m "chore: verify marketplace distribution layout"`

Ask the user to start a new desktop task, approve the displayed hook command,
and invoke `handoff-continue` for the non-destructive first live skill check.
