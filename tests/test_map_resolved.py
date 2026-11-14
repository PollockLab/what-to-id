"""The log of records that left needs-ID and the site file built from it (map_resolved.py)."""

import gzip
import json

import numpy as np
import pandas as pd
import pytest

from what_to_id import map_resolved as mr
from what_to_id import site_files
from what_to_id.inat import COLUMNS, EXTRA_COLUMNS
from what_to_id.map_points import NO_DAY, encode_points
from what_to_id.page_map import write_map
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
    rows = json.loads(gzip.decompress(blobs[meta["taxa"]]))
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
    write_map(out, pool_frame(range(100, 103)))
    argv = ["build", "--log", str(log), "--pool", str(pool), "--out", str(out)]
    assert mr.main(argv) == 0  # no log yet
    assert mr.decode_left(site_files.path(out, "resolved").read_bytes())["id"].size == 0
    log_frame([1, 2, 3], [0, 3, 8]).to_parquet(log, index=False)
    assert mr.main(argv) == 0
    got = mr.decode_left(site_files.path(out, "resolved").read_bytes())
    assert got["id"].tolist() == [1, 2, 3] and got["reason"].tolist() == [1, 1, 1]


def ident(uid, taxon, at, ancestors=(), **kw):
    t = {"id": taxon, "ancestor_ids": [*ancestors, taxon]}
    return {"user": {"id": uid}, "taxon": t, "created_at": at, "current": True, **kw}


def obs(oid, ids, created="2026-10-01T00:00:00Z", ct=10, **kw):
    return {
        "id": oid, "created_at": created, "observed_on": "2026-10-01", "community_taxon_id": ct,
        "taxon": {"id": ct, "rank": "species", "name": "x", "iconic_taxon_name": "Aves"},
        "geojson": {"coordinates": [-123.0, 49.0]}, "photos": [{"url": "u/square.jpg"}],
        "user": {"id": 1}, "identifications": ids, **kw,
    }  # fmt: skip


def test_research_time_is_the_second_agreeing_identification_unless_others_disagree():
    ids = [ident(1, 10, "2026-10-05T00:00:00Z"), ident(2, 10, "2026-10-06T00:00:00Z")]
    assert mr.research_time(obs(1, ids)) == pd.Timestamp("2026-10-06T00:00:00Z")
    assert mr.research_time(obs(1, ids[:1])) is None
    # one dissenter keeps 2 of 3 from passing 2/3; a third agreeing one makes 3 of 4
    no = ident(3, 99, "2026-10-05T12:00:00Z")
    assert mr.research_time(obs(1, [*ids, no])) is None
    more = ident(4, 10, "2026-10-07T00:00:00Z")
    assert mr.research_time(obs(1, [*ids, no, more])) == pd.Timestamp("2026-10-07T00:00:00Z")
    # an ancestor or a descendant of the community taxon is not a dissent
    deep = [ident(u, 10, f"2026-10-0{u + 4}T00:00:00Z", ancestors=(5,)) for u in (1, 2)]
    anc = ident(3, 5, "2026-10-05T12:00:00Z")
    assert mr.research_time(obs(1, [*deep, anc])) == pd.Timestamp("2026-10-06T00:00:00Z")
    assert mr.research_time(obs(1, [], ct=None, taxon=None)) is None


def test_a_taxon_swap_is_dated_by_the_identification_it_replaced():
    old = ident(2, 10, "2026-10-06T00:00:00Z", current=False)
    ids = [
        ident(1, 10, "2026-10-20T00:00:00Z", taxon_change={"id": 7}),
        ident(2, 10, "2026-10-20T00:00:01Z", taxon_change={"id": 7}),
        ident(1, 10, "2026-10-05T00:00:00Z", current=False),
        old,
    ]
    assert mr.research_time(obs(1, ids)) == pd.Timestamp("2026-10-06T00:00:00Z")


RUNS = pd.DatetimeIndex(
    pd.to_datetime(["2026-10-10T00:00Z", "2026-10-11T00:00Z", "2026-10-12T00:00Z"])
)


def at(day, hour=6):
    return [ident(1, 10, f"2026-10-{day}T01:00:00Z"), ident(2, 10, f"2026-10-{day}T0{hour}:00:00Z")]


def test_backfill_stamps_the_run_whose_window_holds_the_time_and_skips_the_rest():
    since = pd.Timestamp("2026-10-01T00:00Z")
    rows = [
        obs(1, at(10)),  # in (10-10, 10-11] -> left 10-11
        obs(2, at(11)),  # 10-11 06:00 -> left 10-12
        obs(3, at(9)),  # before the first run: no window start
        obs(4, at(12)),  # after the last run: the live log has it
        obs(5, at(11), created="2026-10-11T03:00:00Z"),  # uploaded inside the window
        obs(6, at(10), geojson=None),  # no coordinates
        obs(7, [ident(1, 10, "2026-10-10T05:00:00Z")]),  # no consensus
    ]
    got = mr.backfill_rows(rows, RUNS, since)
    assert got["id"].tolist() == [1, 2]
    assert got["left"].tolist() == [RUNS[1], RUNS[2]] and got["reason"].tolist() == [5, 5]
    assert got["reason"].dtype == "uint8" and got["photo_url"][0] == "u/medium.jpg"
    assert mr.backfill_rows(rows, RUNS, pd.Timestamp("2026-10-10T12:00Z"))["id"].tolist() == [2]
    empty = mr.backfill_rows([], RUNS, since)
    assert empty.empty and "left" in empty and list(empty.columns) == list(got.columns)


