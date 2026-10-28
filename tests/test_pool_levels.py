"""pool-levels.bin and pool-levels-looks.bin: identify.parquet packed per pool record."""

import base64
import gzip
import json

import numpy as np
import pandas as pd
import pytest

from what_to_id import page_identify, pool_levels
from what_to_id.identify import IDENTIFY_COLUMNS
from what_to_id.page_map import decode_points, encode_points, render_map

from .embeddings_fixture import TREE, pool_frame

N = 300
LOOKS = ["Bombus a", "Bombus b", "Apis c"]


def write_site(tmp_path):
    ids = np.random.default_rng(4).choice(2**31, N, replace=False) + 1
    blobs, meta = encode_points(pool_frame(ids), TREE)
    site = tmp_path / "site"
    site.mkdir()
    for name, blob in blobs.items():
        (site / name).write_bytes(blob)
    (site / "map.html").write_text(render_map(meta, freeze=None))
    return site, decode_points(blobs, meta)


def scored_frame(points):
    """Every third pool record missing, one with a new label, levels cycling over 0 to 5."""
    rng = np.random.default_rng(6)
    df = pd.DataFrame(
        {
            "id": points["id"].to_numpy(np.int64),
            "taxon_id": points["taxon_id"].to_numpy(np.int64),
            "level": np.arange(N) // 3 % 6,
            "score": rng.normal(size=N).astype(np.float32),
            "score2": np.float32(0),
            "looks_like": pd.Series([LOOKS[i % 3] for i in range(N)], dtype="category"),
        }
    )
    df = df.drop(index=range(0, N, 3)).reset_index(drop=True)
    df.loc[1, "taxon_id"] += 1  # labelled differently now: its level no longer applies
    return df[list(IDENTIFY_COLUMNS)].astype({"level": "int8"})


def test_the_pack_round_trips_identify_parquet_in_shard_order(tmp_path):
    site, points = write_site(tmp_path)
    df = scored_frame(points)
    df.to_parquet(tmp_path / "identify.parquet")
    assert (
        pool_levels.main(["--out", str(site), "--parquet", str(tmp_path / "identify.parquet")]) == 0
    )
    level, q = pool_levels.unpack((site / pool_levels.OUT_NAME).read_bytes())
    looks = pool_levels.unpack_looks((site / pool_levels.LOOKS_NAME).read_bytes(), N)
    assert len(level) == len(q) == len(looks) == N
    row = df.set_index("id")
    for i, pid in enumerate(points["id"]):
        if pid not in row.index or (row.at[pid, "taxon_id"] != points["taxon_id"][i]):
            assert level[i] == 0 and q[i] == 0 and looks[i] is None  # missing or relabelled
            continue
        want = int(row.at[pid, "level"])
        assert level[i] == want
        assert looks[i] == (row.at[pid, "looks_like"] if want in (2, 3, 5) else None)
    assert (level == 0).sum() >= N // 3 + 1 and set(level) == {0, 1, 2, 3, 4, 5}


def test_the_score_steps_rank_within_a_level_and_weird_shows_the_lowest_first():
    level = np.array([1, 1, 1, 1, 4, 4, 4, 4, 0], np.int8)
    score = np.array([0.1, 0.4, 0.3, 0.2, 0.1, 0.4, 0.3, 0.2, np.nan], np.float32)
    got, q = pool_levels.unpack(pool_levels.pack(level, score))
    assert got.tolist() == level.tolist()
    assert q[:4].tolist() == [0, 12, 8, 4] and q[4:8].tolist() == [12, 0, 4, 8] and q[8] == 0


def test_a_build_without_a_table_says_so(tmp_path):
    site, _ = write_site(tmp_path)
    with pytest.raises(ValueError, match="--data-url or --parquet"):
        pool_levels.build(site)


def test_packing_nothing_and_a_record_without_levels():
    level, q = pool_levels.unpack(pool_levels.pack(np.zeros(0, np.int8), np.zeros(0, np.float32)))
    assert len(level) == len(q) == 0
    blob = pool_levels.pack_looks(np.zeros(3, np.int8), np.full(3, "x", dtype=object))
    assert pool_levels.unpack_looks(blob, 3) == [None] * 3


