import re

import pytest

from tests.test_page_methods import ALL_ARMS, _manifest
from what_to_id.page_doc import Doc
from what_to_id.page_method import method_section
from what_to_id.page_methods_size import served_top, size_section


@pytest.fixture(scope="module")
def size():
    html = method_section(_manifest(ALL_ARMS), len(ALL_ARMS))
    return re.search(r'<section id="methods-size">(.*?)</section>', html, re.S).group(1)


def _visible(html):
    return re.sub(r'<details class="more".*?</details>', "", html, flags=re.S)


def test_size_section_shows_both_power_panels_and_the_break_even(size):
    assert "Simulated power against participants, weighted count" in size
    assert "Simulated power against participants, plain count" in size
    assert "more than 0.44 times their rate" in size
    assert "average map score of 0.361, against 0.158" in size
    assert "in 7 of the 10 taxon groups" in size
    assert "Planning values, with no source." in size
    assert "power is 0.80 to 0.81 with 10 participants" in size
    for old in ("Every list", "One list each", "every-2", "every-4", "one-4"):
        assert old not in size
    assert "draft protocol's 4 lists. This build has 5." in size
    f = {"k": 4, "batch_size": 2, "max_batches": None, "cap_reached": False}
    assert "draft protocol's 4 lists" not in size_section(_manifest(ALL_ARMS[:4]), f, Doc())


def test_served_share_is_the_top_of_the_preview_and_not_called_measured(size):
    assert served_top(4, 2400) == [("Plantae", 16), ("Insecta", 33), ("Fungi", 44)]
    assert "top 16 of the 1,000 preview records in Plantae, the top 33 in Insecta and the " in size
    assert "In the model the records met on" in size
    assert "The real pool's top 2,400 per list is not measured" in size
    assert "These scores are measured" not in size and "The lead comes from" not in size


def test_simulated_comparisons_direction_and_no_cap_run_are_stated(size):
    visible = _visible(size)
    assert "runs two comparisons: data-poor places first against newest first" in visible
    assert "lists set only how each participant's effort is split and the level" in visible
    assert (
        "a finding only when data-poor places first comes out ahead, a plain-count run in "
        in visible
    )
    assert "came out behind in at most 0.001 of these runs" in visible
    assert "a mechanism of the model" in visible
    assert (
        "gave 0.159 on newest first and 0.158 on data-poor places first, with none ahead" in visible
    )
    assert "--max-batches 0" in size
    assert "counts from the iNaturalist API on 2026-09-12, recorded in power.py" in size


def test_false_finding_rate_is_stated_once_in_the_main_text_and_linked(size):
    full = method_section(_manifest(ALL_ARMS), len(ALL_ARMS))
    para = re.search(r'<p id="methods-null-rate">.*?</p>', size, re.S).group(0)
    assert para in _visible(size)
    assert "14,000 runs over both seeds and all participant counts" in para
    assert "found one in 0.025 of runs against its level of 0.017, about 1.5 times" in para
    assert "the split is drawn by record" in para
    assert "a little above nominal" not in full
    assert full.count('href="#methods-null-rate"') == 1


def test_power_gloss_uses_the_builds_batch_cap_and_the_exact_p():
    m = _manifest()
    m.max_batches = 1
    html = method_section(m, 2)
    exact = (
        "exact with 12 or fewer non-zero differences, as in the analysis, and otherwise "
        "draws 1,000 random sign patterns, where the analysis draws 10,000"
    )
    assert exact in html
    assert "In this build a cap binds." in html
    free = method_section(_manifest(), 2)
    assert "no cap binds, so its lists serve records with the same scores on average" in free
    assert "the daily job builds only two lists" in _visible(free.split('id="methods-size"')[1])
    assert "docs/protocol.md#open-before-the-blitz" in free
