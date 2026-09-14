import pandas as pd
import pytest

from what_to_id import inat


def _obs(i, **over):
    base = {
        "id": i,
        "created_at": "2026-06-01T10:00:00-07:00",
        "observed_on": "2026-05-31",
        "geojson": {"type": "Point", "coordinates": [-123.1, 49.3]},
        "taxon": {
            "id": 47126,
            "name": "Plantae",
            "rank": "kingdom",
            "iconic_taxon_name": "Plantae",
        },
        "user": {"id": 42},
        "identifications_count": 1,
        "num_identification_agreements": 0,
        "photos": [{"url": "https://static.inaturalist.org/photos/1/square.jpg"}],
    }
    base.update(over)
    return base


class FakeResponse:
    def __init__(self, results):
        self._results = results

    def raise_for_status(self):
        pass

    def json(self):
        return {"results": self._results}


class FakeSession:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(dict(params))
        return FakeResponse(self.pages.pop(0) if self.pages else [])


def test_flatten_row():
    row = inat.flatten(_obs(7))
    assert row is not None
    assert list(row) == list(inat.COLUMNS)
    assert row["id"] == 7
    assert row["lon"] == -123.1 and row["lat"] == 49.3
    assert row["photo_url"] == "https://static.inaturalist.org/photos/1/medium.jpg"
    assert row["iconic_taxon"] == "Plantae"
    assert row["taxon_id"] == 47126
    assert row["user_id"] == 42
    assert row["ident_count"] == 1 and row["agree"] == 0


def test_flatten_missing_geojson_or_photos():
    assert inat.flatten(_obs(1, geojson=None)) is None
    assert inat.flatten(_obs(2, photos=[])) is None
    assert inat.flatten(_obs(3, geojson={"coordinates": []})) is None


def test_flatten_defaults():
    row = inat.flatten(_obs(4, taxon=None, user=None, identifications_count=None, observed_on=None))
    assert row["taxon_id"] is None and row["taxon_name"] is None and row["rank"] is None
    assert row["user_id"] is None
    assert row["ident_count"] == 0
    assert row["observed_on"] is None


def test_pool_params():
    p = inat.pool_params("Aves", d1="2025-01-01", freeze="2026-09-11")
    assert p["place_id"] == inat.BC_PLACE_ID
    assert p["quality_grade"] == "needs_id"
    assert p["iconic_taxa"] == "Aves"
    assert p["created_d2"] == "2026-09-11"
    assert p["order"] == "desc" and p["order_by"] == "id"


def test_pool_params_quality():
    p = inat.pool_params("Aves", d1="2025-01-01", freeze="2026-09-11", quality="research")
    assert p["quality_grade"] == "research"
    with pytest.raises(ValueError, match="quality"):
        inat.pool_params("Aves", d1="2025-01-01", freeze="2026-09-11", quality="casual")


@pytest.mark.parametrize("bad", ["2025-1-1", "20250101", "", None, 20250101])
def test_pool_params_rejects_bad_dates(bad):
    with pytest.raises(ValueError):
        inat.pool_params("Aves", d1=bad, freeze="2026-09-11")
    with pytest.raises(ValueError):
        inat.pool_params("Aves", d1="2025-01-01", freeze=bad)


def test_pull_group_id_below_and_short_page_stop():
    full = [_obs(1000 - k) for k in range(inat.PER_PAGE)]
    short = [_obs(500), _obs(499)]
    sess = FakeSession([full, short, [_obs(1)]])
    logs = []
    df = inat.pull_group(
        "Aves", d1="2025-01-01", freeze="2026-09-11", session=sess, sleep=0, log=logs.append
    )
    assert len(sess.calls) == 2
    assert "id_below" not in sess.calls[0]
    assert sess.calls[1]["id_below"] == full[-1]["id"]
    assert len(df) == inat.PER_PAGE + 2
    assert df["id"].dtype == "int64"
    assert str(df["taxon_id"].dtype) == "Int64"
    assert str(df["user_id"].dtype) == "Int64"
    assert df["lat"].dtype == "float64"
    assert len(logs) == 2


