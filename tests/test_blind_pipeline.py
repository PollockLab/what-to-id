"""The blind track end to end: pool -> records.json -> page -> exports -> answers -> fit -> report.

Pins the formats the five modules pass between them. The browser step is replaced by writing the
JSONL the page exports; `tests/test_page_blind.py` covers the page itself.
"""

import json

import numpy as np
import pandas as pd

from what_to_id import blind_answers, blind_report, blind_sample, page_blind
from what_to_id.blind_skill import fit

GROUPS = ["Plantae", "Fungi", "Aves"]


def test_blind_track_round_trip(tmp_path, monkeypatch):
    rng = np.random.default_rng(0)
    n = 90
    pool = pd.DataFrame(
        {
            "id": np.arange(1, n + 1),
            "iconic_taxon": [GROUPS[i % 3] for i in range(n)],
            "photo_url": [f"https://x/{i}.jpg" for i in range(n)],
        }
    )
    pool.to_parquet(tmp_path / "pool.parquet", index=False)
    planted = [{"id": 1000, "group": "Fungi", "photos": ["https://x/p.jpg"], "taxon_id": 500}]
    (tmp_path / "planted.json").write_text(json.dumps(planted))
    out = tmp_path / "site" / "records.json"
    args = ["--pool", str(tmp_path / "pool.parquet"), "--planted", str(tmp_path / "planted.json")]
    assert blind_sample.main([*args, "--per-stratum", "10", "--seed", "1", "--out", str(out)]) == 0
    records = json.loads(out.read_text())
    assert len(records) == 31
    page = page_blind.build(tmp_path / "site", records)
    assert "taxon_id" not in page.read_text()

    # truth: record id -> taxon id; the first own ID is right 90% when typed, 70% when CV-accepted
    truth = {r["id"]: (500 if r["planted"] else r["id"] * 10) for r in records}
    names = {f"Taxon {t}": t for v in truth.values() for t in (v, v + 1)}  # right and wrong
    logins = [f"s{i}" for i in range(12)]
    skill = dict(zip(logins, rng.uniform(0.6, 0.95, len(logins)), strict=True))
    exports = []
    for login in logins:
        rows = []
        for r in rng.choice(len(records), 20, replace=False):
            rec = records[r]
            if rng.random() < 0.1:
                taxon, conf = "", "abstain"
            elif rng.random() < skill[login]:
                taxon, conf = f"Taxon {truth[rec['id']]}", "sure"
            else:
                taxon, conf = f"Taxon {truth[rec['id']] + 1}", "guess"
            rows.append(
                {"record_id": rec["id"], "login": login, "taxon": taxon, "confidence": conf,
                 "seconds": 4.0, "saved_at": "2026-11-01T20:00:00Z"}
            )  # fmt: skip
        p = tmp_path / f"blind-answers-{login}.jsonl"
        p.write_text("".join(json.dumps(x) + "\n" for x in rows))
        exports.append(p)

    names_path = tmp_path / "names.json"
    names_path.write_text(json.dumps({k: v for k, v in names.items() if v % 2}))  # half known
    looked = []
    monkeypatch.setattr(
        blind_answers, "inat_lookup", lambda name, session=None: looked.append(name) or names[name]
    )
    ans_path = tmp_path / "answers.parquet"
    rc = blind_answers.main(
        [
            *map(str, exports),
            "--records",
            str(out),
            "--names",
            str(names_path),
            "--out",
            str(ans_path),
        ]
    )
    assert rc == 0 and looked and json.loads(names_path.read_text()) == names
    answers = pd.read_parquet(ans_path)
    assert list(answers.columns) == blind_answers.COLUMNS

    planted_truth = pd.read_parquet(tmp_path / "site" / "planted.parquet")
    skill_df, consensus = fit(answers, planted_truth)
    assert consensus.loc[consensus["record_id"] == 1000, "taxon_id"].item() == 500
    got = consensus.dropna(subset=["taxon_id"]).set_index("record_id")["taxon_id"]
    assert (got == pd.Series(truth).reindex(got.index)).mean() > 0.9
    est = skill_df.groupby("login")["accuracy"].mean()
    # 20 answers per login is too few to pin accuracy; test_blind_skill.py does that at scale
    assert np.corrcoef(est, pd.Series(skill).loc[est.index])[0, 1] > 0

    # read-back shaped frames for the report: observer's first own ID, CV flag on half
    ids = [r["id"] for r in records if not r["planted"]]
    obs = pd.DataFrame({"id": ids, "user_id": 7, "iconic_taxon": [GROUPS[i % 3] for i in ids]})
    cv = {i: bool(i % 2) for i in ids}
    first_right = {i: rng.random() < (0.7 if cv[i] else 0.9) for i in ids}
    idents = pd.DataFrame(
        {
            "id": ids,
            "user_id": 7,
            "observer_id": 7,
            "created_at": "2026-01-01T00:00:00Z",
            "taxon_id": [truth[i] if first_right[i] else truth[i] + 1 for i in ids],
            "vision": [cv[i] for i in ids],
        }
    )
    firsts = blind_report.first_own_ids(obs, idents)
    report = blind_report.cv_error(consensus, firsts)
    assert list(report.columns) == blind_report.REPORT_COLUMNS
    allrows = report[report["group"] == "all"].set_index("source")
    assert set(allrows.index) == {"cv", "typed"}
    assert (allrows["lo"] <= allrows["error"]).all() and (allrows["error"] <= allrows["hi"]).all()
    public = pd.DataFrame({"record_id": ids, "taxon_id": [truth[i] for i in ids]})  # all caught
    det = blind_report.detection_rate(consensus, firsts, public, boot=100)
    assert list(det.columns) == blind_report.DETECT_COLUMNS
    # below 1 only because the student consensus itself is wrong on a few records
    assert det.loc[det["group"] == "all", "detection"].between(0.5, 1.0).all()
    lv = blind_report.level_table(consensus, pd.read_parquet(tmp_path / "site" / "levels.parquet"))
    assert lv["level"].tolist() == [0] and lv["n"].item() == 30  # no --levels: one stratum