def test_three_million_records_fit_the_levels_budget():
    n = 3_100_000
    rng = np.random.default_rng(0)
    level = rng.choice([0, 1, 2, 3, 4], n, p=[0.3, 0.25, 0.1, 0.3, 0.05]).astype(np.int8)
    blob = pool_levels.pack(level, rng.normal(size=n).astype(np.float32))
    print(f"pool-levels.bin {len(blob) / 1e6:.2f} MB gzipped for {n} records")
    assert len(blob) <= 3_000_000
    assert len(gzip.decompress(blob)) == n
    # the look-alike names of levels 2 and 3, 8000 of them in a long tail: apart, as measured
    looks = np.array([f"S{k}" for k in range(8000)], dtype=object)
    weight = 1 / np.arange(1, 8001)
    lk = pool_levels.pack_looks(level, looks[rng.choice(8000, n, p=weight / weight.sum())])
    print(f"pool-levels-looks.bin {len(lk) / 1e6:.2f} MB gzipped")


def km_text(k):
    """The page's rounding (levels_app.js kmText): coarser farther out, half up as Math.round."""
    s = 100 if k >= 1000 else 50 if k >= 500 else 10
    return int(np.floor(k / s + 0.5) * s)


def test_the_km_byte_keeps_inside_near_far_and_the_rounding_the_page_shows():
    km = np.arange(0, 15_900, dtype=np.float64)
    back = pool_levels.okm_km(pool_levels.okm_code(km))
    assert (back[:50] == km[:50]).all()  # 0 inside, 1..49 just outside, as is
    assert ((back >= 50) == (km >= 50)).all()
    assert [km_text(b) for b in back[50:]] == [km_text(k) for k in km[50:]]
    code = pool_levels.okm_code(np.array([np.nan, 0, 49, 50, 499, 999, 1e6]))
    assert code.tolist() == [255, 0, 49, 50, 95, 105, 254]
    assert np.isnan(pool_levels.okm_km(code[:1])).all()


def range_tables():
    """Two square cells; Bombus a in cell 0, Apis c in both, Cus off the grid."""
    ranges = pd.DataFrame({"name": ["Bombus a", "Apis c", "Cus"], "cells": [[0], [0, 1], []]})
    grid = pd.DataFrame(
        {
            "lat": [np.float32([48, 48, 49.5, 49.5])] * 2,
            "lon": [np.float32([x, x + 1, x + 1, x]) for x in (-124, -123)],
        }
    )
    return ranges, grid


def test_the_range_file_round_trips_and_empty_and_unknown_stay_so():
    ranges, grid = range_tables()
    km = np.array([0, 12, 300, np.nan])
    note = np.array([None, "Range: fits the look-alike, not the label", None, None], dtype=object)
    head, back, notes = pool_levels.unpack_range(pool_levels.pack_range(km, note, ranges, grid), 4)
    assert back[:3].tolist() == [0, 12, 300] and np.isnan(back[3])
    assert notes == [None, note[1], None, None] and head["notes"] == [note[1]]
    assert head["names"] == ["Bombus a", "Apis c", "Cus"]
    assert head["grid"][1] == [-123000, 48000, -122000, 48000, -122000, 49500, -123000, 49500]
    bits = [base64.b64decode(r) for r in head["rng"]]
    assert bits == [b"\x01", b"\x03", b""]  # off the grid: known, with no cells
    head, back, notes = pool_levels.unpack_range(
        pool_levels.pack_range(np.zeros(0), np.zeros(0, object), ranges[:0], grid[:0]), 0
    )
    assert head == {"grid": [], "names": [], "rng": [], "notes": []} and len(back) == 0
    bad = ranges.assign(cells=[[0], [2], []])
    with pytest.raises(ValueError, match="outside the 2-cell grid"):
        pool_levels.pack_range(km, note, bad, grid)


def write_ranges(d, points):
    """level_ranges output for the site's records: km by position, a note on every fifth."""
    d.mkdir()
    ranges, grid = range_tables()
    ranges.to_parquet(d / "level-ranges.parquet")
    grid.to_parquet(d / "level-range-cells.parquet")
    n = len(points)
    pd.DataFrame(
        {
            "id": points["id"].to_numpy(np.int64),
            "range_note": [pool_levels_note(i) for i in range(n)],
            "lat": np.float32(49),
            "lon": np.float32(-123),
            "out_km": pd.array([None if i % 7 == 0 else i * 10 for i in range(n)], dtype="Int32"),
        }
    ).to_parquet(d / "range-notes.parquet")


def pool_levels_note(i):
    return "Range: outside both ranges" if i % 5 == 0 else None


