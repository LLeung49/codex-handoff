import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hooks.context_guard import (
    ALLOW,
    claim_turn_latch,
    format_hook_output,
    handle_event,
    handle_post_tool_use,
    latest_primary_rate_limit,
    latest_secondary_rate_limit,
    quota_warning,
    turn_latch_exists,
)


ROOT = Path(__file__).resolve().parents[1]
NOW = 4102444800
RESET = NOW + 18000


def repository_root() -> Path:
    """Return the source checkout root or skip repository-only assertions."""
    for candidate in (ROOT, *ROOT.parents):
        plugin_source = candidate / "plugins" / "codex-handoff"
        if (candidate / ".agents/plugins/marketplace.json").exists() and plugin_source == ROOT:
            return candidate
    raise unittest.SkipTest("Repository-only metadata is absent from an installed plugin package")


def rate_limit(used_percent):
    return {"window_minutes": 300, "used_percent": used_percent, "resets_at": RESET}


def prompt_payload(directory, used_percent, session_id="session", resets_at=RESET, prompt=None):
    """Create a direct token-count transcript for a prompt-hook input."""
    transcript = Path(directory) / f"rollout-{session_id}-{resets_at}.jsonl"
    transcript.write_text(json.dumps({
        "type": "token_count",
        "rate_limits": {"primary": {
            "window_minutes": 300,
            "used_percent": used_percent,
            "resets_at": resets_at,
        }},
    }) + "\n")
    payload = {"session_id": session_id, "transcript_path": str(transcript)}
    if prompt is not None:
        payload["prompt"] = prompt
    return payload


def prompt_payload_with_weekly_limit(directory, weekly_used_percent, session_id="session", prompt=None):
    """Create telemetry with a healthy 5h window and a weekly quota snapshot."""
    transcript = Path(directory) / f"rollout-{session_id}-weekly.jsonl"
    transcript.write_text(json.dumps({
        "type": "token_count",
        "rate_limits": {
            "primary": rate_limit(10),
            "secondary": {
                "window_minutes": 10080,
                "used_percent": weekly_used_percent,
                "resets_at": RESET,
            },
        },
    }) + "\n")
    payload = {"session_id": session_id, "transcript_path": str(transcript)}
    if prompt is not None:
        payload["prompt"] = prompt
    return payload


def post_tool_payload(directory, primary_used_percent=10, weekly_used_percent=None,
                      session_id="session", turn_id="turn", resets_at=RESET):
    """Create a PostToolUse payload backed by a Codex event_msg rollout."""
    transcript = Path(directory) / f"post-tool-{session_id}-{turn_id}-{resets_at}.jsonl"
    limits = {
        "primary": {
            "window_minutes": 300,
            "used_percent": primary_used_percent,
            "resets_at": resets_at,
        },
    }
    if weekly_used_percent is not None:
        limits["secondary"] = {
            "window_minutes": 10080,
            "used_percent": weekly_used_percent,
            "resets_at": resets_at + 100,
        }
    transcript.write_text(json.dumps({
        "type": "event_msg",
        "payload": {"type": "token_count", "rate_limits": limits},
    }) + "\n")
    return {
        "hook_event_name": "PostToolUse",
        "session_id": session_id,
        "turn_id": turn_id,
        "transcript_path": str(transcript),
    }


NON_NULL_EVENT = json.dumps({
    "type": "token_count",
    "rate_limits": {"primary": {"window_minutes": 300, "used_percent": 10, "resets_at": RESET}},
})
NULL_EVENT = json.dumps({
    "type": "token_count",
    "rate_limits": {"primary": None},
})
NEWER_EVENT = json.dumps({
    "type": "token_count",
    "rate_limits": {"primary": {"window_minutes": 300, "used_percent": 20, "resets_at": RESET + 300}},
})


class TelemetryTests(unittest.TestCase):
    def test_uses_newest_non_null_primary_rate_limit(self):
        with self.subTest("newest snapshot"):
            from tempfile import TemporaryDirectory

            with TemporaryDirectory() as directory:
                rollout = Path(directory) / "rollout.jsonl"
                rollout.write_text(NON_NULL_EVENT + "\n" + NULL_EVENT + "\n" + NEWER_EVENT + "\n")
                self.assertEqual(latest_primary_rate_limit(rollout)["resets_at"], RESET + 300)

    def test_reads_codex_rollout_envelope_with_trailing_null_limits(self):
        """Dropping event_msg unwrapping loses actual Codex quota telemetry."""
        rollout = ROOT / "tests/fixtures/codex-rollout.jsonl"
        self.assertEqual(latest_primary_rate_limit(rollout), {
            "window_minutes": 300, "used_percent": 97, "resets_at": 4102462800,
        })

    def test_reads_weekly_rate_limit_from_codex_rollout(self):
        rollout = ROOT / "tests/fixtures/codex-rollout.jsonl"
        self.assertEqual(latest_secondary_rate_limit(rollout), {
            "window_minutes": 10080, "used_percent": 20, "resets_at": 4103049600,
        })

    def test_newest_unusable_primary_does_not_resurrect_older_snapshot(self):
        """Skipping an unusable primary would resurrect an older quota window."""
        for invalid_fields in (
            {"window_minutes": 60}, {"used_percent": "unknown"},
            {"used_percent": 101}, {"resets_at": None},
        ):
            with self.subTest(invalid_fields=invalid_fields), tempfile.TemporaryDirectory() as directory:
                rollout = Path(directory) / "rollout.jsonl"
                primary = {**rate_limit(90), **invalid_fields}
                newest = json.dumps({"type": "token_count", "rate_limits": {"primary": primary}})
                rollout.write_text(NON_NULL_EVENT + "\n" + newest + "\n" + NULL_EVENT + "\n")
                self.assertIsNone(latest_primary_rate_limit(rollout))

    def test_quota_warning_boundaries(self):
        self.assertIsNone(quota_warning(rate_limit(84.9)))
        self.assertEqual(quota_warning(rate_limit(85)), "soft")
        self.assertEqual(quota_warning(rate_limit(90)), "soft")
        self.assertEqual(quota_warning(rate_limit(93.9)), "soft")
        self.assertEqual(quota_warning(rate_limit(94)), "strong")
        self.assertEqual(quota_warning(rate_limit(94.9)), "strong")
        self.assertEqual(quota_warning(rate_limit(95)), "strong")
        self.assertEqual(quota_warning(rate_limit(96)), "strong")
        self.assertEqual(quota_warning(rate_limit(97)), "strong")

    def test_weekly_strong_warning_starts_at_six_percent_remaining(self):
        self.assertIsNone(quota_warning(
            {**rate_limit(93.9), "window_minutes": 10080},
            window_minutes=10080,
            soft_warning=False,
        ))
        self.assertEqual(quota_warning(
            {**rate_limit(94), "window_minutes": 10080},
            window_minutes=10080,
            soft_warning=False,
        ), "strong")

    def test_quota_warning_ignores_unsupported_window(self):
        self.assertIsNone(quota_warning({"window_minutes": 60, "used_percent": 90}))

    def test_quota_warning_fails_open_for_integer_overflow(self):
        self.assertIsNone(quota_warning({"window_minutes": 300, "used_percent": 10**10000}))

    def test_parser_ignores_malformed_null_and_unsupported_events(self):
        events = [
            "not json",
            json.dumps({"type": "token_count", "rate_limits": None}),
            json.dumps({"type": "token_count", "rate_limits": {"primary": {"window_minutes": 60, "used_percent": 90, "resets_at": RESET}}}),
            NEWER_EVENT,
        ]
        with tempfile.TemporaryDirectory() as directory:
            rollout = Path(directory) / "rollout.jsonl"
            rollout.write_text("\n".join(events) + "\n")
            self.assertEqual(latest_primary_rate_limit(rollout)["resets_at"], RESET + 300)

    def test_bounded_tail_discards_partial_leading_line(self):
        with tempfile.TemporaryDirectory() as directory:
            rollout = Path(directory) / "rollout.jsonl"
            rollout.write_text("x" * 100 + "\n" + NEWER_EVENT + "\n")
            tail_bytes = len(NEWER_EVENT.encode()) + 2
            self.assertEqual(latest_primary_rate_limit(rollout, tail_bytes=tail_bytes)["resets_at"], RESET + 300)

    def test_bounded_tail_retains_complete_line_at_exact_lf_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            rollout = Path(directory) / "rollout.jsonl"
            event = NEWER_EVENT.encode()
            rollout.write_bytes(b"x" * 100 + b"\n" + event + b"\n")
            self.assertEqual(
                latest_primary_rate_limit(rollout, tail_bytes=len(event) + 1)["resets_at"],
                RESET + 300,
            )

    def test_bounded_tail_retains_complete_line_at_exact_crlf_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            rollout = Path(directory) / "rollout.jsonl"
            event = NEWER_EVENT.encode()
            rollout.write_bytes(b"x" * 100 + b"\r\n" + event + b"\r\n")
            self.assertEqual(
                latest_primary_rate_limit(rollout, tail_bytes=len(event) + 2)["resets_at"],
                RESET + 300,
            )


