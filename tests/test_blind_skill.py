import numpy as np
import pandas as pd
import pytest

from what_to_id.blind_skill import (
    CONSENSUS_COLUMNS,
    SKILL_COLUMNS,
    _roll_up,
    ancestry_from_taxa,
    consensus_at,
    fit,
)


def simulate(seed=0, n_logins=40, n_records=400, n_planted=60, per_record=4):
    rng = np.random.default_rng(seed)
    acc = rng.uniform(0.5, 0.95, n_logins)
    truth = rng.integers(0, 4, n_records)  # index into each record's 4 candidates
    rows = []
    for r in range(n_records):
        for u in rng.choice(n_logins, per_record, replace=False):
            if rng.random() < acc[u]:
                pick = truth[r]
            else:
                pick = rng.choice([c for c in range(4) if c != truth[r]])
            rows.append((r, f"u{u}", r * 4 + int(pick), "g"))
    answers = pd.DataFrame(rows, columns=["record_id", "login", "taxon_id", "group"])
    expert = pd.DataFrame(
        {"record_id": np.arange(n_records), "taxon_id": np.arange(n_records) * 4 + truth}
    )
    return answers, expert, expert.iloc[:n_planted], acc


def test_recovers_skill_and_consensus(capsys):
    answers, expert, planted, acc = simulate()
    skill, cons = fit(answers, planted)
    est = skill.set_index("login")["accuracy"]
    true = pd.Series(acc, index=[f"u{i}" for i in range(len(acc))]).loc[est.index]
    corr, mae = np.corrcoef(est, true)[0, 1], (est - true).abs().mean()
    with capsys.disabled():
        print(f"\ncorr={corr:.3f} mae={mae:.3f}")
    assert corr > 0.8
    assert mae < 0.08
    assert list(skill.columns) == SKILL_COLUMNS
    assert list(cons.columns) == CONSENSUS_COLUMNS

    # planted records keep their truth
    pc = cons[cons["planted"]].merge(planted, on="record_id", suffixes=("", "_true"))
    assert len(pc) == len(planted)
    assert (pc["taxon_id"] == pc["taxon_id_true"]).all()
    assert (pc["posterior"] == 1.0).all()

    # consensus vs plurality vote on unplanted records
    un = cons[~cons["planted"]].merge(expert, on="record_id", suffixes=("", "_true"))
    em = (un["taxon_id"] == un["taxon_id_true"]).mean()
    counts = answers.groupby(["record_id", "taxon_id"]).size().reset_index(name="n")
    mv = counts.sort_values("n", ascending=False, kind="stable").drop_duplicates("record_id")
    mv = mv[mv["record_id"].isin(un["record_id"])].merge(
        expert, on="record_id", suffixes=("", "_true")
    )
    mvm = (mv["taxon_id"] == mv["taxon_id_true"]).mean()
    assert em > mvm or abs(em - mvm) <= 0.01

    hi = consensus_at(cons, 0.9)
    assert (hi["posterior"] >= 0.9).all() and len(hi) <= len(cons)


def test_empty_answers():
    skill, cons = fit(pd.DataFrame(columns=["record_id", "login", "taxon_id", "group"]))
    assert skill.empty and cons.empty
    assert list(skill.columns) == SKILL_COLUMNS
    assert list(cons.columns) == CONSENSUS_COLUMNS


def test_all_abstain_record():
    answers = pd.DataFrame(
        {
            "record_id": [1, 1, 2, 2],
            "login": ["a", "b", "a", "b"],
            "taxon_id": [-1, -1, 7, 7],
            "group": ["g"] * 4,
        }
    )
    _, cons = fit(answers)
    row = cons.set_index("record_id").loc[1]
    assert row["n_abstain"] == 2 and row["n_answers"] == 0
    assert pd.isna(row["taxon_id"]) and np.isnan(row["posterior"])
    assert cons.set_index("record_id").loc[2, "taxon_id"] == 7
    assert 1 not in consensus_at(cons, 0.0)["record_id"].to_numpy()


def _hier(seed=0, n_logins=30, n_records=300, per_record=5, coarse=0.35):
    """Records in genus 1000 + r with species 4r..4r+3; a correct student names the species, or
    the genus with probability ``coarse``; a wrong one names another species of the genus."""
    rng = np.random.default_rng(seed)
    acc = rng.uniform(0.6, 0.95, n_logins)
    truth = rng.integers(0, 4, n_records)
    rows = []
    for r in range(n_records):
        for u in rng.choice(n_logins, per_record, replace=False):
            if rng.random() < acc[u]:
                pick = 1000 + r if rng.random() < coarse else 4 * r + truth[r]
            else:
                pick = 4 * r + rng.choice([c for c in range(4) if c != truth[r]])
            rows.append((r, f"u{u}", int(pick), "g"))
    answers = pd.DataFrame(rows, columns=["record_id", "login", "taxon_id", "group"])
    anc = {4 * r + c: frozenset({1000 + r}) for r in range(n_records) for c in range(4)}
    return answers, pd.Series(4 * np.arange(n_records) + truth), anc


def test_rollup_settles_more_records_without_losing_accuracy():
    answers, truth, anc = _hier()
    flat = consensus_at(fit(answers)[1])
    tree = consensus_at(fit(answers, ancestry=anc)[1])
    right = lambda c: (c["taxon_id"].to_numpy() == truth[c["record_id"]].to_numpy()).mean()  # noqa: E731
    assert len(tree) > len(flat)
    assert right(tree[tree["taxon_id"] < 1000]) >= right(flat[flat["taxon_id"] < 1000]) - 0.01


def test_rollup_picks_the_finest_taxon_that_passes():
    anc = {1: frozenset({10}), 2: frozenset({10}), 3: frozenset({20})}
    cand = pd.DataFrame({"record_id": [0, 0, 1, 1, 2, 2], "taxon_id": [1, 2, 1, 2, 1, 3]}).assign(
        posterior=[0.93, 0.07, 0.5, 0.5, 0.6, 0.4]
    )
    out = _roll_up(cand, anc, 0.9).set_index("record_id")
    assert out.loc[0, "taxon_id"] == 1  # species passes
    assert out.loc[1, "taxon_id"] == 10 and out.loc[1, "posterior"] == pytest.approx(1.0)
    assert len(out.loc[2]) == 2  # no shared taxon passes: candidates unchanged


def test_ancestry_from_taxa():
    taxa = pd.DataFrame({"taxon_id": [1, 5], "ancestry": [None, "48460/1/3"]})
    assert ancestry_from_taxa(taxa) == {1: frozenset(), 5: frozenset({48460, 1, 3})}
