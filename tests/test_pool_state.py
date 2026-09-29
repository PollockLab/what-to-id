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


def test_prepared_snapshot_retains_closures_across_days_and_reconciles_new_bundle(
    tmp_path, monkeypatch
):
    import json
    import shutil

    from what_to_id.arms import Recency
    from what_to_id.batches import build_batches

    original = _new_rows(range(1, 11))
    original["iconic_taxon"] = "Aves"
    source, pool = tmp_path / "prepared.parquet", tmp_path / "pool.parquet"
    state, ids = tmp_path / "bundle-eligibility.json", tmp_path / "ids.parquet"
    original.to_parquet(source, index=False)
    assignment = original[["id"]].assign(arm="recency")

    def prepare():
        assert (
            pool_state.main(
                [
                    "prepared",
                    "--prepared-pool",
                    str(source),
                    "--pool",
                    str(pool),
                    "--eligibility",
                    str(state),
                ]
            )
            == 0
        )

    def selection():
        return build_batches(
            pd.read_parquet(pool),
            assignment,
            {"recency": Recency()},
            size=2,
            seed=0,
            max_batches=1,
        )["id"].tolist()

    def refresh(closed):
        pd.DataFrame({"id": selection()}).to_parquet(ids, index=False)
        monkeypatch.setattr(pool_state, "still_open", lambda checked: set(checked) - closed)
        assert (
            pool_state.main(
                ["refresh", "--pool", str(pool), "--ids", str(ids), "--eligibility", str(state)]
            )
            == 0
        )

    prepare()
    assert selection() == [10, 9]
    refresh({10})
    assert selection() == [9, 8]
    # Only the small exclusion state is needed to reconstruct the next day's eligible pool.
    saved = tmp_path / "release-asset.json"
    shutil.copyfile(state, saved)
    pool.unlink()
    state.unlink()
    shutil.copyfile(saved, state)
    prepare()
    assert selection() == [9, 8]
    refresh({10, 8})
    assert selection() == [9, 7]
    assert json.loads(state.read_text())["closed_ids"] == [8, 10]

    # A newly prepared needs-ID snapshot is authoritative: include new IDs and reopened IDs.
    updated = pd.concat([original, _new_rows([11])], ignore_index=True)
    updated.to_parquet(source, index=False)
    prepare()
    assert set(pd.read_parquet(pool).id) == set(range(1, 12))
    assert json.loads(state.read_text())["closed_ids"] == []


@pytest.mark.parametrize("bad", ["{}", '{"schema_version":1}', "not-json"])
def test_corrupt_eligibility_fails_before_replacing_pool(tmp_path, bad):
    source, pool, state = (
        tmp_path / name for name in ("source.parquet", "pool.parquet", "state.json")
    )
    _new_rows([1, 2]).to_parquet(source, index=False)
    pool.write_bytes(b"previous pool")
    state.write_text(bad)
    with pytest.raises(ValueError):
        pool_state.main(
            [
                "prepared",
                "--prepared-pool",
                str(source),
                "--pool",
                str(pool),
                "--eligibility",
                str(state),
            ]
        )
    assert pool.read_bytes() == b"previous pool"


def test_cmd_prune_drops_records_that_left_needs_id(tmp_path, monkeypatch):
    pool = make_pool(4)
    pool.loc[:, "id"] = [1, 2, 3, 4]
    pool_path = tmp_path / "pool.parquet"
    pool.to_parquet(pool_path, index=False)
    captured = {}

    def fake_closed_since(since, *, d1):
        captured.update(since=since, d1=d1)
        return {2, 4, 99}

    monkeypatch.setattr(pool_state, "closed_since", fake_closed_since)
    rc = pool_state.main(
        ["prune", "--pool", str(pool_path), "--since", "2026-09-28T00:00:00Z", "--d1", "2025-01-01"]
    )
    assert rc == 0
    assert captured == {"since": "2026-09-28T00:00:00Z", "d1": "2025-01-01"}
    assert pd.read_parquet(pool_path)["id"].tolist() == [1, 3]
