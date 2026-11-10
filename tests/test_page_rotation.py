"""The study data Identify serves (page_rotation.py) and the dealing of its batches
(identify_study.js, run in node)."""

import json
import re
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from what_to_id.manifest import Manifest
from what_to_id.page import ARM_WORDS
from what_to_id.page_method import ORDER_DETAIL, ORDER_TEXT, method_section
from what_to_id.page_rotation import read_study, study_data, write_study
from what_to_id.served_log import served_rows

ARM_NAMES = ["recency", "gap_first", "similarity", "novelty", "surprise"]
STUDY_JS = Path(__file__).resolve().parents[1] / "src/what_to_id/identify_assets/identify_study.js"


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


def test_every_order_has_page_words_that_do_not_name_the_arm():
    assert set(ORDER_TEXT) == set(ARM_NAMES)
    for text in ORDER_TEXT.values():
        assert not any(w in text.lower() for w in ARM_WORDS)


def test_study_data_refuses_an_order_without_page_words():
    m = _manifest()
    m.arms = ["recency", "mystery"]
    with pytest.raises(ValueError, match="mystery"):
        study_data(m)


def test_every_order_has_detail_words_that_do_not_name_the_arm():
    assert set(ORDER_DETAIL) == set(ARM_NAMES)
    for text in ORDER_DETAIL.values():
        assert not any(w in text.lower() for w in ARM_WORDS)


def test_pipeline_steps_and_group_labels_come_from_the_build():
    m = _manifest()
    m.batch_size = 7
    how = method_section(m, 2)
    pipe = re.search(r'<div class="pipe".*?</ol></div></div>', how, re.S).group(0)
    assert re.findall(r"<b>([^<]+)</b>", pipe) == [
        "We collect",
        "We split them into 2 lists",
        "Each list gets its own order",
        "You press Next batch",
        "You identify",
        "We count",
    ]
    assert re.findall(r'<i class="when">([^<]+)</i>', pipe) == [
        "Each build",
        "During the blitz",
        "After",
    ]
    assert "up to 7 records" in pipe
    assert "species-level IDs on each list, against newest first, and whether the gap" in pipe
    assert "data-poor places first is judged on IDs weighted by map score" in pipe
    assert "Every day" not in pipe and "Only the order differs" not in pipe
    from what_to_id.page_method import _pipeline

    m.arms = ["recency", "similarity"]
    assert "weighted by map score" not in _pipeline(m, 2)
    # Each stage holds its own steps: 3, 2 and 1.
    stages = re.findall(r'<div class="stage">.*?</ol></div>', pipe, re.S)
    assert [s.count("<li>") for s in stages] == [3, 2, 1]
    _assert_blind(pipe)


def test_method_has_one_summary_numbered_methods_and_folds():
    how = method_section(_manifest(), 2)
    # The workflow and orders are readable without opening the technical sections.
    assert "In short" not in how
    assert '<details class="more"><summary>More detail: ' in how
    assert '<div class="pipe"' in how
    assert re.findall(r"<h3>(\d+)\. ", how) == [str(i) for i in range(1, 12)]
    assert "Why each identifier's batches rotate over the lists" not in how
    assert '<section id="methods-orders"><details class="method" open>' in how
    assert '<section id="methods-analysis"><details class="method">' in how
    assert '<nav class="toc"' not in how
    assert "batches of up to 2 records" in how
    _assert_blind(how)


def test_method_describes_this_builds_assignment():
    m = _manifest()
    assert m.assignment == "stratified"
    seeded = method_section(m, 2)
    assert "a seed shuffles" in seeded and "HMAC" not in seeded
    m.assignment = "keyed"
    keyed = method_section(m, 2)
    assert "HMAC-SHA256" in keyed and "seed shuffles" not in keyed


def test_method_keeps_claims_the_code_does_not_make_off_the_page():
    # Each phrase was on the page once and is false or overstated against the code.
    how = method_section(_manifest(), 2)
    for claim in (
        "nobody had",  # the placebo is before participants got the page; the page is public
        "private build file",  # keyed builds take the letters from the key
        "sit in the same batch",  # arms.py re-sorts groups by map score; cuts cross groups
        "shows only the records",  # Identify also hides records the viewer reviewed
        "Blitz the Gap map",  # the score is where-to-blitz's (cells.py)
        "up to 12 participants",  # 12 counts non-zero differences (analysis.sign_flip_p)
        "is set before",  # the protocol is a draft
    ):
        assert claim not in how, claim
    assert "counts 0" in how and "People with no difference drop out" in how


