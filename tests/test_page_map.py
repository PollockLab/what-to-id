import gzip
import json
import re

import numpy as np
import pandas as pd
import pytest

from what_to_id.page import ARM_WORDS
from what_to_id.page_map import (
    BYTES_PER_RECORD,
    MAP_NAME,
    NO_DAY,
    TAXA_NAME,
    decode_points,
    encode_points,
    main,
    render_map,
    shard_name,
    write_map,
)

from .conftest import make_pool


def _with_extras(pool):
    n = len(pool)
    pool = pool.copy()
    pool["common_name"] = [None if i % 3 else f"Common {i}" for i in range(n)]
    pool["introduced"] = pd.array([i % 2 == 0 for i in range(n)], dtype="boolean")
    pool["threatened"] = pd.array([None] + [i % 5 == 0 for i in range(1, n)], dtype="boolean")
    pool["obscured"] = pd.array([i % 7 == 0 for i in range(n)], dtype="boolean")
    pool["pos_acc"] = pd.array([None] + [i * 100 for i in range(1, n)], dtype="Int64")
    pool["ident_count"] = np.arange(n) % 20
    pool["agree"] = np.arange(n) % 3
    return pool


def test_encode_round_trips_within_quantization():
    pool = _with_extras(make_pool(300, seed=3)).sample(frac=1, random_state=0)
    blobs, meta = encode_points(pool)
    assert sum(s["n"] for s in meta["shards"]) == meta["n"] == len(pool)
    for s in meta["shards"]:
        assert len(gzip.decompress(blobs[s["file"]])) == BYTES_PER_RECORD * s["n"]
    back = decode_points(blobs, meta)
    want = pool.sort_values("id").reset_index(drop=True)
    assert back["id"].tolist() == want["id"].tolist()
    x0, y0, x1, y1 = meta["bbox"]
    assert np.abs(back["lon"] - want["lon"]).max() <= (x1 - x0) / 65535
    assert np.abs(back["lat"] - want["lat"]).max() <= (y1 - y0) / 65535
    assert (back["observed_on"] == pd.to_datetime(want["observed_on"])).all()
    up = pd.to_datetime(want["created_at"], utc=True).dt.tz_localize(None).dt.normalize()
    assert (back["uploaded_on"] == up).all()
    assert back["iconic_taxon"].tolist() == want["iconic_taxon"].tolist()
    assert back["taxon_name"].tolist() == want["taxon_name"].tolist()
    assert back["rank"].tolist() == want["rank"].tolist()
    assert back["ident_count"].tolist() == np.minimum(want["ident_count"], 15).tolist()
    assert back["agree"].tolist() == want["agree"].tolist()
    assert meta["flags"] == ["introduced", "threatened", "obscured", "imprecise"]
    assert back["introduced"].tolist() == want["introduced"].tolist()
    assert back["threatened"].tolist() == want["threatened"].fillna(False).tolist()
    assert back["obscured"].tolist() == want["obscured"].tolist()
    assert back["imprecise"].tolist() == (want["pos_acc"].fillna(0) > 1000).tolist()
    assert meta["sha256"] and meta["groups"] == sorted(pool["iconic_taxon"].unique())


def test_common_names_follow_the_taxon():
    pool = make_pool(4)
    pool["taxon_id"] = pd.array([7, 3, 7, None], dtype="Int64")
    pool["taxon_name"] = ["Alnus", "Acer", "Alnus", None]
    pool["common_name"] = ["alders", None, "alders", None]
    blobs, meta = encode_points(pool)
    assert json.loads(gzip.decompress(blobs[TAXA_NAME])) == [["Acer", ""], ["Alnus", "alders"]]
    back = decode_points(blobs, meta)
    assert back["common_name"].iloc[:3].tolist() == ["alders", "", "alders"]
    assert back["taxon_name"].iloc[:3].tolist() == ["Alnus", "Acer", "Alnus"]
    assert back[["common_name", "taxon_name"]].iloc[3].isna().all()


def test_old_pool_without_extras_has_no_flags():
    blobs, meta = encode_points(make_pool(10))
    assert meta["flags"] == []
    assert "introduced" not in decode_points(blobs, meta)


