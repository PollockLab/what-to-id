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
    # the level terms carry the names Identify shows, not their keys
    assert "Easy confirms</dt>" in html
    assert ">Level " not in html.replace(">Level order</dt>", "")  # the prioritizer, not a level


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
        if key in page_nav.MORE_LINKS:  # another site's page explains it
            assert href == page_nav.MORE_LINKS[key], key
            continue
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
    (tmp_path / page_identify.DATES_NAME).write_text(
        json.dumps({"photos": "2026-01-02", "scored": "2026-02-03", "updated": "2026-02-09"})
    )
    html = terms_page.build(tmp_path).read_text()
    assert "3 February 2026. Updated daily with new records, last on 9 February 2026." in html


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

    dates = {"photos": "2026-10-01", "scored": "2026-10-15", "updated": None}
    html = terms_page.render(dates, manifest=MANIFEST, data_url="https://x.test/atlas")
    methods = html.split('id="methods"')[1]
    assert "__" not in methods and terms_methods.MISSING not in methods
    for text in (
        f"lowest {levels.WEIRD_SHARE:.0%} of",
        f"top {levels.EASY_TOP_SHARE:.0%} of",
        f"{levels.TAXONOMIST_QUANTILE * 100:g}th percentile of the\nnegative margins",
        f"{levels.MIN_LOOKALIKE_RECORDS} or more records needing ID in BC",
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
        'prompt "a photo of {}": 34,717 names, one text vector each',
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
    # the left rate sits beside the corrected one, and the count is n x rate to the rate's rounding
    events = round(mis["n"] * mis["corrected_per_1000"] / 1000)
    c = mis["cluster"]
    lo, hi = c["corrected_per_1000_ci"]
    cell = f"<td>{mis['corrected_per_1000']:.2f} [{lo:.2f}, {hi:.2f}]</td>"
    assert cell + f"<td>{mis['left_per_1000']:.2f} [" in html
    # the observer-clustered ratio and difference sit beside the record-level ratio
    lo, hi = c["corrected_rr_ci"]
    assert f"<td>{mis['corrected_rr']:.2f} [{lo:.2f}, {hi:.2f}]</td>" in html
    lo, hi = c["corrected_diff_per_1000_ci"]
    assert f"<td>{c['corrected_diff_per_1000']:.2f} [{lo:.2f}, {hi:.2f}]</td></tr>" in html
    assert ev["cluster"]["unit"] == "observer (user_id)" and ev["bootstrap_reps"] >= 1000
    assert f"takes the cohort's\n{ev['cluster']['observers']:,} observers with replacement" in html
    assert f"<td>{events:,}</td>" in html
    assert "meaning relabelled while still Needs ID" in html
    assert "reached Research Grade after a re-ID" in html and "rollback to a genus" in html
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
    assert f"the pool of {ev_b['outcome_on']}, 3 days after the first reading:</p>" in methods
    assert "the same cohort, not an independent sample" in " ".join(methods.split()).lower()
    mis, n = ev_b["levels"]["mislabel"], ev_b["levels"]["mislabel"]["n"]
    assert (
        f"<td>Might be mislabelled</td><td>{n:,}</td><td>{mis['corrected_per_1000']:.2f} ["
        in methods
    )
    assert terms_methods.MISSING + " on the index" in methods
    linked = terms_page.render(data_url="https://x.test/atlas/")
    assert f'<a href="https://x.test/atlas/{ev["cohort_file"]}">{ev["cohort_file"]}</a>' in linked


def test_identify_about_links_to_methods():
    assert 'href="terms.html#methods"' in page_identify.render()


def test_the_study_section_and_its_fold_come_with_the_study_only(monkeypatch):
    from collections import Counter

    from what_to_id.page_rotation import read_study

    plain = terms_page.render()
    assert '<h2 id="study">' in plain and 'id="study-methods"' not in plain
    for words in ("starts at a random batch", "GoatCounter", "nothing to sign up for"):
        assert words in plain
    assert ("sign in lasts" in plain) == bool(page_identify.INAT_CLIENT_ID)
    study = read_study(SRC.parents[1] / "site" / "study.json")
    assert 'id="study-methods"' not in terms_page.render(study=study)  # held with the prereg
    monkeypatch.setattr(terms_page, "SHOW_TEST_FOLD", True)
    html = terms_page.render(study=study)
    assert 'id="study-methods"' in html and 'href="#study-methods-refs"' in html
    ids = Counter(re.findall(r'\bid="([^"]+)"', html))
    assert [i for i, n in ids.items() if n > 1] == []
    assert html.index('id="study"') < html.index('id="study-methods"') < html.index('id="methods"')
    assert not re.search("recency|gap_first|gap first|similarity|novelty|surprise", html, re.I)


def test_about_says_odd_shots_are_checked_first_at_any_rank():
    # identify_levels np.select([weird, easy, tax, narrow, mislabel]): a weird genus goes to level 4
    # (tests/test_levels.py::test_weird_wins_at_any_rank)
    text = " ".join(page_identify.render().split())
    assert "Odd shots are checked first, at any rank; then Easy confirms, close calls," in text
    assert "goes here, unless it is an odd shot." in text and "whatever its match" not in text
    assert "unless it is an odd shot" in GLOSSARY["level-narrow-it-down"][0]


def test_no_claim_the_code_does_not_back_remains_in_the_built_pages():
    for page in (terms_page.render(), page_identify.render()):
        flat = " ".join(page.split())
        for gone in ("Probably ", "Likely mislabel", "written down before", "set in advance"):
            assert gone not in flat, gone
    methods = " ".join(terms_page.render().split())
    assert "were chosen using this cohort, so these figures are in-sample." in methods


def test_methods_state_ranges_status_lists_and_limits_from_their_sources():
    from what_to_id import identify

    dates = {"photos": "2026-10-01", "scored": "2026-10-15", "updated": "2026-11-10"}
    methods = " ".join(terms_page.render(dates).split())
    assert {"methods-ranges", "methods-status"} <= _ids(terms_page.render())
    ranges_js = (page_identify.ASSETS / "identify_ranges.js").read_text()
    assert "var OUT_KM=50," in ranges_js
    assert "is 50 km or more from the nearest centre" in methods
    assert "have not yet been validated" in methods and "may lag its spread" in methods
    assert "97.7% level agreement" in identify.__doc__ and "for 97.7% of such records" in methods
    assert "The last full run was on 2026-10-15." in methods
    for name in ("at_risk_bc_taxa", "invasive_bc_taxa"):
        doc = json.loads((SRC / f"{name}.json").read_text())
        assert f"{len(doc['taxa']):,} taxa, fetched {doc['fetched']}" in methods
    assert "weights set by hand. They were not fitted" in methods
    for words in ("fungi and fish", "43% and 53%", "84% for amphibians", "BC only", "19-day"):
        assert words in methods
    assert "a rank, not a measured accuracy" in GLOSSARY["best-match"][0]
    assert "Narrow it down is not yet evaluated" in GLOSSARY["best-match"][0]
    assert GLOSSARY["level-odd-shots"][0].startswith("Photos that match no species well (often")
    assert "These match their label best among their species." in page_identify.render()


def test_methods_open_with_the_intended_use_box():
    methods = " ".join(terms_page.render().split('id="methods"')[1].split())
    box = methods.index('class="use"')
    assert box < methods.index('id="methods-data"')
    assert "for prioritising which records to look at" in methods
    assert "not an ID tool" in methods and "never agree to an ID because of a level" in methods
