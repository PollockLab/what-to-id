"""Exact native Identify links, including the unchanged full-map batch contract."""

import json
import shutil
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

ASSETS = Path(__file__).parents[1] / "src/what_to_id/map_assets"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def evaluate(expression, include_map=False):
    script = (ASSETS / "identify_links.js").read_text()
    if include_map:
        script += (ASSETS / "map_area.js").read_text()
    script += f"\nconsole.log(JSON.stringify({expression}));"
    result = subprocess.run([NODE], input=script, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


@pytest.mark.parametrize("count", [0, 1, 200, 201, 10000])
def test_exact_batches_cover_each_safe_integer_once_with_bounded_native_urls(count):
    ids = [9007199254740991 - index for index in range(count)]
    prepared = evaluate(f"IdentifyLinks.prepare({json.dumps(ids)})")
    assert prepared["ids"] == ids and prepared["duplicateCount"] == 0
    batches = prepared["batches"]
    assert len(batches) == (count + 199) // 200
    actual = []
    for batch in batches:
        url = urlparse(batch["url"])
        assert url.scheme == "https" and url.netloc == "www.inaturalist.org"
        assert url.path == "/observations/identify"
        assert len(batch["url"]) <= 8000
        query = parse_qs(url.query)
        actual.extend(int(ident) for ident in query.pop("id")[0].split(","))
        assert query == {
            "quality_grade": ["needs_id"],
            "reviewed": ["false"],
            "place_id": ["any"],
            "per_page": ["200"],
        }
        assert 0 < batch["n"] <= 200
    assert actual == ids


def test_preparation_deduplicates_explicitly_without_mutating_input():
    prepared = evaluate(
        "(()=>{const ids=Object.freeze([3,1,3,2]);return IdentifyLinks.prepare(ids);})()"
    )
    assert prepared["ids"] == [3, 2, 1] and prepared["duplicateCount"] == 1
    assert prepared["batches"][0]["n"] == 3
    assert evaluate("IdentifyLinks.prepare(new Uint32Array([3,1,2])).ids") == [3, 2, 1]


@pytest.mark.parametrize(
    "expression",
    ["[0]", "[-1]", "[1.5]", "['1']", "[NaN]", "[Infinity]", "[9007199254740992]", "null"],
)
def test_invalid_ids_fail_clearly(expression):
    message = evaluate(
        f"(()=>{{try{{IdentifyLinks.prepare({expression});}}"
        "catch(error){return error.message;}})()"
    )
    assert "Observation IDs" in message


def test_more_than_ten_thousand_unique_ids_are_rejected():
    assert "10,000" in evaluate("""(()=>{try{
        IdentifyLinks.prepare(Array.from({length:10001},(_,i)=>i+1));}
        catch(error){return error.message;}})()""")


def test_map_aliases_preserve_existing_order_batch_shape_and_duplicate_behavior():
    actual = evaluate(
        """(()=>{const ids=[2,2,1];return {
      sameOrder:MapArea.order===IdentifyLinks.order,sameBatches:MapArea.batches===IdentifyLinks.batches,
      order:MapArea.order([22,99,55]),batches:MapArea.batches(ids),original:ids};})()""",
        include_map=True,
    )
    assert actual == {
        "sameOrder": True,
        "sameBatches": True,
        "order": [99, 55, 22],
        "original": [2, 2, 1],
        "batches": [
            {
                "url": "https://www.inaturalist.org/observations/identify?quality_grade=needs_id&reviewed=false&place_id=any&per_page=200&id=2,2,1",
                "n": 3,
                "lo": 1,
                "hi": 2,
            }
        ],
    }