def test_the_build_lines_the_ranges_up_with_the_site_and_skips_them_when_absent(tmp_path, capsys):
    site, points = write_site(tmp_path)
    df = scored_frame(points)
    df.to_parquet(tmp_path / "identify.parquet")
    args = ["--out", str(site), "--parquet", str(tmp_path / "identify.parquet")]
    assert pool_levels.main(args) == 0
    assert not (site / pool_levels.RANGE_NAME).exists()
    assert "no pool-levels-range.bin, so no range maps: no --ranges" in capsys.readouterr().err
    assert pool_levels.main([*args, "--ranges", str(tmp_path / "nowhere")]) == 0
    assert "could not read the range tables" in capsys.readouterr().err
    write_ranges(tmp_path / "ranges", points)
    assert pool_levels.main([*args, "--ranges", str(tmp_path / "ranges")]) == 0
    assert pool_levels.RANGE_NAME in capsys.readouterr().out
    head, km, notes = pool_levels.unpack_range((site / pool_levels.RANGE_NAME).read_bytes(), N)
    row = df.set_index("id")
    for i, pid in enumerate(points["id"]):
        if pid not in row.index or row.at[pid, "taxon_id"] != points["taxon_id"][i]:
            assert np.isnan(km[i]) and notes[i] is None  # missing or relabelled
            continue
        assert np.isnan(km[i]) if i % 7 == 0 else km[i] == km_text(i * 10)
        assert notes[i] == pool_levels_note(i)
    assert head["notes"] == ["Range: outside both ranges"]
    assert pool_levels.main(args) == 0  # a later build without ranges drops the stale file
    assert not (site / pool_levels.RANGE_NAME).exists()


def test_the_manifest_names_the_range_tables_or_the_levels_go_out_alone(tmp_path, monkeypatch):
    site, points = write_site(tmp_path)
    src = tmp_path / "atlas"
    write_ranges(src, points)
    scored_frame(points).to_parquet(src / "identify.parquet")
    entry = {"name": "identify.parquet", **{k: v for k, v in pool_levels.RANGE_FILES.items()}}
    manifest = {"identify": entry}
    monkeypatch.setattr(
        pool_levels,
        "_fetch",
        lambda url, path: path.write_bytes(
            json.dumps(manifest).encode()
            if url.endswith("manifest.json")
            else (src / url.rsplit("/", 1)[1]).read_bytes()
        ),
    )
    pool_levels.build(site, data_url="https://x/")
    assert pool_levels.unpack_range((site / pool_levels.RANGE_NAME).read_bytes(), N)[0]["names"]
    del entry["range_cells"]
    pool_levels.build(site, data_url="https://x/")
    assert not (site / pool_levels.RANGE_NAME).exists()
    assert (site / pool_levels.OUT_NAME).exists()
    assert json.loads((site / pool_levels.DATES_NAME).read_text()) == {
        "photos": None,
        "scored": None,
    }
    entry.update(built_at="2026-10-27T05:11:17Z", emb="/scratch/bulk-2026-10-15/completed/E.npy")
    pool_levels.build(site, data_url="https://x/")
    dates = json.loads((site / pool_levels.DATES_NAME).read_text())
    assert dates == {"photos": "2026-10-15", "scored": "2026-10-27"}
    page_identify.build(site)
    about = (site / page_identify.PAGE_NAME).read_text()
    assert "Photos downloaded on 15 October 2026, scored on 27 October 2026." in about
    assert "not in the\n15 October 2026 photo download" in about
    pool_levels.build(site, parquet=src / "identify.parquet")  # a local table has no dates
    assert not (site / pool_levels.DATES_NAME).exists()


def test_the_scoring_dates_fall_back_to_the_model_source_and_skip_what_is_not_a_date():
    model = {"model": {"source": "bulk-2026-10-15/completed"}}
    assert pool_levels.scoring_dates(model) == {"photos": "2026-10-15", "scored": None}
    bad = {"identify": {"built_at": "soon", "emb": "E.npy"}}
    assert pool_levels.scoring_dates(bad) == {"photos": None, "scored": None}
    html = page_identify.render(dates=None)
    assert "Photos downloaded" not in html and "last photo download" in html
    assert "__" not in html.split("<details", 1)[1].split("</details>", 1)[0]


def test_mislabel_and_weird_show_their_lowest_score_first_and_the_others_their_highest():
    level = np.array([2, 2, 4, 4, 5, 5], np.uint8)
    score = np.array([-0.001, -0.019, 0.1, 0.3, -0.03, -0.2])
    q = pool_levels.quantize(level, score)
    assert q[0] > q[1]  # close calls: the margin nearest 0 first
    assert q[2] > q[3] and q[5] > q[4]  # odd shots and might be mislabelled: lowest first
