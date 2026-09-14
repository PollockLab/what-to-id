import json
import re

import pytest

from what_to_id.manifest import Manifest
from what_to_id.page import ARM_WORDS
from what_to_id.page_rotation import (
    ORDER_TEXT,
    ROTATION_JS,
    render_rotation_index,
    write_rotation_site,
)

ARM_NAMES = ["recency", "gap_first", "similarity", "novelty"]


def _manifest():
    return Manifest(
        freeze="2026-09-01",
        d1="2026-09-15",
        seed=0,
        batch_size=2,
        arms=["recency", "gap_first"],
        arm_labels={"recency": "B", "gap_first": "A"},
        pool_sha256="0" * 64,
        pool_rows=6,
        design="rotation",
        batches={
            "recency-Aves-000": {
                "arm": "recency",
                "group": "Aves",
                "url": "https://x?id=1,2",
                "ids": [1, 2],
            },
            "recency-Aves-001": {
                "arm": "recency",
                "group": "Aves",
                "url": "https://x?id=5,6",
                "ids": [5, 6],
            },
            "recency-Insecta-000": {
                "arm": "recency",
                "group": "Insecta",
                "url": "https://x?id=3",
                "ids": [3],
            },
            "gap_first-Aves-000": {
                "arm": "gap_first",
                "group": "Aves",
                "url": "https://y",
                "ids": [4],
            },
        },
    )


def _assert_blind(html: str) -> None:
    low = html.lower()
    for name in ARM_NAMES:
        assert name not in low


def test_render_rotation_index_blind_and_minimal():
    html = render_rotation_index(_manifest(), title="What to ID next in BC")
    _assert_blind(html)
    assert "batch_id" not in html
    assert "recency-Aves-000" not in html
    assert "<img" not in html
    assert "Next batch" in html
    assert "Batch 0" in html


def test_render_rotation_index_explains_the_cycle():
    html = render_rotation_index(_manifest(), title="t")
    assert html.count('<span class="n">') == 2
    assert "up to 2 records" in html
    assert "next of 2 lists" in html


def test_render_rotation_index_explains_the_method_for_this_builds_orders():
    html = render_rotation_index(_manifest(), title="t")
    assert "How the test works" in html
    assert "Newest first." in html and "Data-poor places first." in html
    assert "Look-alike" not in html and "Unfamiliar" not in html
    _assert_blind(html)


def test_every_order_has_page_words_that_do_not_name_the_arm():
    assert set(ORDER_TEXT) == set(ARM_NAMES)
    for text in ORDER_TEXT.values():
        assert not any(w in text.lower() for w in ARM_WORDS)


def test_render_rotation_index_refuses_an_order_without_page_words():
    m = _manifest()
    m.arms = ["recency", "mystery"]
    with pytest.raises(ValueError, match="mystery"):
        render_rotation_index(m, title="t")


def test_render_rotation_index_data_has_every_url_once_in_order():
    m = _manifest()
    html = render_rotation_index(m, title="t")
    match = re.search(r"var DATA=(\{.*?\});var GROUP_NAMES", html)
    assert match
    data = json.loads(match.group(1))
    assert data == {
        "B": {"Aves": ["https://x?id=1,2", "https://x?id=5,6"], "Insecta": ["https://x?id=3"]},
        "A": {"Aves": ["https://y"]},
    }
    all_urls = [u for by_group in data.values() for urls in by_group.values() for u in urls]
    assert sorted(all_urls) == sorted(b["url"] for b in m.batches.values())
    assert len(all_urls) == len(set(all_urls))


def test_write_rotation_site_writes_only_index(tmp_path):
    written = write_rotation_site(tmp_path, _manifest())
    names = sorted(p.name for p in written)
    assert names == ["index.html"]
    html = (tmp_path / "index.html").read_text()
    _assert_blind(html)


def test_write_rotation_site_refuses_leaked_arm_name(tmp_path):
    m = _manifest()
    m.arm_labels = {"recency": "recency", "gap_first": "A"}
    with pytest.raises(ValueError, match="leaked"):
        write_rotation_site(tmp_path, m)


@pytest.fixture
def node_available():
    import shutil

    if not shutil.which("node"):
        pytest.skip("node not available")


DRIVER = """
var labels = ["A", "B", "C", "D"];
var data = {
  A: {G: ["A-0", "A-1"]},
  B: {G: ["B-0", "B-1", "B-2"]},
  C: {G: []},
  D: {G: ["D-0"]}
};
var state = {perm: labels, progress: {}, offsets: OFFSETS};
var served = [];
var results = [];
for (var i = 0; i < 12; i++) {
  var res = nextBatch(state, data, "G");
  state = res.state;
  results.push({done: res.done, label: res.label, url: res.url, batchNumber: res.batchNumber});
  if (!res.done) served.push(res.label);
}
console.log(JSON.stringify({results: results, served: served}));
"""


