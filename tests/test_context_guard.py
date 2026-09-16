import json
import unittest
from pathlib import Path

from hooks.context_guard import latest_primary_rate_limit, quota_warning


ROOT = Path(__file__).resolve().parents[1]


def rate_limit(used_percent):
    return {"used_percent": used_percent, "resets_at": 100}


NON_NULL_EVENT = json.dumps({
    "type": "token_count",
    "rate_limits": {"primary": {"window_minutes": 300, "used_percent": 10, "resets_at": 100}},
})
NULL_EVENT = json.dumps({
    "type": "token_count",
    "rate_limits": {"primary": None},
})
NEWER_EVENT = json.dumps({
    "type": "token_count",
    "rate_limits": {"primary": {"window_minutes": 300, "used_percent": 20, "resets_at": 200}},
})


class TelemetryTests(unittest.TestCase):
    def test_uses_newest_non_null_primary_rate_limit(self):
        with self.subTest("newest snapshot"):
            from tempfile import TemporaryDirectory

            with TemporaryDirectory() as directory:
                rollout = Path(directory) / "rollout.jsonl"
                rollout.write_text(NON_NULL_EVENT + "\n" + NULL_EVENT + "\n" + NEWER_EVENT + "\n")
                self.assertEqual(latest_primary_rate_limit(rollout)["resets_at"], 200)

    def test_quota_warning_boundaries(self):
        self.assertIsNone(quota_warning(rate_limit(74.9)))
        self.assertEqual(quota_warning(rate_limit(75)), "soft")
        self.assertEqual(quota_warning(rate_limit(85)), "strong")


class PluginMetadataTests(unittest.TestCase):
    def test_plugin_manifest_declares_the_plugin_and_skill_root(self):
        manifest = json.loads((ROOT / ".codex-plugin/plugin.json").read_text())
        self.assertEqual(manifest["name"], "codex-handoff")
        self.assertEqual(manifest["skills"], "./skills/")
