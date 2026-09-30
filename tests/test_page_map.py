import gzip
import json
import re

import numpy as np
import pandas as pd
import pytest

from what_to_id.batches import MAX_URL_LEN
from what_to_id.inat import BC_PLACE_ID
from what_to_id.page import ARM_WORDS
from what_to_id.page_map import (
    BYTES_PER_RECORD,
    IMPRECISE_M,
    MAP_NAME,
    NO_DAY,
    TAXA_NAME,
    TOTAL_ONLY,
    align_totals,
    decode_points,
    encode_points,
    fetch_totals,
    main,
    over_totals,
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
    assert json.loads(gzip.decompress(blobs[TAXA_NAME])) == [
        ["Acer", "", 3],
        ["Alnus", "alders", 4],
    ]
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
    assert "18*n" in html and ">2026-09-28</time>" in html


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


def test_taxa_file_carries_ids_as_steps_and_decode_restores_them():
    pool = make_pool(4)
    pool["taxon_id"] = pd.array([1700000, 3, 1700000, None], dtype="Int64")
    pool["taxon_name"] = ["Alnus", "Acer", "Alnus", None]
    blobs, meta = encode_points(pool)
    assert json.loads(gzip.decompress(blobs[TAXA_NAME])) == [
        ["Acer", "", 3],
        ["Alnus", "", 1699997],
    ]
    back = decode_points(blobs, meta)
    assert back["taxon_id"].iloc[:3].tolist() == [1700000, 3, 1700000]
    assert back["taxon_id"].isna().tolist() == [False, False, False, True]


def test_page_passes_the_place_and_url_limit_and_has_the_identify_link():
    _, meta = encode_points(make_pool(20))
    html = render_map(meta, freeze=None)
    page_meta = json.loads(re.search(r"var META=(\{.*?\});var BASEMAPS", html).group(1))
    assert page_meta["place_id"] == BC_PLACE_ID and page_meta["max_url"] == MAX_URL_LEN
    assert page_meta["imprecise_m"] == IMPRECISE_M
    assert f"place_id={BC_PLACE_ID}" in html
    assert 'id="identify"' in html and 'rel="noopener"' in html
    assert "function identifyUrl(" in html
    assert "https://www.inaturalist.org/observations/identify?" in html
    for key in ("quality_grade", "iconic_taxa", "created_d1", "taxon_id", "month"):
        assert key in html
    assert "place_id=7085" not in re.search(r"<script>var META.*", html, re.S).group(0)


def test_page_carries_the_update_date_for_the_age_check():
    _, meta = encode_points(make_pool(20))
    html = render_map(meta, freeze="2026-09-30")
    assert '<time id="updated" datetime="2026-09-30" title="2026-09-30">2026-09-30</time>' in html
    assert "STALE_DAYS" in html
    assert 'id="updated"' not in render_map(meta, freeze=None).split("<script>")[0]


def test_records_before_1900_sit_at_the_floor_and_are_marked():
    pool = make_pool(50)
    pool.loc[0, "observed_on"] = "1850-06-01"
    blobs, meta = encode_points(pool)
    assert meta["day0"] == "1900-01-01"
    back = decode_points(blobs, meta)
    assert len(back) == len(pool)
    old = back[back["id"] == pool.loc[0, "id"]].iloc[0]
    assert old["observed_on"] == pd.Timestamp("1900-01-01") and old["observed_before_1900"]
    assert back["observed_before_1900"].sum() == 1
    assert not back["uploaded_before_1900"].any()


def test_normal_pool_keeps_its_own_day0_and_no_marks():
    blobs, meta = encode_points(make_pool(50))
    assert meta["day0"] > "1900-01-01"
    back = decode_points(blobs, meta)
    assert not back["observed_before_1900"].any()


class _Hist:
    """A stand-in session answering iNaturalist histogram requests from a table."""

    def __init__(self, table):
        self.table, self.calls = table, []

    def get(self, url, params, timeout):
        self.calls.append((url, params))
        flag = next((k for k, v in TOTAL_ONLY.items() if v.items() <= params.items()), None)
        months = self.table.get((params["date_field"], params["iconic_taxa"], flag), {})

        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"results": {"month": months}}

        return R()


