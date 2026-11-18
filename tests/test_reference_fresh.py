import json
import re
from datetime import date, timedelta
from pathlib import Path

import pytest

DATA = Path(__file__).parents[1] / "src/what_to_id"
MAX_AGE = timedelta(days=60)  # reference.yml refreshes weekly; this means it has stopped working


def fetched(doc):
    """The ISO date a list was fetched: its `fetched` field, else the date in `source`."""
    iso = doc.get("fetched") or re.search(r"fetched (\d{4}-\d{2}-\d{2})", doc["source"])[1]
    return date.fromisoformat(iso)


@pytest.mark.parametrize("name", ["invasive_bc_taxa", "at_risk_bc_taxa"])
def test_reference_list_is_fresh(name):
    age = date.today() - fetched(json.loads((DATA / f"{name}.json").read_text()))
    assert age <= MAX_AGE, f"{name}.json is {age.days} days old; run scripts/refresh_reference.py"


def test_fetched_reads_field_then_source():
    assert fetched({"fetched": "2026-01-02", "source": "x"}) == date(2026, 1, 2)
    assert fetched({"source": "y, fetched 2026-03-04, for z"}) == date(2026, 3, 4)
    with pytest.raises(TypeError):  # no date anywhere
        fetched({"source": "none"})
