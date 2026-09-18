import json
import os
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


def rate_limit(used_percent):
    return {"window_minutes": 300, "used_percent": used_percent, "resets_at": RESET}


def prompt_payload(directory, used_percent, session_id="session", resets_at=RESET):
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
    return {"session_id": session_id, "transcript_path": str(transcript)}


def prompt_payload_with_weekly_limit(directory, weekly_used_percent, session_id="session"):
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
    return {"session_id": session_id, "transcript_path": str(transcript)}


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
        self.assertEqual(quota_warning(rate_limit(96)), "soft")
        self.assertEqual(quota_warning(rate_limit(97)), "strong")

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


class PluginMetadataTests(unittest.TestCase):
    def test_root_readme_documents_public_marketplace_installation(self):
        marketplace_root = next(
            candidate for candidate in (ROOT, *ROOT.parents)
            if (candidate / ".agents/plugins/marketplace.json").exists()
        )
        readme = (marketplace_root / "README.md").read_text()
        self.assertIn("codex plugin marketplace add LLeung49/codex-handoff --ref main", readme)
        self.assertIn("codex plugin add codex-handoff@codex-handoff", readme)
        self.assertNotIn("/Users/lucienleung", readme)

    def test_root_readme_documents_v2_skills_and_guard_limits(self):
        """Removing V2 safety guidance would leave marketplace users misinformed."""
        marketplace_root = next(
            candidate for candidate in (ROOT, *ROOT.parents)
            if (candidate / ".agents/plugins/marketplace.json").exists()
        )
        readme = " ".join((marketplace_root / "README.md").read_text().split())
        for requirement in (
            "$handoff-context-setup", "$handoff-prepare", "$handoff-continue",
            "PostToolUse", "PreToolUse", "尽力而为", "不会自动切换会话",
            "已完成的工具结果会被保留", "托管或特殊工具路径",
        ):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, readme)

    def test_root_readme_has_the_scannable_open_source_sections(self):
        """Keep the public README's onboarding modules and current hero asset."""
        marketplace_root = next(
            candidate for candidate in (ROOT, *ROOT.parents)
            if (candidate / ".agents/plugins/marketplace.json").exists()
        )
        readme = (marketplace_root / "README.md").read_text()
        for heading in ("## 适合什么情况？", "## 一次开发如何被保护？",
                        "## 会带来什么影响？", "## 三步开始使用"):
            with self.subTest(heading=heading):
                self.assertIn(heading, readme)
        self.assertIn("assets/codex-handoff-01-carry-forward.png", readme)
        self.assertTrue(
            (marketplace_root / "assets/codex-handoff-01-carry-forward.png").is_file()
        )

    def test_root_readme_keeps_its_five_handoff_images(self):
        """Keep each visual explanation linked to a shipped project asset."""
        marketplace_root = next(
            candidate for candidate in (ROOT, *ROOT.parents)
            if (candidate / ".agents/plugins/marketplace.json").exists()
        )
        readme = (marketplace_root / "README.md").read_text()
        illustrations = (
            "assets/codex-handoff-00-origin-story.png",
            "assets/codex-handoff-01-carry-forward.png",
            "assets/codex-handoff-02-handoff-envelope.png",
            "assets/codex-handoff-03-quota-guard.png",
            "assets/codex-handoff-04-protective-block.png",
        )
        for illustration in illustrations:
            with self.subTest(illustration=illustration):
                self.assertIn(illustration, readme)
                self.assertTrue((marketplace_root / illustration).is_file())

    def test_root_readme_does_not_link_to_local_docs(self):
        """Published onboarding must not link to user-local documentation."""
        marketplace_root = next(
            candidate for candidate in (ROOT, *ROOT.parents)
            if (candidate / ".agents/plugins/marketplace.json").exists()
        )
        readme = (marketplace_root / "README.md").read_text()
        self.assertNotIn("docs/superpowers", readme)
        self.assertIn("/docs/", (marketplace_root / ".gitignore").read_text())

    def test_plugin_readme_validates_all_v2_skills(self):
        """A released V2 plugin must validate the newly added setup skill."""
        readme = (ROOT / "README.md").read_text()
        self.assertIn("skills/handoff-context-setup", readme)

    def test_marketplace_points_to_the_nested_plugin(self):
        marketplace_root = next(
            (candidate for candidate in (ROOT, *ROOT.parents)
             if (candidate / ".agents/plugins/marketplace.json").exists()),
            ROOT,
        )
        marketplace = json.loads(
            (marketplace_root / ".agents/plugins/marketplace.json").read_text()
        )
        entry = marketplace["plugins"][0]
        self.assertEqual(marketplace["name"], "codex-handoff")
        self.assertEqual(entry["name"], "codex-handoff")
        self.assertEqual(entry["source"]["path"], "./plugins/codex-handoff")

    def test_plugin_manifest_declares_the_plugin_and_skill_root(self):
        manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text())
        self.assertEqual(manifest["name"], "codex-handoff")
        self.assertEqual(manifest["skills"], "./skills/")

    def test_plugin_manifest_uses_the_v0_2_0_release_version(self):
        manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text())
        self.assertTrue(manifest["version"].startswith("0.2.0+codex."))


