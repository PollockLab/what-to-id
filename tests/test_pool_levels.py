"""pool-levels.bin and pool-levels-looks.bin: identify.parquet packed per pool record."""

import gzip

import numpy as np
import pandas as pd
import pytest

from what_to_id import pool_levels
from what_to_id.identify import IDENTIFY_COLUMNS
from what_to_id.page_map import decode_points, encode_points, render_map

from .embeddings_fixture import TREE, pool_frame

N = 300
LOOKS = ["Bombus a", "Bombus b", "Apis c"]


def write_site(tmp_path):
    ids = np.random.default_rng(4).choice(2**31, N, replace=False) + 1
    blobs, meta = encode_points(pool_frame(ids), TREE)
    site = tmp_path / "site"
    site.mkdir()
    for name, blob in blobs.items():
        (site / name).write_bytes(blob)
    (site / "map.html").write_text(render_map(meta, freeze=None))
    return site, decode_points(blobs, meta)


def scored_frame(points):
    """Every third pool record missing, one with a new label, levels cycling over all five."""
    rng = np.random.default_rng(6)
    df = pd.DataFrame(
        {
            "id": points["id"].to_numpy(np.int64),
            "taxon_id": points["taxon_id"].to_numpy(np.int64),
            "level": np.arange(N) % 5,
            "score": rng.normal(size=N).astype(np.float32),
            "score2": np.float32(0),
            "looks_like": pd.Series([LOOKS[i % 3] for i in range(N)], dtype="category"),
        }
    )
    df = df.drop(index=range(0, N, 3)).reset_index(drop=True)
    df.loc[1, "taxon_id"] += 1  # labelled differently now: its level no longer applies
    return df[list(IDENTIFY_COLUMNS)].astype({"level": "int8"})


def test_the_pack_round_trips_identify_parquet_in_shard_order(tmp_path):
    site, points = write_site(tmp_path)
    df = scored_frame(points)
    df.to_parquet(tmp_path / "identify.parquet")
    assert (
        pool_levels.main(["--out", str(site), "--parquet", str(tmp_path / "identify.parquet")]) == 0
    )
    level, q = pool_levels.unpack((site / pool_levels.OUT_NAME).read_bytes())
    looks = pool_levels.unpack_looks((site / pool_levels.LOOKS_NAME).read_bytes(), N)
    assert len(level) == len(q) == len(looks) == N
    row = df.set_index("id")
    for i, pid in enumerate(points["id"]):
        if pid not in row.index or (row.at[pid, "taxon_id"] != points["taxon_id"][i]):
            assert level[i] == 0 and q[i] == 0 and looks[i] is None  # missing or relabelled
            continue
        want = int(row.at[pid, "level"])
        assert level[i] == want
        assert looks[i] == (row.at[pid, "looks_like"] if want in (2, 3) else None)
    assert (level == 0).sum() >= N // 3 + 1 and set(level) == {0, 1, 2, 3, 4}


def test_the_score_steps_rank_within_a_level_and_weird_shows_the_lowest_first():
    level = np.array([1, 1, 1, 1, 4, 4, 4, 4, 0], np.int8)
    score = np.array([0.1, 0.4, 0.3, 0.2, 0.1, 0.4, 0.3, 0.2, np.nan], np.float32)
    got, q = pool_levels.unpack(pool_levels.pack(level, score))
    assert got.tolist() == level.tolist()
    assert q[:4].tolist() == [0, 12, 8, 4] and q[4:8].tolist() == [12, 0, 4, 8] and q[8] == 0


def test_a_build_without_a_table_says_so(tmp_path):
    site, _ = write_site(tmp_path)
    with pytest.raises(ValueError, match="--data-url or --parquet"):
        pool_levels.build(site)


def test_packing_nothing_and_a_record_without_levels():
    level, q = pool_levels.unpack(pool_levels.pack(np.zeros(0, np.int8), np.zeros(0, np.float32)))
    assert len(level) == len(q) == 0
    blob = pool_levels.pack_looks(np.zeros(3, np.int8), np.full(3, "x", dtype=object))
    assert pool_levels.unpack_looks(blob, 3) == [None] * 3


def test_three_million_records_fit_the_levels_budget():
    n = 3_100_000
    rng = np.random.default_rng(0)
    level = rng.choice([0, 1, 2, 3, 4], n, p=[0.3, 0.25, 0.1, 0.3, 0.05]).astype(np.int8)
    blob = pool_levels.pack(level, rng.normal(size=n).astype(np.float32))
    print(f"pool-levels.bin {len(blob) / 1e6:.2f} MB gzipped for {n} records")
    assert len(blob) <= 3_000_000
    assert len(gzip.decompress(blob)) == n
    # the look-alike names of levels 2 and 3, 8000 of them in a long tail: apart, as measured
    looks = np.array([f"S{k}" for k in range(8000)], dtype=object)
    weight = 1 / np.arange(1, 8001)
    lk = pool_levels.pack_looks(level, looks[rng.choice(8000, n, p=weight / weight.sum())])
    print(f"pool-levels-looks.bin {len(lk) / 1e6:.2f} MB gzipped")
