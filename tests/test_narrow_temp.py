"""The maximum-likelihood temperature of scripts/narrow_temp.py and its Methods clause."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from what_to_id import terms_methods, terms_page

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("nt", ROOT / "scripts" / "narrow_temp.py")
nt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nt)


def _draw(temp: float, n: int = 20000):
    rng = np.random.default_rng(1)
    margin = rng.uniform(0, 0.06, n)
    y = (rng.random(n) < 1 / (1 + np.exp(margin / temp))).astype(float)
    return margin, y


def test_the_fit_recovers_the_temperature_that_made_the_data():
    margin, y = _draw(0.02)
    assert nt.fit_temp(margin, y) == pytest.approx(0.02, rel=0.15)


def test_a_margin_that_says_nothing_runs_to_the_upper_bound():
    rng = np.random.default_rng(2)
    margin = rng.uniform(0, 0.06, 5000)
    y = (rng.random(5000) < 0.5).astype(float)
    assert nt.fit_temp(margin, y) > 0.5


def test_bootstrap_is_seeded_and_needs_1000_reps():
    margin, y = _draw(0.02, 600)
    obs = np.arange(600) % 100
    a = nt.bootstrap(margin, y, obs, 1000, seed=3)
    assert a == nt.bootstrap(margin, y, obs, 1000, seed=3) and a[0] < 0.02 < a[1]
    with pytest.raises(ValueError):
        nt.bootstrap(margin, y, obs, 999, seed=3)


def test_methods_state_the_committed_fit():
    fit = json.loads(terms_methods.TEMP_FIT.read_text())
    assert fit["script"] == "scripts/narrow_temp.py" and fit["bootstrap_reps"] >= 1000
    html = terms_page.render()
    assert f"{fit['resolved']:,}" in html
    assert (fit["temp"] >= 1) == ("is not fitted" in html)
