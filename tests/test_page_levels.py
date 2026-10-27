"""The levels page: the data file round-trips the rows in order, the build, the Explore entry."""

import gzip
import json
import re

import numpy as np
import pandas as pd

from what_to_id import page_levels, split_page

from .test_page_nav import FORBIDDEN

OPEN = "https://inaturalist-open-data.s3.amazonaws.com/photos/"
STATIC = "https://static.inaturalist.org/photos/"


def levels_frame():
    rows = [
        (101, 1, "Aus bus", "Plantae", "easy", 0.6, "Cus dus", f"{OPEN}11/medium.jpg"),
        (102, 7, "Eus fus", "Fungi", "easy", 0.7, "Cus dus", f"{STATIC}12/medium.jpeg?15"),
        (201, 1, "Aus bus", "Plantae", "taxonomist", -0.01, "Cus dus", f"{OPEN}21/medium.png"),
        (301, 7, "Eus fus", "Fungi", "weird", 0.3, "Gus hus", f"{OPEN}31/medium.jpg"),
        (302, 9, "Hus ius", None, "weird", 0.4, "Aus bus", "https://example.org/x.jpg"),
    ]
    return pd.DataFrame(rows, columns=list(page_levels.LEVEL_COLUMNS))


def decode(blob):
    return json.loads(gzip.decompress(blob))


def photo_url(d, i):
    m, e = d["meta"][i], len(d["exts"])
    return None if m == 255 else f"{d['hosts'][m // e]}{d['photo'][i]}/medium.{d['exts'][m % e]}"


def write(tmp_path):
    pq = tmp_path / "levels.parquet"
    levels_frame().to_parquet(pq)
    assert page_levels.main(["--out", str(tmp_path / "site"), "--parquet", str(pq)]) == 0
    return tmp_path / "site"


def test_build_round_trips_the_rows_in_order(tmp_path):
    out = write(tmp_path)
    d = decode((out / "levels-data.bin").read_bytes())
    assert d["id"] == [101, 102, 201, 301, 302]
    assert [d["levels"][x][0] for x in d["level"]] == ["easy"] * 2 + ["taxonomist"] + ["weird"] * 2
    assert [d["taxa"][t] for t in d["taxon"]] == [
        "Aus bus",
        "Eus fus",
        "Aus bus",
        "Eus fus",
        "Hus ius",
    ]
    assert d["taxa"][d["looks"][2]] == "Cus dus"
    assert sorted(d["groups"]) == ["Fungi", "Plantae"]
    assert [d["groups"][g] if g >= 0 else None for g in d["group"]] == [
        "Plantae",
        "Fungi",
        "Plantae",
        "Fungi",
        None,
    ]
    assert [photo_url(d, i) for i in range(5)] == [
        f"{OPEN}11/medium.jpg",
        f"{STATIC}12/medium.jpeg",
        f"{OPEN}21/medium.png",
        f"{OPEN}31/medium.jpg",
        None,
    ]
    html = (out / "levels.html").read_text()
    assert "levels-data.bin?v=" in html and "var IdentifyLinks" in html
    assert not re.findall(r"__[A-Z_]+__", html)
    low = (html + json.dumps(d["levels"])).lower()
    assert not [w for w in FORBIDDEN if w in low]


def test_unknown_level_and_missing_column_are_refused(tmp_path, capsys):
    bad = levels_frame().assign(level="hard")
    bad.to_parquet(tmp_path / "bad.parquet")
    args = ["--out", str(tmp_path), "--parquet", str(tmp_path / "bad.parquet")]
    assert page_levels.main(args) == 1
    assert "unknown levels" in capsys.readouterr().err
    levels_frame().drop(columns="photo_url").to_parquet(tmp_path / "bad.parquet")
    assert page_levels.main(args) == 1
    assert "lacks photo_url" in capsys.readouterr().err


def test_empty_table_builds_an_empty_page(tmp_path):
    pq = tmp_path / "levels.parquet"
    levels_frame().iloc[:0].to_parquet(pq)
    assert page_levels.main(["--out", str(tmp_path), "--parquet", str(pq)]) == 0
    assert decode((tmp_path / "levels-data.bin").read_bytes())["id"] == []