def test_pull_group_cap_pages():
    pages = [[_obs(1000 - k - 200 * p) for k in range(inat.PER_PAGE)] for p in range(3)]
    sess = FakeSession(pages)
    df = inat.pull_group(
        "Aves",
        d1="2025-01-01",
        freeze="2026-09-11",
        session=sess,
        cap_pages=2,
        sleep=0,
        log=lambda _: None,
    )
    assert len(sess.calls) == 2
    assert len(df) == 2 * inat.PER_PAGE


def test_pull_group_empty():
    sess = FakeSession([[]])
    df = inat.pull_group(
        "Aves", d1="2025-01-01", freeze="2026-09-11", session=sess, sleep=0, log=lambda _: None
    )
    assert df.empty
    assert list(df.columns) == list(inat.COLUMNS)
    assert df["id"].dtype == "int64"
    assert str(df["taxon_id"].dtype) == "Int64"


def test_pull_pool_dedupes_and_writes(tmp_path):
    sess = FakeSession([[_obs(5), _obs(6)], [_obs(6), _obs(7)]])
    out = tmp_path / "pool.parquet"
    df = inat.pull_pool(
        ["Aves", "Insecta"],
        d1="2025-01-01",
        freeze="2026-09-11",
        out=out,
        session=sess,
        sleep=0,
        log=lambda _: None,
    )
    assert sorted(df["id"]) == [5, 6, 7]
    back = inat.load_pool(out)
    assert len(back) == 3


class FlakySession(FakeSession):
    """Serves its pages, then fails the way a dropped connection would."""

    def get(self, url, params=None, timeout=None):
        if not self.pages:
            raise inat.requests.ConnectionError("dropped")
        return super().get(url, params=params, timeout=timeout)


def _pool(out, sess, groups=("Aves", "Insecta"), **over):
    kw = {"d1": "2025-01-01", "freeze": "2026-09-11", "out": out, "session": sess, "sleep": 0}
    kw.update(over)
    return inat.pull_pool(list(groups), log=lambda _: None, **kw)


def test_pull_pool_resumes_after_failure(tmp_path):
    out = tmp_path / "pool.parquet"
    with pytest.raises(inat.requests.ConnectionError):
        _pool(out, FlakySession([[_obs(5), _obs(6)]]))
    assert not out.exists()
    assert (tmp_path / "pool.parquet.parts" / "Aves.parquet").exists()
    sess = FakeSession([[_obs(7)]])
    df = _pool(out, sess)
    assert [c["iconic_taxa"] for c in sess.calls] == ["Insecta"]
    assert sorted(df["id"]) == [5, 6, 7]
    assert str(df["taxon_id"].dtype) == "Int64"
    assert not (tmp_path / "pool.parquet.parts").exists()


def test_pull_pool_refuses_mismatched_resume(tmp_path):
    out = tmp_path / "pool.parquet"
    with pytest.raises(inat.requests.ConnectionError):
        _pool(out, FlakySession([[_obs(5)]]))
    with pytest.raises(ValueError, match="remove it first"):
        _pool(out, FakeSession([]), freeze="2026-10-15")


def test_make_session_retries_transient_errors():
    retry = inat.make_session().get_adapter(inat.INAT).max_retries
    assert retry.total == inat.RETRIES
    assert set(retry.status_forcelist) == {429, 500, 502, 503, 504}


def test_load_pool_missing_columns(tmp_path):
    p = tmp_path / "bad.parquet"
    pd.DataFrame({"id": [1], "lat": [0.0]}).to_parquet(p)
    with pytest.raises(ValueError, match="photo_url"):
        inat.load_pool(p)


