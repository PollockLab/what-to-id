"""pool-observer.bin: the observer of each map record, in the order of the shards."""

import gzip

import numpy as np
import pandas as pd

from what_to_id.map_observer import OBSERVER_NAME, decode_observer
from what_to_id.page_map import _decode_shard, encode_points, render_map
from what_to_id.site_files import hashed

from .conftest import make_pool


def shard_ids(blobs, meta):
    return np.concatenate(
        [_decode_shard(gzip.decompress(blobs[s["file"]]), s["n"])["id"] for s in meta["shards"]]
    )


def test_the_file_holds_four_bytes_a_record_in_shard_order(monkeypatch):
    monkeypatch.setattr("what_to_id.page_map.SHARD_MAX", 40)
    pool = make_pool(300, seed=3).sample(frac=1, random_state=0)
    pool["observed_on"] = (
        pd.Timestamp("2026-08-31") - pd.to_timedelta(np.arange(len(pool)) * 7, "D")
    ).strftime("%Y-%m-%d")
    blobs, meta = encode_points(pool)
    assert len(meta["shards"]) > 2 and meta["observer"].startswith("pool-observer.")
    assert len(gzip.decompress(blobs[meta["observer"]])) == 4 * len(pool)
    users = decode_observer(blobs[meta["observer"]])
    want = pool.set_index("id")["user_id"].astype("int64")
    assert users.tolist() == want.loc[shard_ids(blobs, meta)].tolist()


def test_missing_or_oversized_observers_are_zero():
    pool = make_pool(5)
    pool["user_id"] = pd.array([7, None, 0, 2**32, 4294967295], dtype="Int64")
    blobs, meta = encode_points(pool)
    assert decode_observer(blobs[meta["observer"]]).tolist() == [7, 0, 0, 0, 4294967295]


def test_a_pool_without_users_has_no_observer_file_and_the_page_has_no_url_for_it():
    blobs, meta = encode_points(make_pool(5).drop(columns="user_id"))
    assert not any(n.startswith("pool-observer") for n in blobs) and "observer" not in meta
    assert '"observer"' not in render_map(meta, freeze=None)


def test_the_page_names_the_file_by_its_hash_and_the_shards_keep_17_bytes(monkeypatch):
    blobs, meta = encode_points(make_pool(20))
    html = render_map(meta, freeze=None)
    assert f'"observer":"{hashed(OBSERVER_NAME, blobs[meta["observer"]])}"' in html
    assert len(gzip.decompress(blobs[meta["shards"][0]["file"]])) == 17 * 20
