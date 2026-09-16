import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hooks.context_guard import handle_event, latest_primary_rate_limit, quota_warning


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
        self.assertIsNone(quota_warning(rate_limit(74.9)))
        self.assertEqual(quota_warning(rate_limit(75)), "soft")
        self.assertEqual(quota_warning(rate_limit(85)), "soft")
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


class HookConfigurationTests(unittest.TestCase):
    def test_hooks_register_prompt_and_precompact_events(self):
        hooks = json.loads((ROOT / "hooks/hooks.json").read_text())
        self.assertEqual(set(hooks["hooks"]), {"UserPromptSubmit", "PreCompact"})


class SkillContractTests(unittest.TestCase):
    def test_continue_skill_forbids_automatic_execution(self):
        content = (ROOT / "skills/handoff-continue/SKILL.md").read_text()
        self.assertIn("does not edit", content)
        self.assertIn("does not run commands", content)


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

    def test_soft_warning_allows_with_one_handoff_nudge(self):
        """Removing soft-level deduplication would repeat the nudge."""
        with tempfile.TemporaryDirectory() as directory:
            payload = prompt_payload(directory, used_percent=75, session_id="s")
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