class HookConfigurationTests(unittest.TestCase):
    def test_hooks_register_all_four_lifecycle_events(self):
        hooks = json.loads((ROOT / "hooks/hooks.json").read_text())
        self.assertEqual(set(hooks["hooks"]), {
            "UserPromptSubmit", "PreCompact", "PostToolUse", "PreToolUse",
        })

    def test_hooks_resolve_the_guard_from_the_plugin_root(self):
        """Relative paths run from the session cwd, not the plugin directory."""
        hooks = json.loads((ROOT / "hooks/hooks.json").read_text())
        for event in hooks["hooks"]:
            command = hooks["hooks"][event][0]["hooks"][0]["command"]
            self.assertEqual(command, 'python3 "$PLUGIN_ROOT/hooks/context_guard.py"')

    def test_tool_hooks_match_all_tools_synchronously(self):
        hooks = json.loads((ROOT / "hooks/hooks.json").read_text())["hooks"]
        for event in ("PreToolUse", "PostToolUse"):
            self.assertEqual(hooks.get(event), [{
                "matcher": "*",
                "hooks": [{
                    "type": "command",
                    "command": 'python3 "$PLUGIN_ROOT/hooks/context_guard.py"',
                }],
            }])


class SkillContractTests(unittest.TestCase):
    """Check the required agent-visible contract, not runtime agent compliance."""

    def read_skill(self, name):
        path = ROOT / "skills" / name / "SKILL.md"
        self.assertTrue(path.is_file(), f"Missing skill: {name}")
        return " ".join(path.read_text().split())

    def test_continue_skill_forbids_automatic_execution(self):
        content = self.read_skill("handoff-continue")
        self.assertIn("does not edit", content)
        self.assertIn("does not run commands", content)

    def test_context_setup_requires_approval_before_writing(self):
        content = self.read_skill("handoff-context-setup")
        for requirement in (
            "read-only discovery", "explicit user approval", "exact source paths",
            "draft", "Before approval, do not persist",
            "docs/agent-context.md", "docs/project-status.md",
        ):
            self.assertIn(requirement, content)

    def test_context_setup_bounds_sources_and_records_authority(self):
        content = self.read_skill("handoff-context-setup")
        for requirement in (
            "at most eight", "source-of-truth hierarchy", "last verified",
            "known gaps", "Do not treat old plans as active",
            "Do not change `AGENTS.md`, `CLAUDE.md`, source code, or `.gitignore`",
        ):
            self.assertIn(requirement, content)

    def test_context_setup_separates_status_from_authority(self):
        content = self.read_skill("handoff-context-setup")
        for requirement in (
            "Delivered and accepted", "acceptance evidence", "One active work item",
            "Blocked work", "Decisions awaiting the user", "Deferred candidates",
            "not authorized", "latest task handoff", "remain the source of truth",
        ):
            self.assertIn(requirement, content)

    def test_prepare_requires_scope_and_evidence(self):
        content = self.read_skill("handoff-prepare")
        sections = (
            "Original user objective", "Scope contract", "Required context",
            "Current state", "Decisions and rationale", "Relevant artifacts",
            "Evidence", "Known issues triage", "Git state", "Continuation contract",
        )
        for section in sections:
            self.assertIn(section, content)
        positions = [content.index(section) for section in sections]
        self.assertEqual(positions, sorted(positions))
        for requirement in ("stop condition", "reading manifest", "unverified", "expected base"):
            self.assertIn(requirement, content)

    def test_prepare_keeps_snapshot_immutable_and_status_opt_in(self):
        content = self.read_skill("handoff-prepare")
        for requirement in (
            "one immutable", ".handoff/<UTC timestamp>-<slug>.md",
            "Never overwrite", "status refresh in the same prompt",
            "If either durable document is absent", "$handoff-context-setup",
            "do not create it", "Do not change `.gitignore`",
        ):
            self.assertIn(requirement, content)

    def test_continue_reads_only_ordered_context(self):
        content = self.read_skill("handoff-continue")
        for requirement in (
            "1. Repository instructions", "2. `docs/agent-context.md`",
            "3. The selected handoff", "4. Only the handoff's required task-specific artifacts",
        ):
            self.assertIn(requirement, content)
        positions = [content.index(prefix) for prefix in ("1. Repository", "2. `docs/", "3. The selected", "4. Only")]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("Do not recursively follow links", content)
        self.assertIn("at most eight", content)

    def test_continue_stops_after_alignment(self):
        content = self.read_skill("handoff-continue")
        for requirement in (
            "context-alignment report", "ends after", "does not run commands",
            "loaded sources", "missing/ambiguous sources", "stop condition",
            "confirmed evidence", "unverified claims", "user decisions",
            "user authorizes a scoped next action", "commits, pushes",
        ):
            self.assertIn(requirement, content)

    def test_continue_handles_v1_and_untrusted_or_ambiguous_sources(self):
        content = self.read_skill("handoff-continue")
        for requirement in (
            "V1", "Goal", "Suggested next steps", "absent", "do not invent",
            "Missing, stale, or contradictory", "ambiguous", "ask the user to choose",
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


class DecisionTests(unittest.TestCase):
    def setUp(self):
        clock = patch("time.time", return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)

    def test_real_rollout_blocks_once(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = {"session_id": "real", "transcript_path": str(ROOT / "tests/fixtures/codex-rollout.jsonl")}
            data_dir = Path(directory) / "markers"
            self.assertEqual(handle_event(payload, data_dir)["decision"], "block")
            self.assertEqual(handle_event(payload, data_dir), {"decision": "allow"})

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

    def test_strong_warning_blocks_only_once(self):
        """Removing the atomic marker would make the repeat prompt block."""
        with tempfile.TemporaryDirectory() as directory:
            payload = prompt_payload(directory, used_percent=97, session_id="s")
            data_dir = Path(directory) / "markers"
            self.assertEqual(handle_event(payload, data_dir)["decision"], "block")
            self.assertEqual(handle_event(payload, data_dir), {"decision": "allow"})

    def test_weekly_limit_blocks_once_at_three_percent_remaining(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = prompt_payload_with_weekly_limit(directory, weekly_used_percent=97, session_id="weekly")
            data_dir = Path(directory) / "markers"
            first = handle_event(payload, data_dir)
            self.assertEqual(first["decision"], "block")
            self.assertIn("Weekly quota", first["reason"])
            self.assertEqual(handle_event(payload, data_dir), {"decision": "allow"})

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
                    payload = post_tool_payload(directory, primary_used_percent=96)
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
            }

            self.assertTrue(handle_event(post_tool, data_dir)["tool_stop"])
            self.assertEqual(handle_event(prompt, data_dir), ALLOW)


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
        if os.geteuid() == 0:
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
            self.assertIsNone(run_hook({**payload, "hook_event_name": "UserPromptSubmit"}))