def test_manifest_without_the_key_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(page_levels, "_fetch", lambda url, path: path.write_text("{}"))
    assert page_levels.main(["--out", str(tmp_path), "--data-url", "https://x.test/"]) == 0
    assert list(tmp_path.iterdir()) == []


def test_manifest_with_the_key_fetches_the_table(tmp_path, monkeypatch):
    src = tmp_path / "src.parquet"
    levels_frame().to_parquet(src)
    entry = {"name": "levels.parquet", "built_at": "2026-10-26T03:00:00Z", "count": 5}

    def fetch(url, path):
        if url.endswith("manifest.json"):
            path.write_text(json.dumps({"levels": entry}))
        else:
            path.write_bytes(src.read_bytes())

    monkeypatch.setattr(page_levels, "_fetch", fetch)
    out = tmp_path / "site"
    assert page_levels.main(["--out", str(out), "--data-url", "https://x.test/"]) == 0
    assert "Built 2026-10-26" in (out / "levels.html").read_text()


def test_explore_offers_the_levels_only_once_built(tmp_path):
    assert 'href="levels.html"' not in split_page.build(tmp_path).read_text()
    (tmp_path / "levels.html").write_text("<html></html>")
    html = split_page.build(tmp_path).read_text()
    assert html.count('href="levels.html"') == 1 and split_page.LEVELS_LINK in html


def test_range_notes_ride_along_only_when_present(tmp_path):
    d = decode(page_levels.encode(levels_frame()))
    assert "note" not in d
    f = levels_frame().assign(range_note=[None, None, "Range: outside both ranges", None, None])
    d = decode(page_levels.encode(f))
    assert d["notes"] == ["Range: outside both ranges"]
    assert d["note"] == [-1, -1, 0, -1, -1]


def range_files():
    ranges = pd.DataFrame({"name": ["Aus bus", "Cus dus"], "cells": [[0, 9], [9]]})
    grid = pd.DataFrame(
        {
            "lat": [np.float32([48.0, 48.5, 48.5])] * 10,
            "lon": [np.float32([-123.0, -122.5, -122.0])] * 10,
        }
    )
    return ranges, grid


def test_range_maps_ride_along_only_with_the_files():
    d = decode(page_levels.encode(levels_frame()))
    assert not {"grid", "rng", "plat", "plon"} & d.keys()
    ranges, grid = range_files()
    f = levels_frame().assign(
        lat=[None, None, 48.51, None, None], lon=-123.456, out_km=[0, None, 120, 5, None]
    )
    d = decode(page_levels.encode(f, "", ranges, grid))
    assert len(d["grid"]) == 10 and d["grid"][0] == [-123000, 48000, -122500, 48500, -122000, 48500]
    assert d["okm"] == [0, -1, 120, 5, -1]
    assert d["plat"] == [None, None, 4851, None, None] and d["plon"][2] == -12346
    by = dict(zip(d["taxa"], d["rng"], strict=True))
    assert by["Eus fus"] == "" and by["Cus dus"] == "AAI="
    assert by["Aus bus"] == "AQI="  # bits 0 and 9, least significant first
    d = decode(page_levels.encode(levels_frame(), "", ranges, grid))
    assert "rng" in d and "plat" not in d


def test_local_parquet_picks_up_the_range_files_beside_it(tmp_path):
    ranges, grid = range_files()
    ranges.to_parquet(tmp_path / "level-ranges.parquet")
    grid.to_parquet(tmp_path / "level-range-cells.parquet")
    out = write(tmp_path)
    assert "grid" in decode((out / "levels-data.bin").read_bytes())


def test_pool_drops_records_identified_or_relabelled_since(tmp_path):
    pq, pool = tmp_path / "levels.parquet", tmp_path / "pool.parquet"
    levels_frame().to_parquet(pq)
    # 102 left the pool, 301 was relabelled; the rest are still Needs ID under their label
    pd.DataFrame({"id": [101, 201, 301, 302, 999], "taxon_id": [1, 1, 8, 9, 1]}).to_parquet(pool)
    out = tmp_path / "site"
    assert page_levels.main(["--out", str(out), "--parquet", str(pq), "--pool", str(pool)]) == 0
    assert decode((out / "levels-data.bin").read_bytes())["id"] == [101, 201, 302]
