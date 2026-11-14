"""terms.html: every glossary key is an anchor, every More link lands on one, the copied
explanations equal their sources, and the study section says what the study does."""

import json
import re
from pathlib import Path

from what_to_id import page_identify, page_nav, terms_page
from what_to_id.glossary import GLOSSARY

SRC = Path(page_nav.__file__).parent


def _ids(html):
    return set(re.findall(r'\bid="([^"]+)"', html))


def test_every_glossary_key_is_one_anchor_in_one_group():
    grouped = [k for keys in terms_page.GROUPS.values() for k in keys]
    assert sorted(grouped) == sorted(GLOSSARY)
    html = terms_page.render()
    for key in GLOSSARY:
        assert f'<dt id="{key}">' in html
    assert html.count("<dt id=") == len(GLOSSARY)
    assert "Needs ID</dt>" in html and "Narrow it down</dt>" in html


def test_labels_read_id_as_ID_and_match_the_page():
    assert terms_page.label("agreeing-ids") == "Agreeing IDs"
    assert terms_page.label("share-needing-id") == "Share needing ID"
    assert terms_page.label("identified-to-rank") == "Identified to rank"
    # the user filter's tick labels on the map
    assert terms_page.label("not-identified-by-me") == "Hide records the user identified"
    assert terms_page.label("my-taxa") == "Only the user's genera"
    assert terms_page.label("observer-filter") == "Only records the user observed"


def test_every_more_link_targets_an_anchor():
    data = re.search(r'id="explain-data">(.*?)</script>', page_nav.nav("map.html")).group(1)
    ids = _ids(terms_page.render())
    hrefs = {k: v[2] for k, v in json.loads(data).items()}
    assert hrefs.keys() == GLOSSARY.keys()
    for key, href in hrefs.items():
        page, _, frag = href.partition("#")
        assert page == "terms.html" and frag in ids, key
    assert "target='_blank'" in (SRC / "site_assets/explain.js").read_text()


def test_the_copied_explanations_equal_their_sources():
    html = terms_page.render()
    text = lambda p: (SRC / p).read_text()  # noqa: E731
    sources = {
        "identify": text("identify_assets/identify.html"),
        "confusion": text("confusion_assets/confusion.html"),
        "tree": text("tree_assets/tree.html"),
        "space": text("embeddings_assets/embeddings.html"),
    }
    # the Identify About, once its placeholders are filled the way page_identify fills them
    about = re.search(
        r'id="about"><summary>About</summary>(.*?)</details>', page_identify.render(), re.S
    ).group(1)
    assert about.strip() in html and "__" not in about
    for src, pattern in (
        ("confusion", r"</summary>\n(<dl>.*?)<dt>Built</dt>"),
        ("tree", r'<p id="about" hidden>(.*?)</p>'),
        ("space", r'<p class="note" id="honest">(.*?)</p>'),
    ):
        copied = (
            re.search(pattern, sources[src], re.S).group(1).replace('<span id="fid"></span> ', "")
        )
        assert copied.strip() in html, src
    assert "__" not in html.split("</style>")[1]


def test_identify_dates_flow_through(tmp_path):
    (tmp_path / page_identify.DATES_NAME).write_text(
        json.dumps({"photos": "2026-01-02", "scored": "2026-02-03"})
    )
    html = terms_page.build(tmp_path).read_text()
    assert "Photos downloaded on 2 January 2026, scored on 3 February 2026." in html


def test_methods_tab_everywhere():
    assert "terms.html" in [p for p, _ in page_nav.PAGES]
    for page in ("map.html", "identify.html", "terms.html"):
        html = page_nav.nav(page)
        assert 'href="terms.html"' in html and "explain-data" in html


MANIFEST = {
    "dims": 1024,
    "nlist": 4096,
    "m": 64,
    "nbits": 8,
    "refine": {"bits": 3},
    "defaults": {"nprobe": 96, "shortlist": 500},
    "model": {"id": "hf-hub:x/y", "revision": "abc123"},
    "taxa": {"count": 34717, "prompt": "a photo of {}"},
    "layout": {
        "fidelity": {
            "k": 12,
            "n_eval": 100000,
            "mean": 0.1466,
            "median": 0.0833,
            "share_zero": 0.269,
            "affinities": "uniform symmetric exact 12-NN",
            "init": "PCA",
            "gradient": "fft",
            "learning_rate": "auto",
            "early_exaggeration": [12, 250],
            "phases": "250@12, 500@4, 500@1",
        }
    },
}


