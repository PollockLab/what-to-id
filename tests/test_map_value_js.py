"""The map's "Sort by conservation status" order (map_value.js), run in node."""

import json
import shutil
import subprocess

import pytest

from what_to_id.page_map import _ASSETS

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node")


def order(ix, tax, taxa, value):
    script = (_ASSETS / "map_value.js").read_text() + (
        f"\nconsole.log(JSON.stringify(MapValue.order({json.dumps(ix)},{json.dumps(tax)},"
        f"MapValue.rows({json.dumps(taxa)},{json.dumps(value)}))));"
    )
    result = subprocess.run(["node"], input=script, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_tier_then_rounds_of_five_per_species_then_fewest_research_grade():
    taxa = [["A", "", 11, "species"], ["B", "", 12, "species"], ["C", "", 13, "species"]]
    value = [[11, 1, 900], [12, 1, 3]]  # both listed in Canada, B with fewer RG records; C none
    tax = [0] * 7 + [1] * 2 + [2] * 2
    got = order(list(range(11)), tax, taxa, value)
    # round 1: B's 2 (fewer RG), A's first 5; round 2: A's last 2; then C in map order
    assert got == [7, 8, 0, 1, 2, 3, 4, 5, 6, 9, 10]


def test_records_without_status_keep_map_order_and_empty_is_empty():
    taxa = [["A", "", 11, "species"]]
    assert order([3, 1, 2], [0, 0, 0, 0], taxa, []) == [3, 1, 2]
    assert order([], [], taxa, [[11, 2, 0]]) == []