def _drive(tmp_path, offsets):
    """Extract the pure nextBatch() step function and drive it with a small node script."""
    import subprocess

    fn_match = re.search(r"function nextBatch\(state, data, group\) \{.*?\n\}", ROTATION_JS, re.S)
    assert fn_match, "nextBatch function not found in ROTATION_JS"
    script = tmp_path / "drive.js"
    script.write_text(fn_match.group(0) + DRIVER.replace("OFFSETS", json.dumps(offsets)))
    out = subprocess.run(["node", str(script)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_next_batch_js_offsets_deal_disjoint_starts(tmp_path, node_available):
    payload = _drive(tmp_path, {"A": {"G": 1}, "B": {"G": 2}})
    urls = [r["url"] for r in payload["results"] if not r["done"]]
    assert urls == ["A-1", "B-2", "D-0", "A-0", "B-0", "B-1"]
    assert sorted(urls) == ["A-0", "A-1", "B-0", "B-1", "B-2", "D-0"]


def test_next_batch_js_logic(tmp_path, node_available):
    payload = _drive(tmp_path, {})
    results = payload["results"]
    served = payload["served"]

    # exactly sum(counts) = 2+3+0+1 = 6 batches served, then done for the rest
    assert served == ["A", "B", "D", "A", "B", "B"]
    assert [r["done"] for r in results] == [False] * 6 + [True] * 6
    assert all(r["url"] is None for r in results if r["done"])
    assert [r["url"] for r in results if not r["done"]] == [
        "A-0",
        "B-0",
        "D-0",
        "A-1",
        "B-1",
        "B-2",
    ]
    # C, which has no batches in this group, is never visited
    assert "C" not in served
    # each label's pointer counts 0,1,2,... as it is repeatedly chosen
    assert [r["batchNumber"] for r in results if not r["done"]] == [1, 2, 3, 4, 5, 6]
    # once exhausted, done stays true and batchNumber stays at the last served count
    assert all(r["batchNumber"] == 6 for r in results if r["done"])


def test_runner_offers_start_over_with_undo():
    html = render_rotation_index(_manifest(), title="t")
    assert 'id="startOver"' in html and "Start over" in html
    assert 'id="undoBtn"' in html
    _assert_blind(html)


def test_start_over_js_resets_only_that_group(tmp_path, node_available):
    import subprocess

    fns = [
        re.search(rf"function {name}\(state, [a-z]+(, group)?\) \{{.*?\n\}}", ROTATION_JS, re.S)
        for name in ("nextBatch", "startOver")
    ]
    assert all(fns), "nextBatch or startOver not found in ROTATION_JS"
    script = tmp_path / "start_over.js"
    script.write_text(
        "\n".join(f.group(0) for f in fns)
        + """
var data = {A: {G: ["A-0", "A-1"], H: ["A-h"]}, B: {G: ["B-0"]}};
var state = {perm: ["A", "B"], progress: {}, offsets: {}, build: "d1"};
state = nextBatch(state, data, "G").state;
state = nextBatch(state, data, "G").state;
state = nextBatch(state, data, "H").state;
var before = JSON.stringify(state);
var reset = startOver(state, "G");
var again = nextBatch(reset, data, "G");
console.log(JSON.stringify({same: JSON.stringify(state) === before, reset: reset,
  url: again.url, n: again.batchNumber}));
"""
    )
    out = json.loads(
        subprocess.run(["node", str(script)], capture_output=True, text=True, check=True).stdout
    )
    assert out["same"], "startOver mutated its input"
    assert "G" not in out["reset"]["progress"]
    assert out["reset"]["progress"]["H"]["served"] == 1
    assert out["reset"]["perm"] == ["A", "B"] and out["reset"]["build"] == "d1"
    assert (out["url"], out["n"]) == ("A-0", 1)


def test_page_embeds_build_id():
    m = _manifest()
    m.created_at = "2026-11-03T06:00:00Z"
    html = render_rotation_index(m, title="t")
    assert 'var BUILD="2026-11-03T06:00:00Z";' in html


def test_new_build_keeps_cycle_and_resets_batches(tmp_path, node_available):
    import subprocess

    block = re.search(r"  if \(state\.build !== BUILD\) \{.*?\n  \}", ROTATION_JS, re.S)
    assert block, "build reset block not found in ROTATION_JS"
    old = {"perm": ["B", "A"], "progress": {"Aves": {"step": 3}}, "offsets": {"A": {"Aves": 1}}}
    script = tmp_path / "reset.js"
    script.write_text(
        "var out = [];\n"
        f"[['day1', 'day2'], ['day2', 'day2']].forEach(function(p){{\n"
        f"  var state = Object.assign({json.dumps(old)}, {{build: p[0]}}), BUILD = p[1];\n"
        f"{block.group(0)}\n"
        "  out.push(state);\n"
        "});\n"
        "console.log(JSON.stringify(out));\n"
    )
    new_build, same_build = json.loads(
        subprocess.run(["node", str(script)], capture_output=True, text=True, check=True).stdout
    )
    assert new_build == {"perm": ["B", "A"], "progress": {}, "build": "day2"}
    assert same_build["progress"] == old["progress"] and same_build["offsets"] == old["offsets"]
