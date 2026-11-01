import numpy as np
import pandas as pd

from what_to_id.blind_skill import CONSENSUS_COLUMNS, SKILL_COLUMNS, consensus_at, fit


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
