import json

import pandas as pd

from what_to_id.blind_planted import COLUMNS, KINDS, candidates, main, pick


def _frames():
    # 1: cv first ID held, two others agree. 2: cv first ID failed, two others agree on 20.
    # 3: typed, only one other agrees. 4: needs_id. 5: typed failed, two agree.
    obs = pd.DataFrame(
        {
            "id": [1, 2, 3, 4, 5],
            "user_id": 9,
            "quality_grade": ["research"] * 3 + ["needs_id", "research"],
        }
    )
    pool = pd.DataFrame(
        {
            "id": [1, 2, 3, 4, 5],
            "iconic_taxon": ["Aves", "Aves", "Plantae", "Aves", "Fungi"],
            "taxon_id": [10, 20, 30, 40, 50],
            "photo_url": [f"https://x/{i}.jpg" for i in range(1, 6)],
        }
    )
    rows = [
        (1, 9, "t0", 10, True),
        (1, 7, "t1", 10, False),
        (1, 8, "t2", 10, False),
        (2, 9, "t0", 21, True),
        (2, 7, "t1", 20, False),
        (2, 8, "t2", 20, False),
        (3, 9, "t0", 30, False),
        (3, 7, "t1", 30, False),
        (4, 9, "t0", 40, True),
        (4, 7, "t1", 40, False),
        (4, 8, "t2", 40, False),
        (5, 9, "t0", 51, False),
        (5, 7, "t1", 50, False),
        (5, 8, "t2", 50, False),
    ]
    idents = pd.DataFrame(rows, columns=["id", "user_id", "created_at", "taxon_id", "vision"])
    idents["observer_id"] = 9
    idents["taxon_rank"] = "species"
    idents["current"] = True
    return obs, idents, pool


def test_candidates_kinds_and_filters():
    obs, idents, pool = _frames()
    out = candidates(obs, idents, pool)
    assert list(out.columns) == COLUMNS
    assert dict(zip(out["id"], out["kind"], strict=True)) == {
        1: "cv_hold",
        2: "cv_fail",
        5: "typed_fail",
    }
    assert out.set_index("id").loc[2, "taxon_id"] == 20  # the settled name, not the first ID
    assert 3 in candidates(obs, idents, pool, min_others=1)["id"].tolist()


def test_coarse_first_id_is_not_a_failure():
    obs, idents, pool = _frames()
    idents.loc[(idents["id"] == 2) & (idents["user_id"] == 9), "taxon_rank"] = "genus"
    assert 2 not in candidates(obs, idents, pool)["id"].tolist()


def test_withdrawn_agreement_does_not_count():
    obs, idents, pool = _frames()
    idents.loc[(idents["id"] == 1) & (idents["user_id"] == 8), "current"] = False
    assert 1 not in candidates(obs, idents, pool)["id"].tolist()


def test_pick_shape_and_main(tmp_path):
    obs, idents, pool = _frames()
    rows = pick(candidates(obs, idents, pool), per_kind=1, seed=0)
    assert [r["kind"] for r in rows] == ["cv_fail", "cv_hold", "typed_fail"]
    assert set(rows[0]) == {"id", "group", "photos", "taxon_id", "kind"}
    for name, df in (("obs", obs), ("idents", idents), ("pool", pool)):
        df.to_parquet(tmp_path / f"{name}.parquet", index=False)
    out = tmp_path / "p" / "planted.json"
    argv = [
        a for n in ("obs", "idents", "pool") for a in (f"--{n}", str(tmp_path / f"{n}.parquet"))
    ]
    assert main([*argv, "--out", str(out)]) == 0
    assert len(json.loads(out.read_text())) == 3 and set(KINDS) >= {r["kind"] for r in rows}
