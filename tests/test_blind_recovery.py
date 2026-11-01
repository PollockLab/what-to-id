"""Simulation-based check: the chain fit -> cv_error -> detection_rate recovers known e and d.

Truth, first IDs, public overturns and student answers are drawn from the model the estimators
assume, so a miss here is an estimator bug, not a study result.
"""

import numpy as np
import pandas as pd

from what_to_id import blind_report
from what_to_id.blind_skill import fit

E = {"cv": 0.06, "typed": 0.09}
D = {"cv": 0.6, "typed": 0.8}


def simulate(n=3000, taxa=200, students=60, per_record=5, planted=150, seed=0):
    rng = np.random.default_rng(seed)
    truth = rng.integers(0, taxa, n)
    vision = rng.random(n) < 0.75
    src = np.where(vision, "cv", "typed")
    e = np.where(vision, E["cv"], E["typed"])
    d = np.where(vision, D["cv"], D["typed"])
    wrong = rng.random(n) < e
    first = np.where(wrong, (truth + rng.integers(1, 4, n)) % taxa, truth)
    caught = wrong & (rng.random(n) < d)
    public = np.where(caught, truth, first)
    acc = rng.uniform(0.65, 0.9, students)
    rec = np.repeat(np.arange(n), per_record)
    who = np.concatenate([rng.choice(students, per_record, replace=False) for _ in range(n)])
    right = rng.random(len(rec)) < acc[who]
    said = np.where(right, truth[rec], (truth[rec] + rng.integers(1, 4, len(rec))) % taxa)
    answers = pd.DataFrame(
        {"login": [f"s{w}" for w in who], "group": "Insecta", "record_id": rec, "taxon_id": said}
    )
    firsts = pd.DataFrame(
        {"record_id": np.arange(n), "group": "Insecta", "taxon_id": first, "vision": vision}
    )
    pub = pd.DataFrame({"record_id": np.arange(n), "taxon_id": public})
    plant = pd.DataFrame({"record_id": np.arange(planted), "taxon_id": truth[:planted]})
    return answers, firsts, pub, plant, pd.Series(src)


def _recover(answers, firsts, public, planted, c):
    _, consensus = fit(answers, planted)
    err = blind_report.cv_error(consensus, firsts, consensus_error=c)
    det = blind_report.detection_rate(consensus, firsts, public, boot=400, consensus_error=c)
    err = err[err["group"] == "all"].set_index("source")
    det = det[det["group"] == "all"].set_index("source")
    return consensus, err, det


def test_chain_recovers_e_and_d_after_consensus_error_correction():
    # 600 planted: c is about 0.5% under these assumptions and 150 planted cannot resolve it
    answers, firsts, public, planted, _ = simulate(planted=600)
    c, n = blind_report.consensus_error(answers, planted)
    assert n > 400 and 0 < c < 0.02, (c, n)
    consensus, err, det = _recover(answers, firsts, public, planted, c)
    assert (consensus["posterior"] >= 0.9).mean() > 0.8
    for s in ("cv", "typed"):
        assert err.loc[s, "lo"] <= E[s] <= err.loc[s, "hi"], (s, err.loc[s].to_dict())
        assert det.loc[s, "lo"] <= D[s] <= det.loc[s, "hi"], (s, det.loc[s].to_dict())
    assert det.loc["cv", "detection"] < det.loc["typed", "detection"]


def test_uncorrected_d_is_biased_down():
    answers, firsts, public, planted, _ = simulate()
    _, _, raw = _recover(answers, firsts, public, planted, 0.0)
    _, _, fixed = _recover(answers, firsts, public, planted, 0.02)
    assert raw.loc["cv", "detection"] < fixed.loc["cv", "detection"] <= 1
