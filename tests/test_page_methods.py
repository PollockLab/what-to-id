import re

import pytest

from what_to_id import assign as assign_mod
from what_to_id import page_methods_analysis
from what_to_id.analysis import sign_flip_p
from what_to_id.manifest import Manifest
from what_to_id.page_doc import Doc
from what_to_id.page_figures import (
    SIGNFLIP_DIFFS,
    deal_example,
    deal_figure,
    power_figure,
    signflip_example,
)
from what_to_id.page_method import method_section
from what_to_id.page_methods_setup import build_facts, records_section
from what_to_id.page_svg import text

ALL_ARMS = ["recency", "gap_first", "similarity", "novelty", "surprise"]
LEAK = re.compile(r"recency|gap_first|gap first|similarity|novelty|surprise", re.I)


def _manifest(arms=("recency", "gap_first"), assignment="stratified"):
    batches = {}
    for arm in arms:
        for g, ids in (("Aves", [[1, 2], [3]]), ("Insecta", [[4, 5]])):
            for j, chunk in enumerate(ids):
                batches[f"{arm}-{g}-{j:03d}"] = {
                    "arm": arm,
                    "group": g,
                    "url": f"https://x?id={chunk[0]}",
                    "ids": chunk,
                }
    return Manifest(
        freeze="2026-09-01",
        d1="2026-11-01",
        seed=0,
        batch_size=2,
        arms=list(arms),
        arm_labels={a: chr(65 + i) for i, a in enumerate(arms)},
        pool_sha256="0" * 64,
        pool_rows=5 * len(arms),
        design="rotation",
        assignment=assignment,
        batches=batches,
    )


@pytest.fixture(scope="module")
def full():
    return method_section(_manifest(ALL_ARMS), len(ALL_ARMS))


def test_no_order_word_or_em_dash_with_all_five_orders(full):
    assert not LEAK.findall(full)
    assert "—" not in full
    for secret in ("0" * 64, "arm_labels", "pool_sha256", "key_fingerprint"):
        assert secret not in full


def test_every_figure_has_a_caption_and_an_accessible_svg(full):
    figures = re.findall(r'<figure class="fig" id="fig-\d+">(.*?)</figure>', full, re.S)
    assert len(figures) >= 9
    for fig in figures:
        assert fig.count("<figcaption>") == 1
        assert re.search(r'<svg[^>]*role="img"[^>]*aria-label="[^"]+"', fig)
        assert re.search(r'<svg[^>]*viewBox="[^"]+"', fig)


def test_figures_and_tables_are_numbered_in_order(full):
    figs = [int(n) for n in re.findall(r"<b>Figure (\d+)\.</b>", full)]
    tabs = [int(n) for n in re.findall(r"<b>Table (\d+)\.</b>", full)]
    assert figs == list(range(1, len(figs) + 1))
    assert tabs == list(range(1, len(tabs) + 1))
    refs = [int(n) for n in re.findall(r'<li id="ref-(\d+)">', full)]
    assert refs == list(range(1, len(refs) + 1))


def test_every_in_page_link_resolves(full):
    ids = set(re.findall(r'\bid="([^"]+)"', full))
    targets = re.findall(r'href="#([^"]+)"', full)
    assert {f"methods-{s}" for s in ("design", "refs", "size")} <= set(targets)
    for t in targets:
        assert t in ids, t


def test_section_is_deterministic():
    m = _manifest(ALL_ARMS)
    assert method_section(m, 5) == method_section(m, 5)


def test_deal_figure_colours_match_the_assignment_code():
    for k in (2, 4, 5):
        pool, arms, seed = deal_example(k)
        want = assign_mod.assign(pool, arms, seed=seed).set_index("id")["arm"]
        got = re.findall(r'data-rec="(\d+)" data-list="(\d+)"', deal_figure(k))
        assert len(got) == len(pool)
        for rid, n in got:
            assert arms[int(n) - 1] == want[int(rid)]


def test_worked_sign_flip_p_is_the_analysis_codes(full):
    ex = signflip_example()
    assert ex["p"] == sign_flip_p(list(SIGNFLIP_DIFFS))
    assert ex["p"] == ex["extreme"] / len(ex["sums"])
    assert f"= {ex['p']:.4f}" in full