def test_pool_params_created_d1():
    p = inat.pool_params("Aves", d1="2025-01-01", freeze="2026-09-11", created_d1="2026-09-10")
    assert p["created_d1"] == "2026-09-10"
    p_default = inat.pool_params("Aves", d1="2025-01-01", freeze="2026-09-11")
    assert "created_d1" not in p_default


def test_pool_params_created_d1_accepts_timestamp():
    ts = pd.Timestamp("2026-09-10T08:00:00", tz="UTC")
    p = inat.pool_params("Aves", d1="2025-01-01", freeze="2026-09-11", created_d1=ts)
    assert p["created_d1"] == ts.isoformat()


def test_pool_params_rejects_bad_created_d1():
    with pytest.raises(ValueError, match="created_d1"):
        inat.pool_params("Aves", d1="2025-01-01", freeze="2026-09-11", created_d1="not-a-date")


def test_pull_group_passes_created_d1():
    sess = FakeSession([[]])
    inat.pull_group(
        "Aves",
        d1="2025-01-01",
        freeze="2026-09-11",
        session=sess,
        sleep=0,
        log=lambda _: None,
        created_d1="2026-09-10",
    )
    assert sess.calls[0]["created_d1"] == "2026-09-10"


def test_pull_pool_passes_created_d1(tmp_path):
    sess = FakeSession([[_obs(5)], []])
    out = tmp_path / "pool.parquet"
    inat.pull_pool(
        ["Aves"],
        d1="2025-01-01",
        freeze="2026-09-11",
        out=out,
        session=sess,
        sleep=0,
        log=lambda _: None,
        created_d1="2026-09-10",
    )
    assert all(c["created_d1"] == "2026-09-10" for c in sess.calls)


def test_fetch_by_ids_chunks():
    sess = FakeSession([[_obs(1)], [_obs(2)]])
    res = inat.fetch_by_ids([1, 2, 3], session=sess, chunk=2, sleep=0)
    assert [o["id"] for o in res] == [1, 2]
    assert sess.calls[0]["id"] == "1,2" and sess.calls[1]["id"] == "3"
    with pytest.raises(ValueError):
        inat.fetch_by_ids([1], session=sess, chunk=201)


def test_still_open_chunks_and_returns_ids():
    ids = list(range(1, 451))  # 450 ids -> 3 chunks of <=200
    pages = [
        [_obs(i) for i in ids[0:200:20]],  # subset "still open" from chunk 1
        [_obs(i) for i in ids[200:400:20]],  # subset from chunk 2
        [],  # nothing open in the last, short chunk
    ]
    sess = FakeSession(pages)
    result = inat.still_open(ids, session=sess)
    assert len(sess.calls) == 3
    assert [len(c["id"].split(",")) for c in sess.calls] == [200, 200, 50]
    assert all(c["quality_grade"] == "needs_id" for c in sess.calls)
    assert all(c["photos"] == "true" for c in sess.calls)
    assert all(c["place_id"] == inat.BC_PLACE_ID for c in sess.calls)
    expected = set(ids[0:200:20]) | set(ids[200:400:20])
    assert result == expected


def test_still_open_dedupes_and_casts_ids():
    sess = FakeSession([[_obs(1)]])
    result = inat.still_open(["1", 1, 2.0], session=sess)
    assert len(sess.calls) == 1
    assert sess.calls[0]["id"] == "1,2"
    assert result == {1}


def test_still_open_empty_input_makes_no_request():
    sess = FakeSession([[_obs(1)]])
    assert inat.still_open([], session=sess) == set()
    assert sess.calls == []


@pytest.mark.network
def test_pull_amphibia_one_page_live():
    df = inat.pull_group(
        "Amphibia", d1="2025-01-01", freeze="2026-09-11", cap_pages=1, log=lambda _: None
    )
    assert list(df.columns) == list(inat.COLUMNS)
    assert not df.empty
    assert df["photo_url"].str.contains("/medium.").all()
    print(f"\nlive rows: {len(df)}")