def test_merge_puts_live_rows_over_backfill_and_leaves_out_the_pool(tmp_path):
    path = tmp_path / "resolved.parquet"
    back = mr.backfill_rows(
        [obs(i, at(10)) for i in (1, 2, 3)], RUNS, pd.Timestamp("2026-10-01T00:00Z")
    )
    live = log_frame([2, 8], [0, 0], reason=[3, 2])
    now = RUNS[2] + pd.Timedelta(days=1)
    only = mr.merge_backfill(back, path, pd.Series([3]), now)
    assert only["id"].tolist() == [1, 2]  # 3 is back in the pool
    live.to_parquet(path, index=False)
    got = mr.merge_backfill(back, path, pd.Series([3]), RUNS[2] + pd.Timedelta(days=61)).set_index(
        "id"
    )
    assert sorted(got.index) == [2, 8]  # the backfilled rows are past the 60-day keep
    got = mr.merge_backfill(back, path, pd.Series([3]), now).set_index("id")
    assert sorted(got.index) == [1, 2, 8] and got.loc[2, "reason"] == 3
    assert list(back.columns) == [*COLUMNS, *EXTRA_COLUMNS, "left", "reason"]  # the pool's


def test_live_day_is_the_oldest_row_that_was_not_backfilled_and_start_when_none():
    log = log_frame([10, 11, 12], [20, 5, 3], reason=[5, 5, 1])  # a live Research Grade row counts
    assert decoded(log)["live"] == DAY1900 - 3 and decoded(log)["start"] == DAY1900 - 20
    assert decoded(log.assign(reason=np.uint8(1)))["live"] == DAY1900 - 20
    assert decoded(log.assign(reason=np.uint8(5)))["live"] == DAY1900 - 20
    assert decoded(None)["live"] == DAY1900


def test_fetch_pages_by_id_below_until_a_short_page():
    calls = []
    pages = [[{"id": i} for i in range(400, 200, -1)], [{"id": 5}]]

    def fetch(p):
        calls.append(p.get("id_below"))
        return pages[len(calls) - 1]

    got = list(mr.fetch_research(pd.Timestamp("2026-10-01T00:00Z"), "1900-01-01", fetch, sleep=0))
    assert len(got) == 201 and calls == [None, 201]


def test_read_runs_takes_gh_json_or_lines():
    j = json.dumps(
        [
            {"createdAt": "2026-10-11T00:00:00Z", "conclusion": "success"},
            {"createdAt": "2026-10-09T00:00:00Z"},
            {"createdAt": "2026-10-10T00:00:00Z", "conclusion": "cancelled"},
        ]
    )
    assert mr.read_runs(j).tolist() == [
        pd.Timestamp("2026-10-09T00:00Z"),
        pd.Timestamp("2026-10-11T00:00Z"),
    ]
    assert len(mr.read_runs("2026-10-11T00:00:00Z\n2026-10-10T00:00:00Z\n")) == 2


def test_backfill_command_writes_the_merged_log(tmp_path, monkeypatch):
    pool = tmp_path / "pool.parquet"
    pool_frame(range(100, 103)).to_parquet(pool, index=False)
    day = pd.Timestamp.now("UTC").normalize() - pd.Timedelta(days=3)  # inside the keep window
    runs = tmp_path / "runs.txt"
    runs.write_text("\n".join(str(day + pd.Timedelta(days=i)) for i in range(3)))
    t = [ident(u, 10, str(day + pd.Timedelta(hours=h))) for u, h in ((1, 25), (2, 26))]
    seen = []
    monkeypatch.setattr(mr, "fetch_research", lambda *a: seen.append(a) or [obs(1, t), obs(100, t)])
    out = tmp_path / "merged.parquet"
    argv = ["backfill", "--log", str(tmp_path / "none"), "--pool", str(pool), "--runs", str(runs)]
    assert mr.main([*argv, "--since", str(day), "--out", str(out)]) == 0
    got = pd.read_parquet(out)
    assert got["id"].tolist() == [1]  # 100 is in the pool
    assert got["left"][0] == day + pd.Timedelta(days=2) and seen[0][0] == day


def test_backfill_from_saved_rows_merges_without_fetching(tmp_path, monkeypatch):
    monkeypatch.setattr(mr, "fetch_research", lambda *a: pytest.fail("fetched"))
    day = pd.Timestamp.now("UTC").normalize() - pd.Timedelta(days=3)
    saved = log_frame([1, 2], [2, 2], reason=5).assign(left=day)
    saved.to_parquet(tmp_path / "back.parquet", index=False)
    pool_frame([2]).to_parquet(tmp_path / "pool.parquet", index=False)
    out = tmp_path / "merged.parquet"
    argv = ["backfill", "--from", str(tmp_path / "back.parquet"), "--log", str(tmp_path / "none")]
    assert mr.main([*argv, "--pool", str(tmp_path / "pool.parquet"), "--out", str(out)]) == 0
    assert pd.read_parquet(out)["id"].tolist() == [1]  # 2 is in the pool
    with pytest.raises(SystemExit):
        mr.main(["backfill", "--log", "x", "--pool", "y", "--out", "z"])
