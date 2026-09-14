import pandas as pd
import pytest

from what_to_id import pool_state
from what_to_id.inat import COLUMNS, DTYPES

from .conftest import make_pool


def _new_rows(ids, created="2026-09-01T00:00:00+00:00"):
    df = make_pool(len(ids))
    df["id"] = pd.array(ids, dtype="int64")
    df["created_at"] = created
    return df


def test_merge_new_dedupes_new_wins_and_keeps_dtypes():
    pool = make_pool(3)
    pool.loc[:, "id"] = [1, 2, 3]
    new = _new_rows([2, 4])
    new.loc[new["id"] == 2, "taxon_name"] = "Updated"
    merged = pool_state.merge_new(pool, new)
    assert list(merged["id"]) == [1, 2, 3, 4]
    row2 = merged[merged["id"] == 2].iloc[0]
    assert row2["taxon_name"] == "Updated"
    for col, dtype in DTYPES.items():
        assert str(merged[col].dtype) == dtype
    assert list(merged.columns) == list(COLUMNS)


def test_merge_new_rejects_column_mismatch():
    pool = make_pool(2)
    bad = pool.drop(columns=["photo_url"])
    with pytest.raises(ValueError, match="photo_url"):
        pool_state.merge_new(pool, bad)


def test_drop_closed_keeps_unchecked_ids():
    pool = make_pool(4)
    pool.loc[:, "id"] = [10, 11, 12, 13]
    updated = pool_state.drop_closed(pool, checked=[10, 11], open_ids={10})
    assert sorted(updated["id"]) == [10, 12, 13]


def test_drop_closed_no_closures_returns_all():
    pool = make_pool(3)
    pool.loc[:, "id"] = [1, 2, 3]
    updated = pool_state.drop_closed(pool, checked=[1, 2, 3], open_ids={1, 2, 3})
    assert sorted(updated["id"]) == [1, 2, 3]


def test_last_created():
    pool = make_pool(5)
    ts = pool_state.last_created(pool)
    expected = pd.to_datetime(pool["created_at"], utc=True).max()
    assert ts == expected


def test_last_created_empty_pool_raises():
    pool = make_pool(0)
    with pytest.raises(ValueError, match="empty"):
        pool_state.last_created(pool)


def test_cmd_update_pulls_since_last_created_and_merges(tmp_path, monkeypatch):
    pool = make_pool(3)
    pool.loc[:, "id"] = [1, 2, 3]
    pool_path = tmp_path / "pool.parquet"
    pool.to_parquet(pool_path, index=False)

    captured = {}

    def fake_pull_pool(*, d1, freeze, out, created_d1, **kw):
        captured["created_d1"] = created_d1
        captured["d1"] = d1
        return _new_rows([4, 5])

    monkeypatch.setattr(pool_state, "pull_pool", fake_pull_pool)

    rc = pool_state.main(["update", "--pool", str(pool_path), "--overlap-hours", "6"])
    assert rc == 0

    expected_since = pool_state.last_created(pool) - pd.Timedelta(hours=6)
    assert captured["created_d1"] == expected_since
    assert captured["d1"] == pool_state.DEFAULT_D1

    result = pd.read_parquet(pool_path)
    assert sorted(result["id"]) == [1, 2, 3, 4, 5]


def test_cmd_update_uses_given_d1(tmp_path, monkeypatch):
    pool = make_pool(2)
    pool.loc[:, "id"] = [1, 2]
    pool_path = tmp_path / "pool.parquet"
    pool.to_parquet(pool_path, index=False)

    captured = {}

    def fake_pull_pool(*, d1, freeze, out, created_d1, **kw):
        captured["d1"] = d1
        return _new_rows([3])

    monkeypatch.setattr(pool_state, "pull_pool", fake_pull_pool)
    rc = pool_state.main(["update", "--pool", str(pool_path), "--d1", "2026-01-01"])
    assert rc == 0
    assert captured["d1"] == "2026-01-01"


def test_cmd_refresh_drops_closed_ids(tmp_path, monkeypatch):
    pool = make_pool(4)
    pool.loc[:, "id"] = [1, 2, 3, 4]
    pool_path = tmp_path / "pool.parquet"
    pool.to_parquet(pool_path, index=False)

    served = pd.DataFrame({"id": pd.array([1, 2, 3], dtype="int64")})
    served_path = tmp_path / "served.parquet"
    served.to_parquet(served_path, index=False)

    captured = {}

    def fake_still_open(ids, *, session=None):
        captured["ids"] = list(ids)
        return {1, 3}

    monkeypatch.setattr(pool_state, "still_open", fake_still_open)

    rc = pool_state.main(["refresh", "--pool", str(pool_path), "--ids", str(served_path)])
    assert rc == 0
    assert sorted(captured["ids"]) == [1, 2, 3]

    result = pd.read_parquet(pool_path)
    assert sorted(result["id"]) == [1, 3, 4]