def test_power_figure_needs_rows_and_the_page_skips_it_without_them(monkeypatch, full):
    with pytest.raises(ValueError):
        power_figure([])
    assert "Simulated power" in full
    monkeypatch.setattr(page_methods_analysis, "POWER", [])
    bare = method_section(_manifest(ALL_ARMS), 5)
    assert "Simulated power" not in bare
    assert bare.count('<figure class="fig"') == full.count('<figure class="fig"') - 1


def test_keyed_build_has_no_deal_figure_and_no_seed_words():
    seeded = method_section(_manifest(), 2)
    keyed = method_section(_manifest(assignment="keyed"), 2)
    assert "observer bucket" in seeded and "observer bucket" not in keyed
    assert "HMAC-SHA256" in keyed and "HMAC" not in seeded
    assert "a seed shuffles" in seeded and "seed shuffles" not in keyed
    assert "seed is in the build record" in seeded and "private key picks" in keyed
    assert "seed is in the build record" not in keyed


def test_svg_text_is_legible_on_a_phone(full):
    sizes = [float(s) for s in re.findall(r'<text[^>]*font-size="([\d.]+)"', full)]
    assert sizes and min(sizes) >= 11
    with pytest.raises(ValueError):
        text(0, 0, "x", size=10.5)


def test_no_panel_title_or_figure_label_uses_a_list_letter(full):
    svg_text = re.findall(r"<text[^>]*>([^<]*)</text>", full)
    labels = re.findall(r'aria-label="([^"]*)"', full)
    for s in svg_text + labels:
        assert not re.search(r"(?<![\w-])[ABCD](?![\w-])", s), s
    assert not re.search(
        r"\b(?:Panel )?[ABCD][.:] ",
        " ".join(re.findall(r"<figcaption>(.*?)</figcaption>", full, re.S)),
    )


@pytest.mark.parametrize(
    "max_batches, want",
    [
        (None, "no cap on batches, so every record is served"),
        (5, "No list reaches it, so every record is served"),
        (1, "serves only the first 1 batches"),
    ],
)
def test_cap_sentence_follows_the_data(max_batches, want):
    m = _manifest()
    m.max_batches = max_batches
    assert want in method_section(m, 2)


@pytest.mark.parametrize(
    "records, want",
    [((1000, 1000), "preview sample"), ((1000, 998), "cannot tell"), ((300, 300), "cannot tell")],
)
def test_frame_sentence_follows_the_group_counts(records, want):
    m = _manifest()
    f = build_facts(m)
    f["groups"] = [dict(g, records=r) for g, r in zip(f["groups"], records, strict=True)]
    html = records_section(m, f, Doc())
    assert want in html
    assert ("preview sample" in html) != ("cannot tell" in html)


@pytest.mark.parametrize("arms", [("recency", "gap_first"), tuple(ALL_ARMS)])
@pytest.mark.parametrize(
    "key, author, doi",
    [
        ("hebert2026", "Hébert K", "https://doi.org/10.32942/X2T09G"),
        ("mesaglio2025", "Mesaglio T", "https://doi.org/10.1002/ppp3.70005"),
    ],
)
def test_preprint_and_prior_art_references_render_and_are_cited(arms, key, author, doi):
    html = method_section(_manifest(arms), len(arms))
    item = re.search(rf'<li id="ref-(\d+)">{author}[^<]*<a href="{re.escape(doi)}"', html)
    assert item, key
    assert f'<a href="#ref-{item.group(1)}">' in html


def test_sum_and_sign_test_sentence_and_change_over_time_row(full):
    assert "gives each person one vote" in full
    assert '<th scope="row">Change over time</th>' in full
    assert "observations per active day" in full and "1.15 times" in full


def test_only_this_builds_orders_get_a_subsection():
    two = method_section(_manifest(), 2)
    assert two.count('<h4 id="order-') == 2
    assert "Look-alike" not in two and "Unfamiliar" not in two


def test_chance_sentence_and_band_only_in_keyed_builds():
    keyed = method_section(_manifest(assignment="keyed"), 2)
    seeded = method_section(_manifest(), 2)
    assert "The keyed split draws each record's list on its own" in keyed
    assert "standard deviation of about" in keyed
    assert "keyed split draws" not in seeded
    assert 'class="band"' in keyed and 'class="band"' not in seeded