def test_method_links_point_at_files_and_headings_in_the_repo():
    root = Path(__file__).resolve().parents[1]
    how = method_section(_manifest(), 2)
    urls = re.findall(r'href="https://github\.com/PollockLab/what-to-id/blob/main/([^"]+)"', how)
    assert len(urls) >= 10
    for url in urls:
        path, _, anchor = url.partition("#")
        assert (root / path).is_file(), url
        if anchor:
            heads = re.findall(r"^#+ (.+)$", (root / path).read_text(), re.M)
            slugs = {re.sub(r"[^\w\- ]", "", h.lower()).replace(" ", "-") for h in heads}
            assert anchor in slugs, url


def test_study_data_puts_each_batch_at_its_index_and_names_no_arm():
    m = _manifest()
    d = study_data(m)
    assert d["lists"] == {"B": {"Aves": [[1, 2], [5, 6]], "Insecta": [[3]]}, "A": {"Aves": [[4]]}}
    assert d["build"] == m.created_at and d["day"] == "2026-09-01"
    assert d["names"] == {"Aves": "Birds (Aves)", "Insecta": "Insects (Insecta)"}
    assert "<summary>How the test works</summary>" in d["methods"]
    _assert_blind(json.dumps(d))


def test_study_data_refuses_a_batch_out_of_sequence():
    m = _manifest()
    m.batches["recency-Aves-005"] = m.batches.pop("recency-Aves-001")
    with pytest.raises(ValueError, match="out of sequence"):
        study_data(m)


def test_write_study_writes_json_and_refuses_a_leaked_arm_name(tmp_path):
    path = write_study(tmp_path, _manifest())
    assert path.name == "study.json" and read_study(path) == study_data(_manifest())
    m = _manifest()
    m.arm_labels = {"recency": "recency", "gap_first": "A"}
    with pytest.raises(ValueError, match="leaked"):
        write_study(tmp_path / "x", m)
    (tmp_path / "bad.json").write_text('{"lists": {"gap_first": {}}}')
    with pytest.raises(ValueError, match="leaked"):
        read_study(tmp_path / "bad.json")


def test_the_served_log_names_every_batch_the_page_can_serve():
    """The read-back joins public IDs to served batches by (label, group, batch_index): the study
    lists hold exactly the served log's batches at those indices, so no browser export is needed."""
    m = _manifest()
    rows = [
        {"arm": b["arm"], "group": b["group"], "batch_id": bid, "position": k, "id": i}
        for bid, b in m.batches.items()
        for k, i in enumerate(b["ids"])
    ]
    log = served_rows(pd.DataFrame(rows), m.arm_labels, pd.DataFrame({"id": []}), m.freeze)
    from_log = {
        key: g.sort_values("position")["id"].tolist()
        for key, g in log.groupby(["label", "group", "batch_index"])
    }
    lists = study_data(m)["lists"]
    from_page = {
        (label, group, k): ids
        for label, by_group in lists.items()
        for group, batches in by_group.items()
        for k, ids in enumerate(batches)
    }
    assert from_page == from_log


@pytest.fixture
def node_available():
    import shutil

    if not shutil.which("node"):
        pytest.skip("node not available")


def _node(source):
    """Runs source after ``var S = require(identify_study.js)`` and returns its printed JSON."""
    script = f"var S = require({json.dumps(str(STUDY_JS))});\n{source}"
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


DATA = """var data = {A: {G: [[10], [11]]}, B: {G: [[20], [21], [22]]}, C: {G: []},
  D: {G: [[30]]}};"""


def _drive(offsets):
    return _node(
        DATA
        + f"""
var state = {{perm: ["A", "B", "C", "D"], progress: {{}}, offsets: {json.dumps(offsets)}}};
var out = [];
for (var i = 0; i < 12; i++) {{
  var r = S.nextBatch(state, data, "G"); state = r.state;
  out.push({{done: r.done, label: r.label, ids: r.done ? null : data[r.label].G[r.index],
    n: r.batchNumber}});
}}
console.log(JSON.stringify(out));
"""
    )


def test_next_batch_deals_every_batch_once_in_turn(node_available):
    out = _drive({})
    served = [r for r in out if not r["done"]]
    # C has no batches in this group and is never visited; 2+3+0+1 batches, then done
    assert [r["label"] for r in served] == ["A", "B", "D", "A", "B", "B"]
    assert [r["ids"] for r in served] == [[10], [20], [30], [11], [21], [22]]
    assert [r["n"] for r in served] == [1, 2, 3, 4, 5, 6]
    assert [r["done"] for r in out] == [False] * 6 + [True] * 6
    assert all(r["label"] is None and r["n"] == 6 for r in out if r["done"])


def test_next_batch_offsets_deal_disjoint_starts(node_available):
    ids = [r["ids"][0] for r in _drive({"A": {"G": 1}, "B": {"G": 2}}) if not r["done"]]
    assert ids == [11, 22, 30, 10, 20, 21]


