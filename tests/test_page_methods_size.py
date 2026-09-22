import re

import pytest

from tests.test_page_methods import ALL_ARMS, _manifest
from what_to_id.page_doc import Doc
from what_to_id.page_method import method_section
from what_to_id.page_methods_size import size_section


@pytest.fixture(scope="module")
def size():
    html = method_section(_manifest(ALL_ARMS), len(ALL_ARMS))
    return re.search(r'<section id="methods-size">(.*?)</section>', html, re.S).group(1)


def _visible(html):
    return re.sub(r'<details class="more".*?</details>', "", html, flags=re.S)


def test_size_section_shows_both_power_panels_and_the_break_even(size):
    assert "Simulated power against participants, weighted count" in size
    assert "Simulated power against participants, plain count" in size
    assert "Planning values, with no source." in size
    for old in ("Every list", "One list each", "every-2", "every-4", "one-4"):
        assert old not in size
    assert "draft protocol's 4 lists. This build has 5." in size
    f = {"k": 4, "batch_size": 2, "max_batches": None, "cap_reached": False}
    assert "draft protocol's 4 lists" not in size_section(_manifest(ALL_ARMS[:4]), f, Doc())


def test_served_share_is_the_top_of_the_preview_and_not_called_measured(size):
    assert "newest preview records, not a random sample" in size
    assert "are assumed" in size
    assert "A binding batch cap concentrates high map scores" in size


def test_simulated_comparisons_direction_and_no_cap_run_are_stated(size):
    visible = _visible(size)
    assert "runs two comparisons: data-poor places first against newest first" in visible
    assert "lists set only how each participant's effort is split and the level" in visible
    assert (
        "a finding only when data-poor places first comes out ahead, a plain-count run in "
        in visible
    )
    assert "without that cap, the lists serve the same scores on average" in visible
    assert "Simulation code and settings" in size


def test_false_finding_rate_is_stated_once_in_the_main_text_and_linked(size):
    full = method_section(_manifest(ALL_ARMS), len(ALL_ARMS))
    para = re.search(r'<p id="methods-null-rate">.*?</p>', size, re.S).group(0)
    assert para in _visible(size)
    assert "14,000 runs over both seeds and all participant counts" in para
    assert "found one in 0.025 of runs against its level of 0.017, about 1.5 times" in para
    assert "the split is drawn by record" in para
    assert "a little above nominal" not in full
    assert full.count('href="#methods-null-rate"') == 1


def test_power_details_link_to_code_instead_of_repeating_the_plots(size):
    assert "src/what_to_id/power_weighted.py" in size
    assert "Simulated power by number of participants" not in size
    assert "<b>Rerun.</b>" not in size
