import gzip
import json
import logging

import pandas as pd
import pytest

from what_to_id import taxonomy
from what_to_id.page_map import TAXA_NAME, encode_points, main
from what_to_id.taxonomy import (
    GROUP_TAXA,
    NO_RANK,
    PRESETS,
    fetch_taxa,
    load_tree,
    missing_ancestors,
    save_tree,
    taxa_table,
    update_tree,
)

from .conftest import make_pool

# a small tree: 1 Life > 2 Plantae > 3 Bryophyta > 4 Sphagnum > 5 Sphagnum fuscum, 6 Polytrichum
TREE = {
    1: [None, "Life", "", "stateofmatter"],
    2: [1, "Plantae", "Plants", "kingdom"],
    3: [2, "Bryophyta", "Mosses", "phylum"],
    4: [3, "Sphagnum", "Peat Mosses", "genus"],
    5: [4, "Sphagnum fuscum", "Rusty Peat Moss", "species"],
    6: [3, "Polytrichum", "Haircap Mosses", "genus"],
}


class FakeSession:
    def __init__(self, tree, hide=()):
        self.tree, self.hide, self.calls = tree, set(hide), []

    def get(self, url, params, timeout):
        ids = [int(i) for i in params["id"].split(",")]
        self.calls.append(ids)
        results = []
        for i in ids:
            if i not in self.tree or i in self.hide:
                continue
            chain, p = [], self.tree[i][0]
            while p is not None:
                chain.insert(0, p)
                p = self.tree[p][0]
            _, name, common, rank = self.tree[i]
            t = {"id": i, "name": name, "rank": rank, "ancestor_ids": [*chain, i]}
            if common:
                t["preferred_common_name"] = common
            results.append(t)

        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"results": results}

        return R()


def _pool(taxa):
    pool = make_pool(len(taxa), seed=2)
    pool["taxon_id"] = pd.array(taxa, dtype="Int64")
    pool["taxon_name"] = [TREE[t][1] if t in TREE else f"Taxon {t}" for t in taxa]
    pool["rank"] = [TREE[t][3] if t in TREE else "species" for t in taxa]
    return pool


def test_tree_cache_round_trips(tmp_path):
    path = tmp_path / "taxonomy.json"
    assert load_tree(path) == {} and load_tree(None) == {}
    save_tree(TREE, path)
    assert load_tree(path) == TREE
    assert not (tmp_path / "taxonomy.json.tmp").exists()


def test_fetch_taxa_reads_parent_and_names():
    got = fetch_taxa([5, 3, 99], session=FakeSession(TREE))
    assert got == {5: [4, "Sphagnum fuscum", "Rusty Peat Moss", "species"], 3: TREE[3]}
    assert fetch_taxa([1], session=FakeSession(TREE))[1][0] is None


def test_fetch_taxa_refuses_more_than_one_request():
    with pytest.raises(ValueError, match="at most"):
        fetch_taxa(range(taxonomy.PER_REQUEST + 1), session=FakeSession(TREE))


def test_update_tree_fetches_ancestors_and_only_what_is_missing(monkeypatch):
    monkeypatch.setattr(taxonomy, "PER_REQUEST", 2)
    s = FakeSession(TREE)
    tree = {}
    assert update_tree(tree, [5, 6], session=s, sleep=0) == 6
    assert tree == TREE and not missing_ancestors(tree)
    assert s.calls[0] == [5, 6]
    # a daily run with nothing new asks nothing; a new taxon costs one request
    s.calls.clear()
    assert update_tree(tree, [5, 6], session=s, sleep=0) == 0 and s.calls == []
    s.tree = {**TREE, 7: [4, "Sphagnum capillifolium", "", "species"]}
    assert update_tree(tree, [5, 7], session=s, sleep=0) == 1 and s.calls == [[7]]


def test_update_tree_stops_when_an_ancestor_is_unknown():
    s = FakeSession(TREE, hide={2})
    tree = {}
    update_tree(tree, [5], session=s, sleep=0)
    assert missing_ancestors(tree) == {2}


def test_taxa_table_without_tree_has_no_parents():
    rows, idx, ranks, complete = taxa_table(_pool([5, 5, 6, 5]))
    assert not complete
    assert [r[2] for r in rows] == [5, 6] and all(len(r) == 4 for r in rows)
    assert list(idx) == [0, 0, 1, 0] and ranks == ["genus", "species"]


def test_taxa_table_with_tree_appends_ancestors_by_id():
    rows, idx, ranks, complete = taxa_table(_pool([5, 5, 6]), TREE)
    assert complete
    assert [r[2] for r in rows] == [5, 6, 1, 2, 3, 4]
    parent = {r[2]: (rows[r[4]][2] if r[4] >= 0 else None) for r in rows}
    assert parent == {k: v[0] for k, v in TREE.items()}
    assert rows[2][3] == ranks.index("stateofmatter") and list(idx) == [0, 0, 1]


def test_taxa_table_with_a_gap_is_incomplete():
    tree = {k: v for k, v in TREE.items() if k != 2}
    rows, _, ranks, complete = taxa_table(_pool([5, 9]), tree)
    assert not complete
    by_id = {r[2]: r for r in rows}
    assert by_id[9][4] == -1 and by_id[3][4] == -1  # 9 unknown, 3's parent 2 missing
    assert all(r[3] == NO_RANK or ranks[r[3]] for r in rows)


def test_encode_points_with_tree_offers_presets():
    pool = _pool([5, 5, 6])
    _, meta = encode_points(pool)
    assert "presets" not in meta and meta["taxa_n"] == 2
    blobs, meta = encode_points(pool, TREE)
    assert meta["presets"] == PRESETS and meta["taxa_n"] == 2
    rows = json.loads(gzip.decompress(blobs[TAXA_NAME]))
    assert len(rows) == 6 and all(len(r) == 5 for r in rows)
    assert meta["group_ids"] == {g: GROUP_TAXA[g] for g in meta["groups"] if g in GROUP_TAXA}


def test_presets_name_their_taxa_once():
    ids = [i for _, taxa, _ in PRESETS for i in taxa]
    assert len(ids) == len(set(ids)) and [p[0] for p in PRESETS] == ["Bryophytes", "Lichens"]


def test_cli_builds_with_and_without_tree(tmp_path, caplog):
    pool = _pool([5, 5, 6])
    pool.to_parquet(tmp_path / "pool.parquet")
    save_tree(TREE, tmp_path / "tree.json")
    args = ["--pool", str(tmp_path / "pool.parquet"), "--out"]
    assert main([*args, str(tmp_path / "a"), "--tree", str(tmp_path / "tree.json")]) == 0
    assert '"presets":' in (tmp_path / "a" / "map.html").read_text()
    with caplog.at_level(logging.WARNING):
        assert main([*args, str(tmp_path / "b"), "--tree", str(tmp_path / "none.json")]) == 0
    assert "no taxon tree" in caplog.text
    assert '"presets":' not in (tmp_path / "b" / "map.html").read_text()


def test_taxonomy_cli_fills_the_cache(tmp_path, monkeypatch):
    _pool([5, 6]).to_parquet(tmp_path / "pool.parquet")
    monkeypatch.setattr(taxonomy, "make_session", lambda: FakeSession(TREE))
    monkeypatch.setattr(taxonomy, "SLEEP", 0)
    path = tmp_path / "tree.json"
    assert taxonomy.main(["--pool", str(tmp_path / "pool.parquet"), "--tree", str(path)]) == 0
    assert load_tree(path) == TREE