def test_start_over_resets_only_that_group(node_available):
    out = _node(
        """
var data = {A: {G: [[1], [2]], H: [[9]]}, B: {G: [[3]]}};
var state = {perm: ["A", "B"], progress: {}, offsets: {}, build: "d1",
  cur: {G: {label: "B", index: 0}, H: {label: "A", index: 0}}};
state = S.nextBatch(state, data, "G").state;
state = S.nextBatch(state, data, "G").state;
state = S.nextBatch(state, data, "H").state;
var before = JSON.stringify(state), reset = S.startOver(state, "G");
var again = S.nextBatch(reset, data, "G");
console.log(JSON.stringify({same: JSON.stringify(state) === before, reset: reset,
  ids: data[again.label].G[again.index], n: again.batchNumber}));
"""
    )
    assert out["same"], "startOver changed its input"
    assert "G" not in out["reset"]["progress"] and out["reset"]["progress"]["H"]["served"] == 1
    assert out["reset"]["cur"] == {"H": {"label": "A", "index": 0}}
    assert out["reset"]["perm"] == ["A", "B"] and out["reset"]["build"] == "d1"
    assert (out["ids"], out["n"]) == ([1], 1)


def test_group_progress_counts_all_lists_together(node_available):
    out = _node(
        """
var data = {A: {G: [[1], [2]], H: [[9]]}, B: {G: [[3]]}, C: {}};
var state = {perm: ["A", "B", "C"], progress: {}, offsets: {}};
var out = [S.groupProgress(state, data, "G"), S.groupProgress(state, data, "none")];
state = S.nextBatch(state, data, "G").state;
out.push(S.groupProgress(state, data, "G"));
for (var i = 0; i < 3; i++) state = S.nextBatch(state, data, "G").state;
out.push(S.groupProgress(state, data, "G"));
console.log(JSON.stringify(out));
"""
    )
    assert out == [
        {"opened": 0, "left": 3, "total": 3},
        {"opened": 0, "left": 0, "total": 0},
        {"opened": 1, "left": 2, "total": 3},
        {"opened": 3, "left": 0, "total": 3},
    ]


def test_a_new_build_keeps_the_turn_order_and_deals_afresh(node_available):
    out = _node(
        DATA
        + """
var r = 0, rand = function(){ r = (r + 0.37) % 1; return r; };
var first = S.fresh(null, data, "day1", rand).state;
var worked = S.nextBatch(first, data, "G").state;
var same = S.fresh(worked, data, "day1", rand), next = S.fresh(worked, data, "day2", rand);
var unworked = S.fresh(first, data, "day2", rand);
console.log(JSON.stringify({first: first, same: same, next: next, unworked: unworked.renewed}));
"""
    )
    first, same, nxt = out["first"], out["same"], out["next"]
    assert sorted(first["perm"]) == ["A", "B", "C", "D"] and first["build"] == "day1"
    assert set(first["offsets"]) == {"A", "B", "C", "D"}
    assert 0 <= first["offsets"]["B"]["G"] < 3 and first["offsets"]["C"]["G"] == 0
    assert same["renewed"] is False and same["state"]["progress"]["G"]["served"] == 1
    assert nxt["renewed"] is True and nxt["state"]["perm"] == first["perm"]
    assert nxt["state"]["progress"] == {} and nxt["state"]["build"] == "day2"
    assert out["unworked"] is False


def test_a_new_list_set_draws_a_new_turn_order(node_available):
    out = _node(
        DATA
        + """
var old = {perm: ["A", "B", "X"], progress: {}, build: "d"};
console.log(JSON.stringify(S.fresh(old, data, "d", Math.random).state.perm.sort()));
"""
    )
    assert out == ["A", "B", "C", "D"]


def _config(html):
    return json.loads(re.search(r"var IDENTIFY_CONFIG=(\{.*?\});</script>", html).group(1))


def test_identify_embeds_the_lists_but_not_the_fold_and_refuses_a_leak(tmp_path):
    from what_to_id import page_identify

    path = write_study(tmp_path, _manifest())
    html = page_identify.build(tmp_path, study=path).read_text()
    cfg = _config(html)
    assert set(cfg["study"]) == {"build", "day", "names", "lists"}
    assert 'href="terms.html#study"' in html and 'id="sgrid"' in html
    _assert_blind(html)
    assert _config(page_identify.render())["study"] is None
    leaked = tmp_path / "leaked.json"
    leaked.write_text(path.read_text().replace('"day"', '"novelty"'))
    with pytest.raises(ValueError, match="novelty"):
        page_identify.build(tmp_path, study=leaked)
