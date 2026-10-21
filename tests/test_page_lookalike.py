"""Look-alike stats: agreement and nearest other-taxon level from the HD neighbours, host pairs
skipped, packed in the two-plane byte layout the photo-space page reads."""

from __future__ import annotations

import gzip
import json

import numpy as np
import pandas as pd
import pytest

from what_to_id import page_lookalike
from what_to_id.atlas_index_io import VERSION
from what_to_id.atlas_neighbors import write_neighbor_records
from what_to_id.page_map import encode_points, render_map

from .embeddings_fixture import pool_frame

# taxon id -> [parent, latin, common, rank]
TREE = {
    1: [None, "Fungi", "", "kingdom"],
    2: [1, "Basidiomycota", "", "phylum"],
    3: [2, "Ustilaginomycetes", "", "class"],
    4: [3, "Ustilaginales", "", "order"],
    5: [4, "Ustilaginaceae", "", "family"],
    10: [5, "Ustilago a", "", "species"],
    11: [5, "Ustilago b", "", "species"],
    12: [4, "Smut sp", "", "species"],  # no family between it and its order
    20: [None, "Plantae", "", "kingdom"],
    21: [20, "Tracheophyta", "", "phylum"],
    22: [21, "Liliopsida", "", "class"],
    23: [22, "Poales", "", "order"],
    24: [23, "Poaceae", "", "family"],
    25: [23, "Cyperaceae", "", "family"],
    30: [24, "Grass a", "", "species"],
    31: [24, "Grass b", "", "species"],
    32: [25, "Sedge", "", "species"],
}
TAXON = {101: 10, 102: 10, 103: 11, 104: 11, 105: 10, 106: 12, 107: 10, 109: None, 110: 1}
TAXON.update({201: 30, 202: 31, 301: 32})
OLD = (201, 202, 301)  # observed long ago, so they sit in the second shard
OUT = 999_999  # a neighbour outside the site
# record -> its 12 HD neighbours in cosine order (padded with OUT); 107 has none
NEIGHBORS = {
    101: [102, 201, 103],  # Ustilago a: same taxon, its grass host, then a same-family smut
    102: [101, 103],
    103: [104],  # only its own taxon
    104: [103],  # overridden by the delta below
    105: [102, 201, 202],  # only own taxon and hosts
    106: [201],  # family unknown, so never a host pair
    109: [101],  # no taxon
    110: [101],  # kingdom only: undecidable below it
    201: [101, 301],
    202: [201],
    301: [201],
}
DELTA = {104: [301]}  # a later set wins for the ids it holds
HOSTS = "family_a\tfamily_b\ttypes\tglobi_rows\tsource\nPoaceae\tUstilaginaceae\thasHost\t5\tdoi\n"
NO_HOSTS = "family_a\tfamily_b\ttypes\tglobi_rows\tsource\n"


def _write_site(site):
    ids = sorted(TAXON)
    pool = pool_frame(np.array(ids))
    tid = [TAXON[i] for i in ids]
    pool["taxon_id"] = pd.array(tid, dtype="Int64")
    pool["taxon_name"] = [TREE[t][1] if t else None for t in tid]
    pool["rank"] = [TREE[t][3] if t else None for t in tid]
    old = pool["id"].isin(OLD)
    pool.loc[old, "observed_on"] = "2001-05-01"
    pool.loc[old, "created_at"] = "2001-05-01T00:00:00Z"
    blobs, meta = encode_points(pool, TREE)
    assert len(meta["shards"]) == 2
    for name, blob in blobs.items():
        (site / name).write_bytes(blob)
    (site / "map.html").write_text(render_map(meta, freeze=None))


def _write_parts(parts):
    (parts / "manifest.json").write_text(json.dumps({"version": VERSION, "count": 0}))
    for name, table in (("neighbors", NEIGHBORS), ("neighbors-delta-1", DELTA)):
        ids = np.array(sorted(table))
        nb = np.array([(table[i] + [OUT] * 12)[:12] for i in ids])
        cos = np.tile(np.linspace(0.9, 0.5, 12), (len(ids), 1))
        write_neighbor_records(parts, name, ids, nb, cos)