def test_list_share_figure_is_rendered_for_both_assignments(full):
    assert "as a share of each taxon group" in full
    assert 'class="rng"' in full


def test_threats_row_links_to_the_size_table_and_the_share_figure(full):
    assert '<th scope="row">Chance differences between lists</th>' in full
    assert '<a href="#tab-2">Table 2</a>' in full
    share = re.search(r'<figure class="fig" id="fig-(\d+)">[^<]*<svg[^>]*as a share', full)
    assert share
    assert f'<a href="#fig-{share.group(1)}">Figure {share.group(1)}</a>' in full
    assert '<th scope="row">Who takes part</th>' in full
    assert "for records in British Columbia, for the dates of this build" in full


def test_doc_ref_raises_before_the_figure_is_rendered():
    with pytest.raises(KeyError):
        Doc().ref("sizes")


def test_reproducibility_rows_for_the_commit_and_the_key():
    m = _manifest(assignment="keyed")
    m.key_fingerprint = "abc123def456"
    keyed = method_section(m, 2)
    assert '<th scope="row">Code commit</th>' in keyed
    assert "not in this build's manifest" in keyed
    assert '<th scope="row">Key fingerprint</th>' in keyed
    assert "abc123def456" in keyed
    assert "first 12 hex characters" in keyed
    assert '<th scope="row">Key fingerprint</th>' not in method_section(_manifest(), 2)


def test_code_commit_row_shows_the_manifest_value_when_present():
    m = _manifest()
    m.code_commit = "f" * 40
    html = method_section(m, 2)
    assert "f" * 40 in html
    assert "not in this build's manifest" not in html


def test_placebo_caution_and_not_stated_timing(full):
    assert full.count("does not prove") >= 2
    assert "Not stated" in full
    assert "With the count" not in full


def test_per_list_outcome_table_and_holm_comparisons(full):
    assert "What the analysis code computes for each list" in full
    assert "It is the control that every other list is compared with" in full
    assert "The code computes the same outcomes for every list" in full
    assert "so this build gives 4 comparisons" in full
    assert "the code does not adjust across runs" in full


def test_batches_are_cut_up_to_the_batch_size(full):
    assert "batches of up to" in full
    assert not re.search(r"batches of \d", full)
    assert "the last group takes the photos left" in full


def test_the_number_of_lists_is_settled_not_a_preview(full):
    assert "This design uses 5 lists. An earlier draft of the protocol proposed 2" in full
    assert "The BC team fixes these values before the blitz" in full
    assert "This preview has" not in full
    assert "The draft protocol plans 2" not in full


def test_record_level_rerandomisation_is_a_secondary_test(full):
    assert "A second test, on the records" in full
    assert "redraws which list each record would have gone to" in full
    assert "This is the check the sign-flip test cannot give" in full
    assert "does not replace the primary test" in full
    assert "Over 2,000 redrawn splits the code returns p = 0.2629" in full


def test_table_six_pins_an_outcome_for_every_list(full):
    assert "Open." not in full
    assert (
        "The outcome is the same species-level ID count as every list, plain and weighted" in full
    )
    assert "fewer switches between kinds of photo make identifying faster" in full
    assert "predicts more IDs" not in full
    assert "predicted direction on the count is not stated in the draft protocol" in full
    assert "It states none for the other lists, and this page does not supply one" in full


def test_inaturalist_source_reference_renders_and_is_cited(full):
    item = re.search(r'<li id="ref-(\d+)">iNaturalist source code[^<]*<a href="([^"]+)"', full)
    assert item
    assert "search_params_reducer.js#L10-L21" in item.group(2)
    assert full.count(f'<a href="#ref-{item.group(1)}">') >= 5


def test_gbif_and_participants_and_window_wording(full):
    assert "Records that reach Research Grade, with an open licence, go to GBIF." in full
    assert "reads one of the two, the project or the sign-up list" in full
    assert "A withdrawn ID still counts." in full
    assert "meets all its records that still need an ID" in full


def test_power_gloss_uses_the_builds_batch_cap():
    m = _manifest()
    m.max_batches = 3
    html = method_section(m, 2)
    assert "draws 1,000 random sign patterns per test, where the analysis draws 10,000" in html
    assert "serves at most 6 records per list and taxon group" in html
    assert "no cap on batches, so it serves every record" in method_section(_manifest(), 2)
