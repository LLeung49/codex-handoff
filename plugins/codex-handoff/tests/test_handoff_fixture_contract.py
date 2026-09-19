import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "fixtures" / "handoff-v2-1.md"


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
        self.assertLessEqual(count_rows(text, "L1: read now"), 3)
        self.assertLessEqual(count_rows(text, "L2: read conditionally"), 5)
        for row in rows(text, "L2: read conditionally"):
            self.assertIn("Trigger:", row)
            self.assertIn("Answers:", row)
