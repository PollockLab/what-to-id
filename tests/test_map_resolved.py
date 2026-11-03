"""The log of records that left needs-ID and the site file built from it (map_resolved.py)."""

import gzip
import json

import numpy as np
import pandas as pd
import pytest

from what_to_id import map_resolved as mr
from what_to_id.page_map import NO_DAY, encode_points
from what_to_id.taxonomy import NO_TAXON

from .embeddings_fixture import TREE, pool_frame

NOW = pd.Timestamp("2026-11-03T15:00:00Z")
DAY1900 = (pd.Timestamp("2026-11-03") - pd.Timestamp("1900-01-01")).days


def log_frame(ids, ago, **over):
    """Log rows for ids, each having left ``ago`` days before NOW (one value per id)."""
    df = pool_frame(ids)
    df["left"] = pd.Series(
        [NOW - pd.Timedelta(days=d, hours=1) for d in ago], dtype="datetime64[ns, UTC]"
    )
    df["reason"] = np.array([1] * len(ids), dtype="uint8")
    for k, v in over.items():
        df[k] = v
    return df


def test_left_rows_are_the_ids_before_minus_after_with_a_reason_each():
    before, after = pool_frame(range(1, 8)), pool_frame([1, 2, 5])
    grades = {3: "research", 4: "casual", 6: "needs_id"}
    got = mr.left_rows(before, after, grades, NOW)
    assert got["id"].tolist() == [3, 4, 6, 7]
    assert got["reason"].tolist() == [1, 2, 3, 4] and got["reason"].dtype == "uint8"
    assert (got["left"] == NOW).all() and list(got.columns)[-2:] == ["left", "reason"]
    assert mr.left_rows(before, before, {}, NOW).empty


def test_append_log_starts_the_file_dedupes_prunes_and_drops_returned(tmp_path):
    path = tmp_path / "resolved.parquet"
    first = mr.append_log(path, log_frame([1, 2], [0, 59]), pool_frame([9])["id"], NOW)
    assert first["id"].tolist() == [1, 2]
    first.to_parquet(path, index=False)
    again = log_frame([2, 3, 4, 5], [0, 1, 61, 2], reason=[3, 1, 1, 1])
    log = mr.append_log(path, again, pd.Series([5]), NOW)
    # 2 keeps its newest row, 4 is older than 60 days, 5 is back in the pool
    assert sorted(log["id"]) == [1, 2, 3]
    assert log.set_index("id").loc[2, "reason"] == 3
    nothing = mr.append_log(tmp_path / "none", log_frame([], []), pd.Series([], dtype="int64"), NOW)
    assert nothing.empty


def decoded(log, pool=None, tree=TREE, days=30):
    pool = pool_frame(range(100, 103)) if pool is None else pool
    return mr.decode_left(mr.encode_left(log, pool, tree, NOW, days=days))


def test_encode_then_decode_gives_back_positions_days_reasons_and_the_window():
    log = log_frame([5, 3, 4], [0, 10, 40], reason=[1, 2, 3])
    log.loc[log["id"] == 5, ["lat", "lon"]] = [48.5, -123.25]
    got = decoded(log)
    assert got["build"] == DAY1900 and got["start"] == DAY1900 - 40
    assert got["id"].tolist() == [3, 5]  # sorted; the 40-day-old one is outside the file
    assert got["reason"].tolist() == [2, 1]
    assert got["left"].tolist() == [DAY1900 - 10, DAY1900]
    assert got["lat"][1] == np.float32(48.5) and got["lon"][1] == np.float32(-123.25)
    row = log[log["id"] == 3].iloc[0]
    assert got["obs"][0] == (pd.Timestamp(row["observed_on"]) - pd.Timestamp("1900-01-01")).days


def test_taxa_and_groups_index_the_pages_tables_with_an_ancestor_for_a_taxon_the_pool_lacks():
    pool = pool_frame(range(1, 4))  # taxa 1000-1002 (Genus A), groups Aves, Insecta, Plantae
    blobs, meta = encode_points(pool, TREE)
    rows = json.loads(gzip.decompress(blobs["pool-taxa.bin"]))
    row = {r[2]: i for i, r in enumerate(rows)}
    log = log_frame([10, 11, 12], [0, 0, 0], taxon_id=[1001, 1004, 77])
    log["iconic_taxon"] = ["Plantae", "Aves", "Insecta"]
    got = decoded(log, pool)
    # 1004 is not in the pool; its genus is not either, its family is
    assert got["taxon"].tolist() == [row[1001], row[800], NO_TAXON]
    assert [meta["groups"][g] for g in got["group"]] == ["Plantae", "Aves", "Insecta"]


def test_records_of_a_group_the_pool_lacks_or_back_in_the_pool_are_left_out():
    log = log_frame([10, 11, 100], [0, 0, 0])
    log.loc[log["id"] == 11, "iconic_taxon"] = "Fungi"
    assert decoded(log)["id"].tolist() == [10]  # 100 is in the pool again; Fungi has no index


def test_no_log_or_an_empty_one_gives_a_header_only_file():
    for log in (None, log_frame([], [])):
        got = decoded(log)
        assert got["id"].size == 0 and got["start"] == got["build"] == DAY1900


def test_missing_dates_and_early_dates_are_marked():
    log = log_frame([1, 2], [0, 0])
    log["observed_on"] = [None, "1850-03-04"]
    got = decoded(log)
    assert got["obs"].tolist() == [NO_DAY, 0] and got["flags"][1] & 16 and not got["flags"][0] & 16


def test_decode_rejects_a_truncated_file():
    with pytest.raises(ValueError, match="pool-resolved.bin"):
        mr.decode_left(gzip.compress(b"\0" * 9))


def test_check_matches_the_log_with_the_pool_diff_and_the_site_file():
    before, after = pool_frame(range(1, 101)), pool_frame(range(1, 96))
    since = NOW - pd.Timedelta(hours=6)
    log = log_frame(range(96, 101), [0] * 5)
    site = mr.encode_left(log, after, TREE, NOW)
    ok = mr.check(before, after, log, since, site)
    assert ok["pool_ok"] and ok["site_ok"] and ok["site_7d"] == 5 and ok["ratio"] == 1
    # a record the log missed, and one it logged that was never in the first snapshot
    assert not mr.check(before, pool_frame(range(1, 95)), log, since)["pool_ok"]
    extra = pd.concat([log, log_frame([500], [0])])
    assert mr.check(before, after, extra, since)["ratio"] == 1.2
    assert mr.check(before, after, extra, since)["pool_ok"] is False
    assert mr.check(before, before, log.iloc[:0], since)["pool_ok"]


def test_build_command_writes_a_file_decode_reads_back(tmp_path):
    pool, log = tmp_path / "pool.parquet", tmp_path / "resolved.parquet"
    pool_frame(range(100, 103)).to_parquet(pool, index=False)
    out = tmp_path / "site"
    argv = ["build", "--log", str(log), "--pool", str(pool), "--out", str(out)]
    assert mr.main(argv) == 0  # no log yet
    assert mr.decode_left((out / mr.NAME).read_bytes())["id"].size == 0
    log_frame([1, 2, 3], [0, 3, 8]).to_parquet(log, index=False)
    assert mr.main(argv) == 0
    got = mr.decode_left((out / mr.NAME).read_bytes())
    assert got["id"].tolist() == [1, 2, 3] and got["reason"].tolist() == [1, 1, 1]
