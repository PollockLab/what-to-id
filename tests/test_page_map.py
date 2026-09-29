import json
import re

import numpy as np
import pandas as pd
import pytest

from what_to_id.page import ARM_WORDS
from what_to_id.page_map import (
    BIN_NAME,
    BYTES_PER_RECORD,
    MAP_NAME,
    NO_DAY,
    decode_points,
    encode_points,
    main,
    render_map,
    write_map,
)

from .conftest import make_pool


def test_encode_round_trips_within_quantization():
    pool = make_pool(300, seed=3).sample(frac=1, random_state=0)
    blob, meta = encode_points(pool)
    assert len(blob) == BYTES_PER_RECORD * len(pool) == BYTES_PER_RECORD * meta["n"]
    back = decode_points(blob, meta)
    want = pool.sort_values("id").reset_index(drop=True)
    assert back["id"].tolist() == want["id"].tolist()
    x0, y0, x1, y1 = meta["bbox"]
    assert np.abs(back["lon"] - want["lon"]).max() <= (x1 - x0) / 65535
    assert np.abs(back["lat"] - want["lat"]).max() <= (y1 - y0) / 65535
    assert (back["observed_on"] == pd.to_datetime(want["observed_on"])).all()
    up = pd.to_datetime(want["created_at"], utc=True).dt.tz_localize(None).dt.normalize()
    assert (back["uploaded_on"] == up).all()
    assert back["iconic_taxon"].tolist() == want["iconic_taxon"].tolist()
    assert meta["sha256"] and meta["groups"] == sorted(pool["iconic_taxon"].unique())


def test_late_upload_and_missing_date():
    pool = make_pool(3)
    pool["observed_on"] = ["2025-01-01", None, "2026-09-01"]
    pool["created_at"] = ["2026-09-20T10:00:00Z", "2026-09-21T10:00:00Z", "2026-09-02T01:00:00Z"]
    blob, meta = encode_points(pool)
    assert meta["day0"] == "2025-01-01"
    back = decode_points(blob, meta)
    assert back["observed_on"].isna().tolist() == [False, True, False]
    assert back["uploaded_on"].iloc[0] == pd.Timestamp("2026-09-20")
    n = meta["n"]
    obs = np.frombuffer(blob, "<u2", n, 8 * n)
    assert obs[1] == NO_DAY
    assert meta["days"] == (pd.Timestamp("2026-09-21") - pd.Timestamp("2025-01-01")).days + 1


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
    blob, meta = encode_points(make_pool(5))
    with pytest.raises(ValueError, match="expected"):
        decode_points(blob[:-1], meta)


def test_page_is_blind_and_carries_meta():
    _, meta = encode_points(make_pool(20))
    html = render_map(meta, freeze="2026-09-28")
    low = html.lower()
    assert not [w for w in ARM_WORDS if w in low]
    m = re.search(r"var META=(\{.*?\});", html)
    page_meta = json.loads(m.group(1))
    assert page_meta["n"] == 20
    assert page_meta["bin"] == f"{BIN_NAME}?v={meta['sha256'][:12]}"
    assert "13*n" in html and "on 2026-09-28" in html


def test_write_map_and_cli(tmp_path):
    pool = make_pool(40)
    paths = write_map(tmp_path / "a", pool)
    assert sorted(p.name for p in paths) == sorted([MAP_NAME, BIN_NAME])
    pool.to_parquet(tmp_path / "pool.parquet", index=False)
    assert main(["--pool", str(tmp_path / "pool.parquet"), "--out", str(tmp_path / "b")]) == 0
    a, b = (tmp_path / d / BIN_NAME for d in "ab")
    assert a.read_bytes() == b.read_bytes()