def test_methods_numbers_come_from_the_code_and_the_manifest():
    from what_to_id import atlas_update, confusion, host_pairs, levels, pool_levels, terms_methods

    html = terms_page.render(manifest=MANIFEST, data_url="https://x.test/atlas")
    methods = html.split('id="methods"')[1]
    assert "__" not in methods and terms_methods.MISSING not in methods
    for text in (
        f"lowest {levels.WEIRD_SHARE:.0%} of",
        f"top {levels.EASY_TOP_SHARE:.0%} of",
        f"not below &minus;{levels.TAXONOMIST_MARGIN:g},",
        f"{levels.MIN_LOOKALIKE_RECORDS} or more verifiable records",
        f"has {confusion.MIN_PER_CLASS} or more scored",
        f"at most {confusion.FIR_PAIRS_PER_SPECIES} pairs with up to "
        f"{confusion.FIR_RECORDS_PER_PAIR} records",
        f"in {pool_levels.STEPS} equal buckets",
        f"the {atlas_update.NEIGHBOR_K} photos with the highest cosine",
        f"approximately ({atlas_update.DEFAULT_NPROBE} lists)",
        f"release {host_pairs.DUMP_RELEASE}, keeping family pairs with\n"
        f"{host_pairs.MIN_ROWS} or more",
        "<code>hf-hub:x/y</code>",
        "<code>abc123</code>",
        "vector of 1024 numbers",
        'prompt "a photo of {}"; the index holds 34,717',
        "sample of 100,000 photos, the 12 nearest",
        "on average 15% of the 12 true closest matches (median\n8%, and 27% of sampled",
        "early exaggeration 12 for 250 iterations; phases 250@12, 500@4, 500@1",
        "4,096 lists with optimised product quantisation to 64 codes of 8 bits",
        "refine stage of 3 bits per code",
        "probes 96 lists and re-scores a shortlist of 500",
    ):
        assert text in methods, text
    for ref in (
        "10.18637/jss.v109.i03",
        "2505.23883",
        "2401.08281",
        "10.1016/j.ecoinf.2014.08.005",
    ):
        assert ref in methods
    assert {"methods-levels", "methods-space", "methods-refs"} <= _ids(methods)


def test_methods_without_an_index_and_without_leaked_list_names():
    from what_to_id import terms_methods

    html = terms_page.render()
    assert terms_methods.MISSING in html and "__" not in html.split("</style>")[1]
    assert not re.search("recency|gap_first|gap first|similarity|novelty|surprise", html, re.I)
    assert "—" not in html  # no em dashes


def test_evaluation_table_comes_from_the_committed_script_output():
    from what_to_id import terms_methods

    ev = json.loads(terms_methods.OUTCOME.read_text())
    assert ev["script"] == "scripts/levels_outcome.py"
    assert {"scores", "pool_before", "pool_after"} == ev["inputs"].keys()
    assert all(len(v["sha256"]) == 64 for v in ev["inputs"].values())
    html = terms_page.render()
    mis = ev["levels"]["mislabel"]
    assert f"<td>Might be mislabelled</td><td>{mis['n']:,}</td>" in html
    assert f"{mis['corrected_rr']:.2f} [{mis['corrected_rr_ci'][0]:.2f}, " in html
    assert f"scored on\n{ev['scored_on']} were looked up again" in html
    assert f"in the pool of {ev['outcome_on']}" in html
    assert "<td>No level</td>" in html and "1 (reference)" in html
    none = ev["levels"]["none"]
    assert f"Might be mislabelled, {mis['to_suggested_share']:.0%}\nmoved to the species" in html
    assert f"the shares are {none['to_suggested_share']:.0%} and " in html
    assert f"(rate ratios {mis['to_suggested_rr']:.2f} [" in html


def test_figures_baselines_replication_and_cohort_link_come_from_the_outputs():
    from what_to_id import terms_methods

    ev = json.loads(terms_methods.OUTCOME.read_text())
    ev_b = json.loads(terms_methods.OUTCOME_B.read_text())
    assert ev["inputs"]["scores"] == ev_b["inputs"]["scores"]
    assert ev["inputs"]["pool_before"] == ev_b["inputs"]["pool_before"]
    assert ev["outcome_on"] < ev_b["outcome_on"]
    html = terms_page.render()
    methods = html.split('id="methods"')[1]
    assert methods.count("<figure ") == 2 and methods.count("<svg") == 2
    page = ev["baselines"]["page"]
    assert (
        f"<td>The page's order (level, then score within the level)</td><td>{page['auc']:.3f} ["
        in methods
    )
    assert f"{ev['baselines']['margin_lowest_first_shown']['auc']:.3f} [" in methods
    assert (
        f"gives an AUC of {ev['baselines']['close_calls_lowest_margin_first']['auc']:.3f} ["
        in methods
    )
    assert f"the pool of {ev_b['outcome_on']}:</p>" in methods
    mis, n = ev_b["levels"]["mislabel"], ev_b["levels"]["mislabel"]["n"]
    assert (
        f"<td>Might be mislabelled</td><td>{n:,}</td><td>{mis['corrected_per_1000']:.2f}</td>"
        in methods
    )
    assert terms_methods.MISSING + " on the index" in methods
    linked = terms_page.render(data_url="https://x.test/atlas/")
    assert f'<a href="https://x.test/atlas/{ev["cohort_file"]}">{ev["cohort_file"]}</a>' in linked


def test_identify_about_links_to_methods():
    assert 'href="terms.html#methods"' in page_identify.render()


def test_the_study_section_and_its_fold_come_with_the_study_only():
    from collections import Counter

    from what_to_id.page_rotation import read_study

    plain = terms_page.render()
    assert '<h2 id="study">' in plain and 'id="study-methods"' not in plain
    for words in ("only thing randomized", "public on iNaturalist", "nothing to sign up for"):
        assert words in plain
    study = read_study(SRC.parents[1] / "site" / "study.json")
    html = terms_page.render(study=study)
    assert 'id="study-methods"' in html and 'href="#study-methods-refs"' in html
    ids = Counter(re.findall(r'\bid="([^"]+)"', html))
    assert [i for i, n in ids.items() if n > 1] == []
    assert html.index('id="study"') < html.index('id="study-methods"') < html.index('id="methods"')
    assert not re.search("recency|gap_first|gap first|similarity|novelty|surprise", html, re.I)