@pytest.fixture
def site(tmp_path):
    root, parts = tmp_path / "site", tmp_path / "parts"
    root.mkdir()
    parts.mkdir()
    _write_site(root)
    _write_parts(parts)
    (tmp_path / "hosts.tsv").write_text(HOSTS)
    (tmp_path / "none.tsv").write_text(NO_HOSTS)
    return tmp_path


def _read(site_dir):
    """Decode pool-lookalike.bin per the contract, keyed by record id."""
    raw = gzip.decompress((site_dir / "pool-lookalike.bin").read_bytes())
    order = sorted(i for i in TAXON if i not in OLD) + sorted(OLD)
    n = len(order)
    assert len(raw) == 2 * n
    a, b = raw[:n], raw[n:]
    return {
        rid: {
            "class": a[k] & 15,
            "order": a[k] >> 4,
            "family": b[k] & 15,
            "level": (b[k] >> 4) - 2 if b[k] >> 4 != 15 else None,
        }
        for k, rid in enumerate(order)
    }


def _build(tmp, hosts="hosts.tsv"):
    stats = page_lookalike.build(tmp / "site", parts=tmp / "parts", pair_files=[tmp / hosts])
    return _read(tmp / "site"), stats


def test_look_alike_skips_host_pairs_and_keeps_other_neighbours(site):
    got, stats = _build(site)
    level = {rid: r["level"] for rid, r in got.items()}
    assert level[101] == 0  # its grass is skipped, the next other taxon is a same-family smut
    assert level[201] == 1  # symmetric: the grass skips the smut and finds the sedge
    assert level[104] == 5  # an unflagged cross-family neighbour is kept (from the delta set)
    assert level[105] == -2  # every other taxon among its neighbours is a host
    assert level[106] == 5  # its family is unknown, so the grass is never a host pair
    assert level[102] == 0 and level[202] == 0 and level[301] == 1
    assert level[103] == -2  # only its own taxon
    assert level[110] == -1  # kingdom only: the LCA rank cannot be told
    assert level[107] is None and level[109] is None  # no neighbours, no taxon
    assert stats["records_changed"] == 3
    assert stats["edges_dropped"] == 4  # 101>201, 105>201, 105>202, 201>101


def test_without_host_pairs_the_first_other_taxon_counts(site):
    got, _ = _build(site, "none.tsv")
    assert got[101]["level"] == 5 and got[105]["level"] == 5 and got[201]["level"] == 5


def test_agreement_counts_known_site_neighbours_and_ignores_the_host_filter(site):
    with_hosts, _ = _build(site)
    without, _ = _build(site, "none.tsv")
    for rid in TAXON:
        for rank in ("class", "order", "family"):
            assert with_hosts[rid][rank] == without[rid][rank]
    r = with_hosts
    assert (r[101]["class"], r[101]["order"], r[101]["family"]) == (8, 8, 8)  # 2 of 3 in twelfths
    assert r[105]["family"] == 4 and r[104]["family"] == 0 and r[102]["family"] == 12
    assert r[106]["family"] == 15 and r[106]["order"] == 0  # no family of its own
    assert r[107] == {"class": 15, "order": 15, "family": 15, "level": None}
    assert r[109]["class"] == 15 and r[110]["class"] == 15


def test_cli_fetches_the_sets_from_the_data_url(site, capsys):
    url = (site / "parts").as_uri() + "/"
    assert page_lookalike.main(["--out", str(site / "site"), "--data-url", url]) == 0
    assert "edges_dropped" in capsys.readouterr().out
    assert set(_read(site / "site")) == set(TAXON)


def test_cli_without_a_neighbour_source_fails_cleanly(site, capsys):
    assert page_lookalike.main(["--out", str(site / "site")]) == 1
    assert "--data-url" in capsys.readouterr().err
