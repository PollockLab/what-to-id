import re

import pytest

from what_to_id.page_power import IDS, PLAIN, WEIGHTED, p2, power_at, power_panel


def test_p2_rounds_exact_thousandths_half_up():
    assert p2(0.305) == "0.31"
    assert p2(0.985) == "0.99"
    assert p2(0.304) == "0.30"
    assert p2(1.0) == "1.00"


def test_power_at_gives_one_value_or_a_range_when_the_seeds_round_apart():
    assert power_at(WEIGHTED, 1.0, 10) == "0.80 to 0.81"
    assert power_at(WEIGHTED, 0.6, 20) == "0.31 to 0.38"
    assert power_at(PLAIN, 0.2, 40) == "0.99"
    with pytest.raises(ValueError):
        power_at(PLAIN, 0.2, 11)


def test_power_panel_draws_one_line_per_series_and_checks_its_input():
    out = power_panel({"a": (0.1,) * len(IDS), "b": (0.5,) * len(IDS)}, "test")
    assert out.count("<polyline") == 2
    assert 'class="pw1"' in out and 'class="pw2"' in out and "pw3" not in out
    assert re.search(r'aria-label="Simulated power against participants, test: a, 10', out)
    with pytest.raises(ValueError, match="at least one"):
        power_panel({}, "test")
    with pytest.raises(ValueError, match="has 1 values"):
        power_panel({"a": (0.1,)}, "test")