def test_recent_records_come_first_and_old_ones_after():
    pool = make_pool(5)
    pool["observed_on"] = ["1987-06-01", "2024-12-31", "2025-01-01", None, "2026-09-01"]
    blobs, meta = encode_points(pool)
    assert [s["file"] for s in meta["shards"]] == [shard_name(0), shard_name(1)]
    assert [s["n"] for s in meta["shards"]] == [3, 2]
    first = decode_points({**blobs}, {**meta, "shards": meta["shards"][:1]})
    assert first["id"].tolist() == pool["id"].iloc[2:].tolist()
    assert meta["day0"] == "1987-06-01"
    assert meta["hist0"] == 0
    assert decode_points(blobs, meta)["id"].tolist() == pool["id"].tolist()


def test_histogram_starts_after_rare_old_records():
    pool = make_pool(1000)
    pool.loc[0, "observed_on"] = "1949-05-01"
    _, meta = encode_points(pool)
    assert meta["day0"] == "1949-05-01"
    start = pd.Timestamp(meta["day0"]) + pd.Timedelta(days=meta["hist0"])
    assert start == pd.Timestamp("2026-01-01")


def test_late_upload_and_missing_date():
    pool = make_pool(3)
    pool["observed_on"] = ["2025-01-01", None, "2026-09-01"]
    pool["created_at"] = ["2026-09-20T10:00:00Z", "2026-09-21T10:00:00Z", "2026-09-02T01:00:00Z"]
    blobs, meta = encode_points(pool)
    assert meta["day0"] == "2025-01-01"
    back = decode_points(blobs, meta)
    assert back["observed_on"].isna().tolist() == [False, True, False]
    assert back["uploaded_on"].iloc[0] == pd.Timestamp("2026-09-20")
    n = meta["shards"][0]["n"]
    obs = np.frombuffer(gzip.decompress(blobs[shard_name(0)]), "<u2", n, 8 * n)
    assert NO_DAY in obs.tolist()
    assert meta["days"] == (pd.Timestamp("2026-09-21") - pd.Timestamp("2025-01-01")).days + 1


def test_files_are_deterministic():
    pool = _with_extras(make_pool(50))
    assert encode_points(pool) == encode_points(pool.sample(frac=1, random_state=1))


@pytest.mark.parametrize(
    "change, msg",
    [
        (lambda p: p.iloc[0:0], "empty"),
        (lambda p: p.drop(columns="created_at"), "lacks columns"),
        (lambda p: p.assign(lat=np.nan), "without coordinates"),
        (lambda p: p.assign(id=-1), "uint32"),
        (lambda p: p.assign(observed_on=None), "observed date"),
    ],
)
def test_encode_rejects_bad_pools(change, msg):
    with pytest.raises(ValueError, match=msg):
        encode_points(change(make_pool(5)))


def test_decode_rejects_wrong_size():
    blobs, meta = encode_points(make_pool(5))
    cut = gzip.compress(gzip.decompress(blobs[shard_name(0)])[:-1])
    with pytest.raises(ValueError, match="expected"):
        decode_points({**blobs, shard_name(0): cut}, meta)


def test_page_is_blind_and_carries_meta():
    _, meta = encode_points(make_pool(20))
    html = render_map(meta, freeze="2026-09-28")
    low = html.lower()
    assert not [w for w in ARM_WORDS if w in low]
    assert "{{" not in html
    m = re.search(r"var META=(\{.*?\});var BASEMAPS", html)
    page_meta = json.loads(m.group(1))
    v = meta["sha256"][:12]
    assert page_meta["n"] == 20
    assert page_meta["shards"] == [{"file": f"{shard_name(0)}?v={v}", "n": 20}]
    assert page_meta["taxa"] == f"{TAXA_NAME}?v={v}"
    assert "18*n" in html and "on 2026-09-28" in html


def test_meta_cannot_close_the_script():
    pool = make_pool(3).assign(iconic_taxon="</script><b>")
    _, meta = encode_points(pool)
    assert "</script><b>" not in render_map(meta, freeze=None)


def test_write_map_and_cli(tmp_path):
    pool = make_pool(40)
    paths = write_map(tmp_path / "a", pool)
    assert sorted(p.name for p in paths) == sorted([MAP_NAME, shard_name(0), TAXA_NAME])
    pool.to_parquet(tmp_path / "pool.parquet", index=False)
    assert main(["--pool", str(tmp_path / "pool.parquet"), "--out", str(tmp_path / "b")]) == 0
    for name in (shard_name(0), TAXA_NAME, MAP_NAME):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()
