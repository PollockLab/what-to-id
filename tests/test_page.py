import re
from pathlib import Path

from what_to_id.arms import ARMS
from what_to_id.page import ARM_WORDS, group_name


def test_group_name():
    assert group_name("Aves") == "Birds (Aves)"
    assert group_name("Unknownia") == "Unknownia"


def test_leak_checks_cover_every_list_name():
    # The published-page greps in CI and the daily build must know every list name.
    assert set(ARMS) <= set(ARM_WORDS)
    root = Path(__file__).resolve().parents[1]
    for rel in (".github/workflows/map.yml", "scripts/daily.sh"):
        m = re.search(r"grep -ril -E '([^']+)'", (root / rel).read_text())
        assert m, rel
        assert [w for w in ARM_WORDS if not re.search(m.group(1), w)] == [], rel