class PluginMetadataTests(unittest.TestCase):
    def test_root_readme_documents_public_marketplace_installation(self):
        marketplace_root = repository_root()
        readme = (marketplace_root / "README.md").read_text(encoding="utf-8")
        self.assertIn("codex plugin marketplace add LLeung49/codex-handoff --ref main", readme)
        self.assertIn("codex plugin add codex-handoff@codex-handoff", readme)
        self.assertNotIn("/Users/lucienleung", readme)

    def test_root_readme_documents_v2_skills_and_guard_limits(self):
        """Removing V2 safety guidance would leave marketplace users misinformed."""
        marketplace_root = repository_root()
        readme = " ".join((marketplace_root / "README.md").read_text(encoding="utf-8").split())
        for requirement in (
            "$handoff-context-setup", "$handoff-prepare", "$handoff-continue",
            "PostToolUse", "PreToolUse", "continue", "L1", "L2",
        ):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, readme)

    def test_root_readme_has_the_scannable_open_source_sections(self):
        """Keep the public README's onboarding modules and current hero asset."""
        marketplace_root = repository_root()
        readme = (marketplace_root / "README.md").read_text(encoding="utf-8")
        self.assertGreaterEqual(readme.count("## "), 4)
        self.assertIn("assets/codex-handoff-05-progressive-checkpoint-v2.png", readme)
        self.assertTrue(
            (marketplace_root / "assets/codex-handoff-05-progressive-checkpoint-v2.png").is_file()
        )

    def test_root_readme_keeps_its_five_handoff_images(self):
        """Keep each visual explanation linked to a shipped project asset."""
        marketplace_root = repository_root()
        readme = (marketplace_root / "README.md").read_text(encoding="utf-8")
        illustrations = (
            "assets/codex-handoff-00-origin-story.png",
            "assets/codex-handoff-03-quota-guard-v2.png",
            "assets/codex-handoff-04-protective-block.png",
            "assets/codex-handoff-05-progressive-checkpoint-v2.png",
            "assets/codex-handoff-06-optional-clarification-v2.png",
        )
        for illustration in illustrations:
            with self.subTest(illustration=illustration):
                self.assertIn(illustration, readme)
                self.assertTrue((marketplace_root / illustration).is_file())

    def test_root_readme_does_not_link_to_local_docs(self):
        """Published onboarding must not link to user-local documentation."""
        marketplace_root = repository_root()
        readme = (marketplace_root / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("docs/superpowers", readme)
        self.assertIn("/docs/", (marketplace_root / ".gitignore").read_text(encoding="utf-8"))

    def test_root_readme_explains_current_quota_and_progressive_handoff(self):
        marketplace_root = repository_root()
        readme = (marketplace_root / "README.md").read_text(encoding="utf-8")
        for requirement in ("6%", "continue", "L0", "L1", "L2"):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, readme)

    def test_hook_runtime_sources_are_ascii_only(self):
        """Machine-facing hook source and configuration must be code-page neutral."""
        for path in sorted((ROOT / "hooks").iterdir()):
            if path.suffix not in {".py", ".json"}:
                continue
            with self.subTest(path=path.name):
                path.read_bytes().decode("ascii")

    def test_plugin_readme_validates_all_v2_skills(self):
        """A released V2 plugin must validate the newly added setup skill."""
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("skills/handoff-context-setup", readme)

    def test_plugin_readme_documents_v21_context_budget(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for requirement in (
            "L1", "L2", "at most 3", "at most 5", "project-status.md",
            "does not create or refresh",
        ):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, readme)

    def test_marketplace_points_to_the_nested_plugin(self):
        marketplace_root = repository_root()
        marketplace = json.loads(
            (marketplace_root / ".agents/plugins/marketplace.json").read_text(encoding="utf-8")
        )
        entry = marketplace["plugins"][0]
        self.assertEqual(marketplace["name"], "codex-handoff")
        self.assertEqual(entry["name"], "codex-handoff")
        self.assertEqual(entry["source"]["path"], "./plugins/codex-handoff")

    def test_plugin_manifest_declares_the_plugin_and_skill_root(self):
        manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "codex-handoff")
        self.assertEqual(manifest["skills"], "./skills/")

    def test_plugin_manifest_uses_the_v0_3_6_release_version(self):
        manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertRegex(manifest["version"], r"^0\.3\.6\+codex\.\d{14}$")