def test_fetch_totals_asks_once_per_group_date_and_status_filter():
    s = _Hist(
        {
            ("observed", "Aves", None): {"2026-08-01": 7},
            ("created", "unknown", None): {"2026-09-01": 2},
            ("observed", "Aves", "threatened"): {"2026-08-01": 1},
        }
    )
    t = fetch_totals(["Aves", "Unknown"], on="2026-09-30", session=s, sleep=0)
    assert len(s.calls) == 4 * (1 + len(TOTAL_ONLY))
    assert all(u.endswith("/observations/histogram") for u, _ in s.calls)
    p = s.calls[0][1]
    assert p["quality_grade"] == "needs_id,research" and p["photos"] == "true"
    assert p["place_id"] == BC_PLACE_ID and p["interval"] == "month"
    assert t == {
        "on": "2026-09-30",
        "obs": {"Aves": {"2026-08": 7}, "Unknown": {}},
        "up": {"Aves": {}, "Unknown": {"2026-09": 2}},
        "only": {
            "introduced": {"obs": {"Aves": {}, "Unknown": {}}, "up": {"Aves": {}, "Unknown": {}}},
            "threatened": {
                "obs": {"Aves": {"2026-08": 1}, "Unknown": {}},
                "up": {"Aves": {}, "Unknown": {}},
            },
            "exact": {"obs": {"Aves": {}, "Unknown": {}}, "up": {"Aves": {}, "Unknown": {}}},
        },
    }
    exact = [p for _, p in s.calls if "obscuration" in p]
    assert exact and exact[0]["obscuration"] == "none" and exact[0]["acc_below_or_unknown"] == 1001


def test_align_totals_folds_early_months_and_drops_late_ones():
    meta = {"day0": "2026-08-15", "days": 40, "groups": ["Aves", "Fungi"]}
    raw = {
        "on": "2026-09-30",
        "obs": {"Aves": {"2020-01": 3, "2026-08": 5, "2026-09": 4, "2026-11": 9}},
        "up": {"Fungi": {"2026-09": 1}},
    }
    t = align_totals(raw, meta)
    assert t["m0"] == "2026-08" and t["on"] == "2026-09-30"
    assert t["obs"] == [[8, 4], [0, 0]]
    assert t["up"] == [[0, 0], [0, 1]]
    assert t["only"] == {}
    raw["only"] = {"threatened": {"obs": {"Aves": {"2026-09": 1}}, "up": {}}}
    assert align_totals(raw, meta)["only"] == {
        "threatened": {"obs": [[0, 1], [0, 0]], "up": [[0, 0], [0, 0]]}
    }


def test_over_totals_counts_months_the_pool_exceeds():
    pool = make_pool(30)
    _, meta = encode_points(pool)
    big = {g: {"2026-08": 10**6, "2026-09": 10**6} for g in meta["groups"]}
    meta["totals"] = align_totals({"on": "x", "obs": big, "up": big}, meta)
    assert over_totals(pool, meta) == 0
    meta["totals"] = align_totals({"on": "x", "obs": {}, "up": big}, meta)
    assert over_totals(pool, meta) > 0


def test_page_carries_totals_only_when_given(tmp_path):
    pool = make_pool(20)
    write_map(tmp_path / "a", pool)
    html = (tmp_path / "a" / MAP_NAME).read_text()
    assert '"totals"' not in re.search(r"var META=(\{.*?\});var BASEMAPS", html).group(1)
    groups = sorted(pool["iconic_taxon"].unique())
    raw = {"on": "2026-09-30", "obs": {g: {"2026-08": 50} for g in groups}, "up": {}}
    write_map(tmp_path / "b", pool, totals=raw)
    html = (tmp_path / "b" / MAP_NAME).read_text()
    meta = json.loads(re.search(r"var META=(\{.*?\});var BASEMAPS", html).group(1))
    assert meta["totals"]["on"] == "2026-09-30" and len(meta["totals"]["obs"]) == len(groups)
    assert 'id="share"' in html and 'id="hint"' in html
    assert not [w for w in ARM_WORDS if w in html.lower()]


def test_cli_builds_without_totals_when_the_fetch_fails(tmp_path, monkeypatch):
    import requests

    import what_to_id.page_map as pm

    def boom(*a, **k):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(pm, "fetch_totals", boom)
    make_pool(20).to_parquet(tmp_path / "pool.parquet", index=False)
    assert main(["--pool", str(tmp_path / "pool.parquet"), "--out", str(tmp_path), "--totals"]) == 0
    assert '"totals"' not in (tmp_path / MAP_NAME).read_text()
