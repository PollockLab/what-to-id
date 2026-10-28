import pandas as pd
import pytest

from what_to_id import taxon_status
from what_to_id.taxon_status import COLUMNS, fetch_status, main, update_status

from .conftest import make_pool

ARMS = ("recency", "gap_first", "similarity", "novelty")


def _cs(authority, status, place_id, geoprivacy="open"):
    place = {"id": place_id} if place_id else None
    return {"authority": authority, "status": status, "place": place, "geoprivacy": geoprivacy}


PAYLOAD = {
    10: {
        "id": 10,
        "establishment_means": {"establishment_means": "native"},
        "conservation_statuses": [
            _cs("NatureServe", "G3", None, "obscured"),
            _cs("Canadian Species at Risk Act", "Endangered", 6712, "private"),
            _cs("NatureServe", "N1", 6712),
            _cs("NatureServe", "S1", 7085, "open"),
            _cs("NatureServe", "S1", 7085, "obscured"),
            _cs("NatureServe", "S2", 46),
        ],
    },
    11: {
        "id": 11,
        "conservation_statuses": [_cs("Canadian Species at Risk Act", "Threatened", 6712)],
    },
    12: {"id": 12, "conservation_statuses": [], "establishment_means": None},
}


class FakeSession:
    def __init__(self, payload=PAYLOAD):
        self.payload, self.calls = payload, []

    def get(self, url, params, timeout):
        ids = [int(i) for i in url.rsplit("/", 1)[1].split(",")]
        self.calls.append(ids)
        results = [self.payload.get(i, {"id": i}) for i in ids]

        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"results": results}

        return R()


def test_fetch_status_maps_ranks_and_nulls():
    got = fetch_status([10, 11, 12], session=FakeSession())
    assert got[10] == {
        "natureserve_bc_srank": "S1",
        "natureserve_n_rank": "N1",
        "sara_status": "Endangered",
        "establishment_means": "native",
        "geoprivacy": "obscured",
    }
    assert got[11]["sara_status"] == "Threatened" and got[11]["geoprivacy"] == "open"
    assert got[11]["natureserve_bc_srank"] is None
    assert got[12] == dict.fromkeys(got[12])


def test_fetch_status_refuses_more_than_one_request():
    with pytest.raises(ValueError, match="at most"):
        fetch_status(range(taxon_status.PER_REQUEST + 1), session=FakeSession())


def test_update_status_is_incremental(tmp_path):
    path, s = tmp_path / "status.parquet", FakeSession()
    assert update_status(path, [10, 11], session=s, sleep=0, today="2026-11-01") == 2
    assert update_status(path, [10, 11], session=s, sleep=0, today="2026-11-02") == 0
    assert s.calls == [[10, 11]]
    assert update_status(path, [10, 12], session=s, sleep=0, today="2026-11-02") == 1
    assert s.calls[-1] == [12]
    df = pd.read_parquet(path)
    assert list(df.columns) == COLUMNS
    assert df["taxon_id"].tolist() == [10, 11, 12] and str(df["taxon_id"].dtype) == "int64"
    assert df.set_index("taxon_id")["lookup_date"].to_dict() == {
        10: "2026-11-01",
        11: "2026-11-01",
        12: "2026-11-02",
    }
    assert pd.isna(df.loc[2, "sara_status"]) and not (df.astype(str) == "").any().any()
    assert not (tmp_path / "status.parquet.tmp").exists()


def test_update_status_batches_by_per_request(tmp_path, monkeypatch):
    monkeypatch.setattr(taxon_status, "PER_REQUEST", 2)
    s = FakeSession()
    assert update_status(tmp_path / "s.parquet", [1, 2, 3], session=s, sleep=0) == 3
    assert s.calls == [[1, 2], [3]]


def test_main_writes_the_table(tmp_path, monkeypatch):
    pool = make_pool(30)
    pool.to_parquet(tmp_path / "pool.parquet")
    s = FakeSession()
    monkeypatch.setattr(taxon_status, "make_session", lambda: s)
    out = tmp_path / "taxon_status.parquet"
    assert main(["--pool", str(tmp_path / "pool.parquet"), "--out", str(out)]) == 0
    df = pd.read_parquet(out)
    assert sorted(df["taxon_id"]) == sorted(pool["taxon_id"].dropna().unique())


def test_table_names_no_arm(tmp_path):
    path = tmp_path / "s.parquet"
    update_status(path, [10, 11, 12], session=FakeSession(), sleep=0, today="2026-11-01")
    df = pd.read_parquet(path)
    cells = {str(v) for v in df.to_numpy().ravel()} | set(df.columns)
    assert not cells & set(ARMS)
