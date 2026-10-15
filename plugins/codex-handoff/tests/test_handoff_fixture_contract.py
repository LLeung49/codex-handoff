import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PLUGIN_ROOT = ROOT.parent
FIXTURE = ROOT / "fixtures" / "handoff-v2-1.md"
ACTIVE_FIXTURE = ROOT / "fixtures" / "handoff-v2-1-active-rebuild.md"
OLDER_V21_FIXTURE = ROOT / "fixtures" / "handoff-v2-1-older-order.md"
LEGACY_FIXTURE = ROOT / "fixtures" / "handoff-v1.md"


def rows(text: str, heading: str) -> list[str]:
    lines = text.splitlines()
    start = lines.index(f"### {heading}") + 1
    result = []
    for line in lines[start:]:
        if line.startswith("### ") or line.startswith("## "):
            break
        if line.startswith("- "):
            result.append(line)
    return result


def count_rows(text: str, heading: str) -> int:
    return len(rows(text, heading))


class V21FixtureTests(unittest.TestCase):
    def test_v21_fixture_has_bounded_progressive_disclosure(self):
        text = FIXTURE.read_text()
        self.assertIn("## User checkpoint", text)
        self.assertIn("## Delivery and acceptance ledger", text)
        self.assertLessEqual(count_rows(text, "L1: next-action sources"), 3)
        self.assertLessEqual(count_rows(text, "L2: read conditionally"), 5)
        for row in rows(text, "L2: read conditionally"):
            self.assertIn("Trigger:", row)
            self.assertIn("Answers:", row)

    def test_l0_is_first_three_sections_and_does_not_auto_load_l1(self):
        text = FIXTURE.read_text()
        headings = [line for line in text.splitlines() if line.startswith("## ")]
        self.assertEqual(headings[0:3], [
            "## User checkpoint", "## Task contract", "## Next action and boundary",
        ])
        self.assertIn("Do not automatically read L1 or L2", text)
        self.assertNotIn("Read L0 and L1", text)

    def test_active_rebuild_example_keeps_snapshot_and_authority_distinct(self):
        text = ACTIVE_FIXTURE.read_text()
        l0 = text.split("## Delivery and acceptance ledger", 1)[0]
        self.assertIn("2026-10-14T17:42:52Z", l0)
        self.assertIn("market-full-qmt-20261014", l0)
        self.assertIn("current status unknown", l0)
        self.assertIn("untracked", text)
        self.assertIn("resolved", text)
        self.assertIn("pending", text)
        self.assertIn("separate", text)
        self.assertIn("one read-only status check", l0)
        self.assertIn("do not start a new rebuild", l0)


class SkillBehaviorContractTests(unittest.TestCase):
    def skill(self, name: str) -> str:
        return (PLUGIN_ROOT / "skills" / name / "SKILL.md").read_text()

    def test_prepare_requires_atomic_next_action_and_dated_live_state(self):
        text = " ".join(self.skill("handoff-prepare").split())
        self.assertIn("one atomic next action", text)
        self.assertIn("timestamped snapshot", text)
        self.assertIn("current status is unknown", text)
        self.assertIn("untracked", text)
        self.assertIn("resolved", text)
        self.assertIn("pending", text)
        self.assertIn("separate", text)

    def test_continue_revalidates_old_live_state_only_after_authorization(self):
        text = " ".join(self.skill("handoff-continue").split())
        self.assertIn("first three sections", text)
        self.assertIn("Do not automatically read L1 or L2", text)
        self.assertIn("revalidate", text)
        self.assertIn("batch identity", text)
        self.assertIn("older V2.1", text)


class LegacyFixtureTests(unittest.TestCase):
    def test_older_v21_layout_is_preserved_for_compatibility(self):
        text = OLDER_V21_FIXTURE.read_text()
        self.assertLess(text.index("## Delivery and acceptance ledger"),
                        text.index("## Next action and boundary"))
        self.assertIn("### L1: read now", text)
        skill = (PLUGIN_ROOT / "skills" / "handoff-continue" / "SKILL.md").read_text()
        self.assertIn("older V2.1", skill)
        self.assertIn("Do not treat `read now` as an", skill)

    def test_v1_fixture_remains_readable_without_v21_sections(self):
        text = LEGACY_FIXTURE.read_text()
        for heading in ("## Goal", "## Current state", "## Suggested next steps"):
            self.assertIn(heading, text)
        for v21_heading in ("## User checkpoint", "## Minimal reading package"):
            self.assertNotIn(v21_heading, text)