class HookConfigurationTests(unittest.TestCase):
    def test_hooks_register_all_four_lifecycle_events(self):
        hooks = json.loads((ROOT / "hooks/hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(set(hooks["hooks"]), {
            "UserPromptSubmit", "PreCompact", "PostToolUse", "PreToolUse",
        })

    def test_hooks_resolve_the_guard_from_the_plugin_root(self):
        """Relative paths run from the session cwd, not the plugin directory."""
        hooks = json.loads((ROOT / "hooks/hooks.json").read_text(encoding="utf-8"))
        for event in hooks["hooks"]:
            handler = hooks["hooks"][event][0]["hooks"][0]
            self.assertEqual(handler["command"], 'python3 "$PLUGIN_ROOT/hooks/context_guard.py"')
            self.assertEqual(
                handler["commandWindows"],
                'python "${env:PLUGIN_ROOT}\\hooks\\context_guard.py"',
            )

    def test_tool_hooks_match_all_tools_synchronously(self):
        hooks = json.loads((ROOT / "hooks/hooks.json").read_text(encoding="utf-8"))["hooks"]
        for event in ("PreToolUse", "PostToolUse"):
            self.assertEqual(hooks.get(event), [{
                "matcher": "*",
                "hooks": [{
                    "type": "command",
                    "command": 'python3 "$PLUGIN_ROOT/hooks/context_guard.py"',
                    "commandWindows": 'python "${env:PLUGIN_ROOT}\\hooks\\context_guard.py"',
                }],
            }])

    @unittest.skipUnless(sys.platform == "darwin", "macOS command execution requires /bin/sh")
    def test_macos_command_launches_from_unrelated_cwd_with_spaces(self):
        """Catch broken POSIX expansion or quoting in the shipped macOS command."""
        hooks = json.loads((ROOT / "hooks/hooks.json").read_text(encoding="utf-8"))["hooks"]
        command = hooks["PostToolUse"][0]["hooks"][0]["command"]
        with tempfile.TemporaryDirectory(prefix="codex handoff ") as directory:
            temp_root = Path(directory)
            plugin_root = temp_root / "installed plugin"
            shutil.copytree(ROOT / "hooks", plugin_root / "hooks")
            session_cwd = temp_root / "unrelated project"
            session_cwd.mkdir()
            data_dir = temp_root / "plugin data"
            result = subprocess.run(
                ["/bin/sh", "-c", command],
                input=json.dumps({"hook_event_name": "PreCompact", "trigger": "manual"}),
                text=True,
                capture_output=True,
                cwd=session_cwd,
                env={**os.environ, "PLUGIN_ROOT": str(plugin_root), "PLUGIN_DATA": str(data_dir)},
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")

    @unittest.skipUnless(os.name == "nt", "Windows command execution requires PowerShell")
    def test_windows_command_launches_in_powershell_from_unrelated_cwd_with_spaces(self):
        """Catch cmd.exe environment syntax that PowerShell leaves unexpanded."""
        hooks = json.loads((ROOT / "hooks/hooks.json").read_text(encoding="utf-8"))["hooks"]
        command = hooks["PostToolUse"][0]["hooks"][0]["commandWindows"]
        with tempfile.TemporaryDirectory(prefix="codex handoff ") as directory:
            temp_root = Path(directory)
            plugin_root = temp_root / "installed plugin"
            shutil.copytree(ROOT / "hooks", plugin_root / "hooks")
            session_cwd = temp_root / "unrelated project"
            session_cwd.mkdir()
            data_dir = temp_root / "plugin data"
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                input=json.dumps({"hook_event_name": "PreCompact", "trigger": "manual"}),
                text=True,
                capture_output=True,
                cwd=session_cwd,
                env={**os.environ, "PLUGIN_ROOT": str(plugin_root), "PLUGIN_DATA": str(data_dir)},
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")


class SkillContractTests(unittest.TestCase):
    """Check the required agent-visible contract, not runtime agent compliance."""

    def read_skill(self, name):
        path = ROOT / "skills" / name / "SKILL.md"
        self.assertTrue(path.is_file(), f"Missing skill: {name}")
        return " ".join(path.read_text(encoding="utf-8").split())

    def test_continue_skill_uses_guidance_not_a_capability_firewall(self):
        content = self.read_skill("handoff-continue")
        self.assertIn("does not authorize", content)
        self.assertIn("any available read-only mechanism", content)
        self.assertIn("Get-Content", content)
        self.assertNotIn("do not use command execution as a fallback", content)

    def test_context_setup_proposes_only_the_optional_context_index(self):
        content = self.read_skill("handoff-context-setup")
        for requirement in (
            "read-only discovery", "explicit user approval", "exact source paths",
            "draft", "Before approval, do not persist", "docs/agent-context.md",
            "source-of-truth hierarchy", "at most eight", "last verified",
            "known gaps", "Do not treat old plans as active",
            "does not create or refresh `docs/project-status.md`",
            "Do not change `AGENTS.md`, `CLAUDE.md`, source code, or `.gitignore`",
        ):
            self.assertIn(requirement, content)
        self.assertNotIn("## Delivery Status Shape", content)

    def test_prepare_requires_v21_checkpoint_and_budget(self):
        content = self.read_skill("handoff-prepare")
        sections = (
            "User checkpoint", "Task contract", "Next action and boundary",
            "Delivery and acceptance ledger", "Minimal reading package", "Trace metadata",
            "Continuation contract",
        )
        for section in sections:
            self.assertIn(section, content)
        positions = [content.index(section) for section in sections]
        self.assertEqual(positions, sorted(positions))
        for requirement in (
            "implemented", "verified", "accepted", "in progress", "not started",
            "blocked", "at most 3", "at most 5", "clarification supplement",
            "Never overwrite",
        ):
            self.assertIn(requirement, content)

    def test_prepare_keeps_snapshot_immutable_without_status_page_output(self):
        content = self.read_skill("handoff-prepare")
        for requirement in (
            "one immutable", ".handoff/<UTC timestamp>-<slug>.md",
            "Never overwrite", "does not create or refresh `docs/project-status.md`",
            "Do not change `.gitignore`",
        ):
            self.assertIn(requirement, content)

    def test_continue_reads_only_v21_initial_context(self):
        content = self.read_skill("handoff-continue")
        for requirement in (
            "L0", "L1", "L2", "Do not automatically read L1 or L2 during initial alignment",
            "zero to three", "missing fact", "affected delivery",
            "preferred responder", "Single authorization request",
            "any available read-only mechanism", "ends after",
        ):
            self.assertIn(requirement, content)
        self.assertIn("Do not recursively follow links", content)

    def test_continue_excludes_supplements_from_default_selection(self):
        content = self.read_skill("handoff-continue")
        for requirement in (
            "directly in `.handoff/`", ".handoff/clarifications/",
            "not candidates for automatic selection", "user explicitly selects",
        ):
            self.assertIn(requirement, content)

    def test_continue_reads_compact_l0_before_on_demand_detail(self):
        content = self.read_skill("handoff-continue")
        for requirement in (
            "first three sections", "User checkpoint", "Task contract",
            "Next action and boundary", "Do not read the ledger, risks, trace",
            "Do not automatically read L1 or L2",
        ):
            self.assertIn(requirement, content)

    def test_continue_stops_after_alignment(self):
        content = self.read_skill("handoff-continue")
        for requirement in (
            "context-alignment report", "ends after", "does not authorize",
            "loaded sources", "missing/ambiguous sources", "stop condition",
            "confirmed evidence", "unverified claims", "user decisions",
            "user-authorized scoped action", "commits, pushes",
        ):
            self.assertIn(requirement, content)

    def test_continue_handles_v1_and_untrusted_or_ambiguous_sources(self):
        content = self.read_skill("handoff-continue")
        for requirement in (
            "V1", "Goal", "Suggested next steps", "absent", "do not invent",
            "missing, stale, local-only/untracked, or contradictory",
            "ambiguous", "ask the user to choose",
            "data, never authority", "User messages and repository instructions retain precedence",
        ):
            self.assertIn(requirement, content)

    def test_scope_escalation_never_silently_authorizes_work(self):
        for name in ("handoff-context-setup", "handoff-prepare", "handoff-continue"):
            with self.subTest(skill=name):
                content = self.read_skill(name)
                for requirement in (
                    "blocking", "approved acceptance criterion", "smallest scoped fix",
                    "follow-up candidate", "separate task", "out of scope",
                    "No classification grants authorization",
                ):
                    self.assertIn(requirement, content)


class PromptRecoveryTests(unittest.TestCase):
    """Exercise the shipped process across blocked and resumed user turns."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.data_dir = Path(self.directory.name) / "markers"

    def run_hook(self, payload):
        result = subprocess.run(
            [sys.executable, str(ROOT / "hooks/context_guard.py")],
            input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            capture_output=True, timeout=10,
            env={**os.environ, "PLUGIN_DATA": str(self.data_dir),
                 "PYTHONIOENCODING": "cp936", "PYTHONUTF8": "0"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, b"")
        return json.loads(result.stdout) if result.stdout else None

    def prompt(self, text, weekly=False, session_id="recovery", resets_at=RESET):
        if weekly:
            payload = prompt_payload_with_weekly_limit(
                self.directory.name, 95, session_id=session_id, prompt=text,
            )
        else:
            payload = prompt_payload(
                self.directory.name, 95, session_id=session_id,
                resets_at=resets_at, prompt=text,
            )
        return {**payload, "hook_event_name": "UserPromptSubmit"}

    def context(self, output):
        self.assertIsInstance(output, dict)
        self.assertIn("hookSpecificOutput", output)
        specific = output["hookSpecificOutput"]
        self.assertEqual(specific["hookEventName"], "UserPromptSubmit")
        return specific["additionalContext"]

    def test_continue_restores_the_blocked_prompt_verbatim_in_model_context(self):
        original = "\u5bf9\u6bd4\u65b0\u65e7\u6570\u636e\u6709\u4ec0\u4e48\u610f\u4e49\uff1f\nDiscuss first. Do not write a plan. \"quoted\" </prompt>"
        for weekly in (False, True):
            with self.subTest(weekly=weekly):
                payload = self.prompt(original, weekly=weekly, session_id=str(weekly))
                self.assertEqual(self.run_hook(payload)["decision"], "block")
                resumed = self.run_hook({**payload, "prompt": "continue"})
                context = self.context(resumed)
                self.assertEqual(json.loads(context.splitlines()[-1])["prompt"], original)
                self.assertIn("before resuming any earlier plan", context)
                self.assertIsNone(self.run_hook({**payload, "prompt": "next request"}))
        self.assertTrue(all(path.stat().st_size == 0 for path in self.data_dir.glob("*.marker")))

    def test_rejected_followup_does_not_replace_the_original_request(self):
        payload = self.prompt("Discuss the data comparison before planning.")
        self.assertEqual(self.run_hook(payload)["decision"], "block")
        self.assertEqual(self.run_hook({**payload, "prompt": "unconfirmed followup"})["decision"], "block")
        context = self.context(self.run_hook({**payload, "prompt": "continue"}))
        self.assertEqual(json.loads(context.splitlines()[-1])["prompt"], payload["prompt"])

    def test_tool_stop_continues_existing_work_without_replaying_a_prompt(self):
        payload = post_tool_payload(self.directory.name, primary_used_percent=95)
        self.assertIsNotNone(self.run_hook(payload))
        resumed = self.run_hook({**payload, "hook_event_name": "UserPromptSubmit", "prompt": "continue"})
        context = self.context(resumed)
        self.assertIn("completed tool result", context)
        self.assertNotIn('"prompt":', context)

    def test_handoff_carries_the_unanswered_request_as_context_only(self):
        payload = self.prompt("Please discuss the data comparison.")
        self.assertEqual(self.run_hook(payload)["decision"], "block")
        context = self.context(self.run_hook({**payload, "prompt": "$handoff-prepare"}))
        self.assertEqual(json.loads(context.splitlines()[-1])["prompt"], payload["prompt"])
        self.assertIn("unanswered", context)
        self.assertTrue(all(path.stat().st_size == 0 for path in self.data_dir.glob("*.marker")))

    def test_empty_legacy_state_asks_for_the_request_instead_of_guessing(self):
        payload = self.prompt("Review this before planning.")
        self.assertEqual(self.run_hook(payload)["decision"], "block")
        for path in self.data_dir.glob("*.marker"):
            path.write_bytes(b"")
        context = self.context(self.run_hook({**payload, "prompt": "continue"}))
        self.assertIn("ask the user to resend", context)

    def test_corrupt_pending_state_allows_continue_and_requests_clarification(self):
        payload = self.prompt("Review this before planning.")
        self.assertEqual(self.run_hook(payload)["decision"], "block")
        for path in self.data_dir.glob("*.marker"):
            if path.stat().st_size:
                path.write_bytes(b"{broken")
        context = self.context(self.run_hook({**payload, "prompt": "continue"}))
        self.assertIn("ask the user to resend", context)

    def test_both_low_windows_restore_one_request_and_consume_all_pending_state(self):
        payload = self.prompt("Discuss before writing the plan.")
        transcript = Path(payload["transcript_path"])
        event = json.loads(transcript.read_text(encoding="utf-8"))
        event["rate_limits"]["secondary"] = {
            "window_minutes": 10080, "used_percent": 95, "resets_at": RESET + 100,
        }
        transcript.write_text(json.dumps(event), encoding="utf-8")
        self.assertEqual(self.run_hook(payload)["decision"], "block")
        context = self.context(self.run_hook({**payload, "prompt": "continue"}))
        self.assertEqual(json.loads(context.splitlines()[-1])["prompt"], payload["prompt"])
        self.assertTrue(all(path.stat().st_size == 0 for path in self.data_dir.glob("*.marker")))
        self.assertIsNone(self.run_hook({**payload, "prompt": "continue"}))

    def test_prompt_storage_failure_fails_open_without_partial_request(self):
        payload = self.prompt("Discuss before planning.")
        with patch("hooks.context_guard.json.dump", side_effect=OSError("disk full")):
            self.assertEqual(handle_event(payload, self.data_dir), ALLOW)
        self.assertTrue(all(path.stat().st_size == 0 for path in self.data_dir.glob("*.marker")))

    def test_missing_prompt_is_not_mistaken_for_a_tool_stop(self):
        payload = self.prompt("temporary")
        del payload["prompt"]
        self.assertEqual(self.run_hook(payload)["decision"], "block")
        context = self.context(self.run_hook({**payload, "prompt": "continue"}))
        self.assertIn("ask the user to resend", context)

    def test_resume_does_not_recover_another_session_or_reset(self):
        first = self.prompt("First session private question.")
        self.assertEqual(self.run_hook(first)["decision"], "block")
        other = self.prompt("Second session question.", session_id="other")
        self.assertEqual(self.run_hook(other)["decision"], "block")
        context = self.context(self.run_hook({**other, "prompt": "continue"}))
        self.assertEqual(json.loads(context.splitlines()[-1])["prompt"], other["prompt"])
        later = self.prompt("New window question.", resets_at=RESET + 300)
        self.assertEqual(self.run_hook(later)["decision"], "block")
        context = self.context(self.run_hook({**later, "prompt": "continue"}))
        self.assertEqual(json.loads(context.splitlines()[-1])["prompt"], later["prompt"])


class DecisionTests(unittest.TestCase):
    def setUp(self):
        clock = patch("time.time", return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)

    def test_real_rollout_allows_explicit_handoff_after_the_block(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = {
                "session_id": "real", "transcript_path": str(ROOT / "tests/fixtures/codex-rollout.jsonl"),
                "prompt": "ordinary work",
            }
            data_dir = Path(directory) / "markers"
            self.assertEqual(handle_event(payload, data_dir)["decision"], "block")
            self.assertEqual(handle_event({**payload, "prompt": "$handoff-prepare"}, data_dir)["decision"], "allow")

    def test_expired_or_current_reset_allows_without_marker(self):
        """Missing expiry validation would block and write a stale marker."""
        for reset in (NOW - 1, NOW):
            with self.subTest(reset=reset), tempfile.TemporaryDirectory() as directory:
                payload = prompt_payload(directory, used_percent=90, resets_at=reset)
                data_dir = Path(directory) / "markers"
                self.assertEqual(handle_event(payload, data_dir), {"decision": "allow"})
                self.assertFalse(data_dir.exists())

    def test_newest_unsupported_snapshot_allows_without_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = prompt_payload(directory, used_percent=90)
            transcript = Path(payload["transcript_path"])
            with transcript.open("a") as stream:
                stream.write(json.dumps({"type": "token_count", "rate_limits": {
                    "primary": {"window_minutes": 60, "used_percent": 90, "resets_at": RESET},
                }}) + "\n")
            data_dir = Path(directory) / "markers"
            self.assertEqual(handle_event(payload, data_dir), {"decision": "allow"})
            self.assertFalse(data_dir.exists())

    def test_strong_warning_waits_for_an_explicit_user_choice(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = prompt_payload(directory, used_percent=97, session_id="s", prompt="ordinary work")
            data_dir = Path(directory) / "markers"
            first = handle_event(payload, data_dir)
            self.assertEqual(first["decision"], "block")
            self.assertIn("$handoff-prepare", first["reason"])
            self.assertIn("`continue`", first["reason"])
            self.assertTrue(first["reason"].isascii())
            self.assertNotIn("$handoff-continue", first["reason"])
            self.assertEqual(handle_event({**payload, "prompt": "keep coding"}, data_dir)["decision"], "block")
            self.assertEqual(handle_event({**payload, "prompt": "$handoff-prepare"}, data_dir)["decision"], "allow")

    def test_prompt_blocks_at_six_percent_for_each_quota_window(self):
        for window in ("five-hour", "weekly"):
            with self.subTest(window=window), tempfile.TemporaryDirectory() as directory:
                if window == "five-hour":
                    payload = prompt_payload(directory, used_percent=94, prompt="ordinary work")
                else:
                    payload = prompt_payload_with_weekly_limit(
                        directory, weekly_used_percent=94, prompt="ordinary work",
                    )
                self.assertEqual(handle_event(payload, Path(directory) / "markers")["decision"], "block")

    def test_namespaced_and_natural_handoff_commands_unblock(self):
        for cmd in (
            "$codex-handoff:handoff-prepare",
            "codex-handoff:handoff-prepare",
            "Run $codex-handoff:handoff-prepare",
            "Run $handoff-prepare to save a checkpoint",
        ):
            with self.subTest(cmd=cmd), tempfile.TemporaryDirectory() as directory:
                payload = prompt_payload(directory, used_percent=95, session_id="ns", prompt="work")
                data_dir = Path(directory) / "markers"
                self.assertEqual(handle_event(payload, data_dir)["decision"], "block")
                self.assertEqual(handle_event({**payload, "prompt": cmd}, data_dir)["decision"], "allow")

    def test_proactive_handoff_is_never_blocked_at_low_quota(self):
        """A proactive handoff prompt at or below 6% quota must be allowed without block."""
        with tempfile.TemporaryDirectory() as directory:
            payload = prompt_payload(directory, used_percent=96, session_id="p", prompt="$codex-handoff:handoff-prepare")
            data_dir = Path(directory) / "markers"
            self.assertEqual(handle_event(payload, data_dir), ALLOW)

    def test_continue_burns_remaining_quota_without_further_blocks_or_stops(self):
        """Choosing to continue development suppresses all further blocks and tool stops in the session."""
        with tempfile.TemporaryDirectory() as directory:
            payload = prompt_payload(directory, used_percent=95, session_id="burn", prompt="start feature")
            data_dir = Path(directory) / "markers"
            first = handle_event(payload, data_dir)
            self.assertEqual(first["decision"], "block")

            # User chooses to continue
            continued = handle_event({**payload, "prompt": "continue"}, data_dir)
            self.assertEqual(continued["decision"], "allow")

            # Subsequent prompt turns in the same session and window are silent ALLOW
            for quota in (96, 98, 99):
                turn_payload = prompt_payload(directory, used_percent=quota, session_id="burn", prompt="keep working")
                self.assertEqual(handle_event(turn_payload, data_dir), ALLOW)

            # Tool executions (PostToolUse) in continuation turns are silent ALLOW
            post_tool = post_tool_payload(directory, primary_used_percent=99, session_id="burn", turn_id="turn-later")
            self.assertEqual(handle_event(post_tool, data_dir), ALLOW)

            # PreToolUse in continuation turns is also ALLOW
            pre_tool = {
                "hook_event_name": "PreToolUse",
                "session_id": "burn",
                "turn_id": "turn-later",
            }
            self.assertEqual(handle_event(pre_tool, data_dir), ALLOW)

    def test_continue_variations_recognized(self):
        for choice in ("continue", "Continue"):
            with self.subTest(choice=choice), tempfile.TemporaryDirectory() as directory:
                payload = prompt_payload(directory, used_percent=95, session_id="var", prompt="work")
                data_dir = Path(directory) / "markers"
                self.assertEqual(handle_event(payload, data_dir)["decision"], "block")
                continued = handle_event({**payload, "prompt": choice}, data_dir)
                self.assertEqual(continued["decision"], "allow")

    def test_weekly_limit_allows_exact_continue_at_three_percent_remaining(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = prompt_payload_with_weekly_limit(
                directory, weekly_used_percent=97, session_id="weekly", prompt="ordinary work",
            )
            data_dir = Path(directory) / "markers"
            first = handle_event(payload, data_dir)
            self.assertEqual(first["decision"], "block")
            self.assertIn("Weekly quota", first["reason"])
            continued = handle_event({**payload, "prompt": "continue"}, data_dir)
            self.assertEqual(continued["decision"], "allow")
            self.assertIn("Resuming the paused request", continued["reason"])

    def test_pending_choice_is_scoped_to_the_active_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "markers"
            first = prompt_payload(directory, used_percent=97, session_id="s", prompt="ordinary work")
            reset = prompt_payload(
                directory, used_percent=97, session_id="s", resets_at=RESET + 300, prompt="new work",
            )
            self.assertEqual(handle_event(first, data_dir)["decision"], "block")
            self.assertEqual(handle_event(reset, data_dir)["decision"], "block")

    def test_soft_warning_allows_with_one_handoff_nudge(self):
        """Removing soft-level deduplication would repeat the nudge."""
        with tempfile.TemporaryDirectory() as directory:
            payload = prompt_payload(directory, used_percent=85, session_id="s")
            data_dir = Path(directory) / "markers"
            first = handle_event(payload, data_dir)
            self.assertEqual(first["decision"], "allow")
            self.assertIn("$handoff-prepare", first["reason"])
            self.assertEqual(handle_event(payload, data_dir), {"decision": "allow"})

    def test_reset_time_rearms_the_warning(self):
        """Ignoring reset time in the marker key would suppress the second block."""
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "markers"
            first = prompt_payload(directory, used_percent=97, session_id="s")
            second = prompt_payload(directory, used_percent=97, session_id="s", resets_at=RESET + 300)
            self.assertEqual(handle_event(first, data_dir)["decision"], "block")
            self.assertEqual(handle_event(second, data_dir)["decision"], "block")

    def test_auto_compaction_warns_but_manual_is_silent(self):
        """Dropping the auto trigger branch would remove the handoff warning."""
        with tempfile.TemporaryDirectory() as directory:
            auto = handle_event({"trigger": "auto"}, Path(directory))
            self.assertEqual(auto["decision"], "allow")
            self.assertIn("$handoff-prepare", auto["reason"])
            self.assertEqual(handle_event({"trigger": "manual"}, Path(directory)), {"decision": "allow"})

    def test_valid_subagent_telemetry_bypasses_without_marker(self):
        """Removing the agent bypass would block and write a marker for child telemetry."""
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "markers"
            payload = prompt_payload(directory, used_percent=86, session_id="s")
            payload["agent_id"] = "child"
            self.assertEqual(
                handle_event(payload, data_dir),
                {"decision": "allow"},
            )
            self.assertFalse(data_dir.exists())

    def test_malformed_telemetry_allows_without_marker(self):
        """Treating unreadable telemetry as a warning would write a marker or block."""
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "markers"
            transcript = Path(directory) / "rollout.jsonl"
            transcript.write_text("not json\n")
            self.assertEqual(
                handle_event({"session_id": "s", "transcript_path": str(transcript)}, data_dir),
                {"decision": "allow"},
            )
            self.assertFalse(data_dir.exists())

    def test_malformed_prompt_payloads_fail_open(self):
        """Malformed hook payloads must remain harmless."""
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "markers"
            self.assertEqual(handle_event({"session_id": "s"}, data_dir), {"decision": "allow"})

    def test_router_keeps_v1_prompt_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = prompt_payload(directory, used_percent=97)
            self.assertEqual(handle_event(payload, Path(directory) / "markers")["decision"], "block")

    def test_turn_latch_key_is_turn_specific(self):
        with tempfile.TemporaryDirectory() as directory:
            marker_dir = Path(directory) / "markers"
            claim_turn_latch(marker_dir, "s", "turn-a", RESET, "five-hour")
            self.assertTrue(turn_latch_exists(marker_dir, "s", "turn-a", RESET, "five-hour"))
            self.assertFalse(turn_latch_exists(marker_dir, "s", "turn-b", RESET, "five-hour"))

    def test_missing_turn_or_session_never_creates_a_latch(self):
        with tempfile.TemporaryDirectory() as directory:
            marker_dir = Path(directory) / "markers"
            self.assertEqual(handle_post_tool_use({"turn_id": "t"}, marker_dir), ALLOW)
            self.assertFalse(marker_dir.exists())


class ToolLoopTests(unittest.TestCase):
    def setUp(self):
        clock = patch("time.time", return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)

    def test_post_tool_use(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "markers"
            payload = post_tool_payload(directory, primary_used_percent=97)

            decision = handle_event(payload, data_dir)

            self.assertEqual(decision["decision"], "allow")
            self.assertTrue(decision["tool_stop"])
            self.assertIn("$handoff-prepare", decision["reason"])
            self.assertTrue(turn_latch_exists(data_dir, "session", "turn", RESET, "five-hour"))

    def test_post_tool_stops_at_six_percent_for_each_quota_window(self):
        for window in ("five-hour", "weekly"):
            with self.subTest(window=window), tempfile.TemporaryDirectory() as directory:
                data_dir = Path(directory) / "markers"
                payload = post_tool_payload(
                    directory,
                    primary_used_percent=94 if window == "five-hour" else 10,
                    weekly_used_percent=94 if window == "weekly" else None,
                )
                decision = handle_event(payload, data_dir)
                self.assertEqual(decision["decision"], "allow")
                self.assertTrue(decision["tool_stop"])
                reset = RESET if window == "five-hour" else RESET + 100
                self.assertTrue(turn_latch_exists(data_dir, "session", "turn", reset, window))

    def test_post_tool_use_weekly_quota_creates_latch_and_advisory(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "markers"
            payload = post_tool_payload(directory, weekly_used_percent=97)

            decision = handle_event(payload, data_dir)

            self.assertEqual(decision["decision"], "allow")
            self.assertTrue(decision["tool_stop"])
            self.assertIn("Weekly quota", decision["reason"])
            self.assertTrue(turn_latch_exists(data_dir, "session", "turn", RESET + 100, "weekly"))

    def test_post_tool_use_both_strong_claims_both_latches(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "markers"
            payload = post_tool_payload(directory, primary_used_percent=97, weekly_used_percent=97)

            decision = handle_event(payload, data_dir)

            self.assertTrue(decision["tool_stop"])
            self.assertIn("Five-hour quota", decision["reason"])
            self.assertIn("Weekly quota", decision["reason"])
            self.assertTrue(turn_latch_exists(data_dir, "session", "turn", RESET, "five-hour"))
            self.assertTrue(turn_latch_exists(data_dir, "session", "turn", RESET + 100, "weekly"))

    def test_post_tool_use_failures_fail_open_without_latch(self):
        cases = ("healthy", "expired", "invalid", "missing-turn", "subagent", "unreadable", "storage")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                data_dir = Path(directory) / "markers"
                payload = post_tool_payload(directory, primary_used_percent=97)
                if case == "healthy":
                    payload = post_tool_payload(directory, primary_used_percent=90)
                elif case == "expired":
                    payload = post_tool_payload(directory, primary_used_percent=97, resets_at=NOW)
                elif case == "invalid":
                    Path(payload["transcript_path"]).write_text(json.dumps({
                        "type": "event_msg",
                        "payload": {"type": "token_count", "rate_limits": {"primary": {
                            "window_minutes": 60, "used_percent": 97, "resets_at": RESET,
                        }}},
                    }) + "\n")
                elif case == "missing-turn":
                    payload.pop("turn_id")
                elif case == "subagent":
                    payload["agent_id"] = "child"
                elif case == "unreadable":
                    payload["transcript_path"] = str(Path(directory) / "missing.jsonl")

                if case == "storage":
                    with patch("hooks.context_guard._claim_marker", side_effect=OSError("read-only")):
                        decision = handle_event(payload, data_dir)
                else:
                    decision = handle_event(payload, data_dir)

                self.assertEqual(decision, ALLOW)
                self.assertFalse(data_dir.exists())

    def test_post_tool_use_consumes_prompt_strong_warning_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "markers"
            post_tool = post_tool_payload(directory, primary_used_percent=97, session_id="shared")
            prompt = {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "shared",
                "transcript_path": post_tool["transcript_path"],
                "prompt": "$handoff-prepare",
            }

            self.assertTrue(handle_event(post_tool, data_dir)["tool_stop"])
            self.assertEqual(handle_event(prompt, data_dir), ALLOW)

    def test_post_tool_only_latches_the_turn_that_claims_the_strong_warning(self):
        """A later low-quota turn must be able to prepare the requested handoff."""
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "markers"
            first = post_tool_payload(
                directory, weekly_used_percent=97, session_id="shared", turn_id="first",
            )
            later = post_tool_payload(
                directory, weekly_used_percent=97, session_id="shared", turn_id="later",
            )

            self.assertTrue(handle_event(first, data_dir)["tool_stop"])
            self.assertEqual(handle_event(later, data_dir), ALLOW)
            self.assertEqual(handle_event({
                "hook_event_name": "PreToolUse", "session_id": "shared", "turn_id": "later",
            }, data_dir), ALLOW)


class HookOutputTests(unittest.TestCase):
    def test_allow_decision_emits_no_json(self):
        for event in ("UserPromptSubmit", "PreCompact", "PostToolUse", "PreToolUse"):
            self.assertIsNone(format_hook_output({"hook_event_name": event}, ALLOW))

    def test_soft_warning_uses_system_message(self):
        self.assertEqual(
            format_hook_output({"hook_event_name": "UserPromptSubmit"},
                               {"decision": "allow", "reason": "Prepare a handoff."}),
            {"systemMessage": "Prepare a handoff."},
        )

    def test_strong_warning_keeps_the_block_schema(self):
        self.assertEqual(
            format_hook_output({"hook_event_name": "UserPromptSubmit"},
                               {"decision": "block", "reason": "Prepare a handoff."}),
            {"decision": "block", "reason": "Prepare a handoff."},
        )


class ToolLoopOutputTests(unittest.TestCase):
    def test_pre_tool_denies_only_same_turn_latch(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "markers"
            self.assertTrue(claim_turn_latch(data_dir, "s", "t1", RESET, "five-hour"))
            payload = {"hook_event_name": "PreToolUse", "session_id": "s", "turn_id": "t1"}
            decision = handle_event(payload, data_dir)
            self.assertEqual(decision.get("decision"), "block")
            message = decision["reason"]
            self.assertIn("$handoff-prepare", message)
            self.assertEqual(format_hook_output(payload, decision), {
                "systemMessage": message,
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": message,
                },
            })
            self.assertEqual(handle_event({**payload, "turn_id": "t2"}, data_dir), ALLOW)
            self.assertEqual(handle_event({**payload, "session_id": "other"}, data_dir), ALLOW)

    def test_pre_tool_bypasses_subagents_and_invalid_identifiers(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "markers"
            claim_turn_latch(data_dir, "s", "t", RESET, "weekly")
            payload = {"hook_event_name": "PreToolUse", "session_id": "s", "turn_id": "t"}
            for overrides in ({"agent_id": "child"}, {"agent_id": None},
                              {"session_id": None}, {"turn_id": ""}, {"turn_id": []}):
                with self.subTest(overrides=overrides):
                    self.assertEqual(handle_event({**payload, **overrides}, data_dir), ALLOW)

    def test_pre_tool_never_detects_quota_without_post_tool_latch(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = post_tool_payload(directory, primary_used_percent=100, weekly_used_percent=100)
            payload["hook_event_name"] = "PreToolUse"
            data_dir = Path(directory) / "markers"
            self.assertEqual(handle_event(payload, data_dir), ALLOW)
            self.assertFalse(data_dir.exists())

    def test_pre_tool_observes_latch_with_unreadable_transcript(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "markers"
            claim_turn_latch(data_dir, "s", "t", RESET, "weekly")
            payload = {"hook_event_name": "PreToolUse", "session_id": "s", "turn_id": "t",
                       "transcript_path": str(Path(directory) / "missing.jsonl")}
            self.assertEqual(handle_event(payload, data_dir).get("decision"), "block")

    def test_pre_tool_missing_or_unavailable_storage_fails_open(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "markers"
            payload = {"hook_event_name": "PreToolUse", "session_id": "s", "turn_id": "t"}
            self.assertEqual(handle_event(payload, data_dir), ALLOW)
            self.assertFalse(data_dir.exists())
            data_dir.write_text("not a directory")
            self.assertEqual(handle_event(payload, data_dir), ALLOW)

    def test_pre_tool_unreadable_storage_fails_open(self):
        geteuid = getattr(os, "geteuid", None)
        if geteuid is None:
            self.skipTest("Windows does not expose POSIX directory access semantics")
        if geteuid() == 0:
            self.skipTest("Root can read directories with access removed")
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "markers"
            claim_turn_latch(data_dir, "s", "t", RESET, "five-hour")
            payload = {"hook_event_name": "PreToolUse", "session_id": "s", "turn_id": "t"}
            data_dir.chmod(0)
            try:
                self.assertEqual(handle_event(payload, data_dir), ALLOW)
            finally:
                data_dir.chmod(0o700)

    def test_post_tool_message_does_not_replace_result(self):
        message = "Stop expanding work and prepare a handoff."
        output = format_hook_output({"hook_event_name": "PostToolUse"}, {
            "decision": "allow", "reason": message, "tool_stop": True,
        })
        self.assertEqual(output, {
            "systemMessage": message,
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse", "additionalContext": message,
            },
        })

    def test_precompact_message_remains_nonblocking(self):
        payload = {"hook_event_name": "PreCompact", "trigger": "auto"}
        with tempfile.TemporaryDirectory() as directory:
            decision = handle_event(payload, Path(directory))
            self.assertEqual(format_hook_output(payload, decision), {
                "systemMessage": decision["reason"],
            })

    def test_real_hook_process_preserves_post_tool_result_then_denies_same_turn(self):
        """Catch a stale main formatter call or process-local latch storage."""
        with tempfile.TemporaryDirectory() as directory:
            payload = post_tool_payload(directory, primary_used_percent=97)
            payload["tool_response"] = {"output": "completed tool evidence"}
            data_dir = Path(directory) / "markers"

            def run_hook(event_payload):
                result = subprocess.run(
                    [sys.executable, str(ROOT / "hooks/context_guard.py")],
                    input=json.dumps(event_payload), text=True, capture_output=True,
                    env={**os.environ, "PLUGIN_DATA": str(data_dir)}, check=True, timeout=10,
                )
                self.assertEqual(result.stderr, "")
                return json.loads(result.stdout) if result.stdout else None

            post_output = run_hook(payload)
            self.assertEqual(set(post_output), {"systemMessage", "hookSpecificOutput"})
            self.assertEqual(post_output["hookSpecificOutput"], {
                "hookEventName": "PostToolUse", "additionalContext": post_output["systemMessage"],
            })
            pre_payload = {"hook_event_name": "PreToolUse", "session_id": "session", "turn_id": "turn"}
            pre_output = run_hook(pre_payload)
            self.assertEqual(pre_output["hookSpecificOutput"], {
                "hookEventName": "PreToolUse", "permissionDecision": "deny",
                "permissionDecisionReason": pre_output["systemMessage"],
            })
            self.assertIsNone(run_hook({**pre_payload, "turn_id": "new-turn"}))
            blocked = run_hook({
                **payload, "hook_event_name": "UserPromptSubmit", "turn_id": "new-turn",
                "prompt": "ordinary work",
            })
            self.assertEqual(blocked["decision"], "block")
            self.assertIn("`continue`", blocked["reason"])
            self.assertTrue(blocked["reason"].isascii())
            self.assertIsNone(run_hook({
                **payload, "hook_event_name": "UserPromptSubmit", "turn_id": "new-turn",
                "prompt": "$handoff-prepare",
            }))

    def test_real_hook_process_accepts_utf8_json_on_non_utf8_windows_stdio(self):
        """Codex sends UTF-8 JSON even when Windows Python pipes use a local code page."""
        for code_page in ("cp437", "cp936"):
            with self.subTest(code_page=code_page), tempfile.TemporaryDirectory() as directory:
                payload = prompt_payload(directory, used_percent=96, session_id="windows", prompt="work")
                payload["hook_event_name"] = "UserPromptSubmit"
                data_dir = Path(directory) / "markers"

                def run_hook(event_payload):
                    result = subprocess.run(
                        [sys.executable, str(ROOT / "hooks/context_guard.py")],
                        input=json.dumps(event_payload, ensure_ascii=False).encode("utf-8"),
                        capture_output=True,
                        env={**os.environ, "PLUGIN_DATA": str(data_dir),
                             "PYTHONIOENCODING": code_page, "PYTHONUTF8": "0"},
                        timeout=10,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
                    return json.loads(result.stdout) if result.stdout else None

                self.assertEqual(run_hook(payload)["decision"], "block")
                continued = run_hook({**payload, "prompt": "continue"})
                self.assertIsNotNone(continued)
                self.assertNotEqual(continued.get("decision"), "block")
                self.assertIn("Resuming the paused request", continued["systemMessage"])
                self.assertIsNone(run_hook({**payload, "prompt": "review the caf\u00e9 output"}))
