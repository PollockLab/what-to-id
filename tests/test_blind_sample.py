import json

import pandas as pd

from what_to_id import blind_sample as bs
from what_to_id import page_blind


def _pool(n=60):
    groups = ["Fungi", "Aves", "Plantae", None]
    return pd.DataFrame(
        {
            "id": range(1, n + 1),
            "iconic_taxon": [groups[i % 4] for i in range(n)],
            "photo_url": [f"https://x/{i}.jpg" for i in range(1, n + 1)],
            "rank": "species",
        }
    )


def test_sample_caps_each_stratum_and_is_seeded():
    pool = _pool()
    a, b = bs.sample(pool, 5, 7), bs.sample(pool, 5, 7)
    assert a.equals(b)
    assert set(a["group"]) == {"Fungi", "Aves", "Plantae"}  # None group skipped
    assert bs.strata(a)["n"].tolist() == [5, 5, 5]
    assert not bs.sample(pool, 5, 8).equals(a)

    levels = pd.DataFrame({"id": range(1, 61), "level": [i % 3 for i in range(60)]})  # 0 skipped
    c = bs.sample(pool, 2, 1, levels)
    s = bs.strata(c)
    assert set(s["level"]) == {1, 2} and s["n"].max() <= 2
    assert len(c) == 12  # 3 groups x 2 levels x 2


def test_to_records_mixes_planted_without_truth_and_rejects_overlap():
    sampled = bs.sample(_pool(), 2, 3)
    planted = [{"id": 999, "group": "Fungi", "photos": ["https://x/p.jpg"], "taxon_id": 48715}]
    recs = bs.to_records(sampled, planted, 3)
    assert len(recs) == len(sampled) + 1
    assert all(set(r) == {"id", "group", "photos", "planted"} for r in recs)
    assert sum(r["planted"] for r in recs) == 1
    assert "taxon_id" not in page_blind.render(recs)
    dup = [{**planted[0], "id": int(sampled["id"].iloc[0])}]
    try:
        bs.to_records(sampled, dup, 3)
    except ValueError:
        pass
    else:
        raise AssertionError("overlap must fail")


def test_main_writes_records_and_planted(tmp_path):
    _pool().to_parquet(tmp_path / "pool.parquet", index=False)
    planted = [{"id": 999, "group": "Fungi", "photos": ["https://x/p.jpg"], "taxon_id": 48715}]
    (tmp_path / "planted.json").write_text(json.dumps(planted))
    out = tmp_path / "site" / "records.json"
    args = ["--pool", str(tmp_path / "pool.parquet"), "--planted", str(tmp_path / "planted.json")]
    assert bs.main([*args, "--per-stratum", "3", "--seed", "1", "--out", str(out)]) == 0
    recs = json.loads(out.read_text())
    assert len(recs) == 10 and "taxon_id" not in out.read_text()
    truth = pd.read_parquet(tmp_path / "site" / "planted.parquet")
    assert truth.to_dict("records") == [{"record_id": 999, "taxon_id": 48715}]
    page_blind.build(tmp_path / "site", recs)
    assert (tmp_path / "site" / "blind.html").exists()
