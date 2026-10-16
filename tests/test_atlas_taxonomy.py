"""Expert scopes use taxon ancestry, including explicit incomplete-path states."""

import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from what_to_id.atlas_taxonomy import AtlasTaxonomy, membership
from what_to_id.embedding_atlas import build, group_payload
from what_to_id.taxonomy import PRESETS


def cache(tmp_path, taxa):
    path = tmp_path / "taxonomy.json"
    path.write_text(json.dumps({"taxa": taxa}))
    return path


def row(parent):
    return [parent, "Recorded taxon", "", "species"]


def test_known_membership_survives_partial_ancestry_and_missing_taxa(tmp_path):
    tree = AtlasTaxonomy(cache(tmp_path, {"1": row(None), "2": row(1), "3": row(9)}))
    assert tree.lineage(2) == {
        "taxon_id": 2,
        "ancestor_taxon_ids": [2, 1],
        "taxonomy_complete": True,
    }
    incomplete = tree.lineage(3)
    assert incomplete["ancestor_taxon_ids"] == [3, 9]
    assert incomplete["taxonomy_complete"] is False
    assert membership(incomplete, [9]) is True
    assert membership(incomplete, [1]) is None
    assert membership(tree.lineage(2), [9]) is False
    assert membership(tree.lineage(9), [9]) is True
    assert membership(tree.lineage(9), [1]) is None
    assert tree.lineage(None) == {
        "taxon_id": None,
        "ancestor_taxon_ids": [],
        "taxonomy_complete": False,
    }
    assert membership(tree.lineage(None), [1]) is None
    # One caller cannot corrupt another observation's cached ancestry.
    incomplete["ancestor_taxon_ids"].clear()
    assert tree.lineage(3)["ancestor_taxon_ids"] == [3, 9]


def test_metadata_reuses_map_presets_with_explicit_lichen_approximation(tmp_path):
    path = cache(tmp_path, {"1": row(None), "311249": row(1), "54743": row(1)})
    source = "https://example.org/releases/taxonomy.json"
    tree = AtlasTaxonomy(path, source_url=source)
    metadata = tree.metadata([tree.lineage(311249), tree.lineage(54743), tree.lineage(999)])
    assert metadata["cache_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert metadata["source_url"] == source
    assert metadata["complete_count"] == 2
    assert metadata["incomplete_count"] == 1
    for preset, (label, roots, description) in zip(metadata["presets"], PRESETS, strict=True):
        assert preset["label"] == label
        assert preset["taxon_ids"] == roots
        assert preset["description"] == description
        assert preset["approximate"] is (label == "Lichens")
        assert preset["match_count"] == 1
        assert preset["nonmatch_count"] == 1
        assert preset["unknown_count"] == 1


@pytest.mark.parametrize(
    ("taxa", "message"),
    [
        ({"1": row(1)}, "cycle"),
        ({"1": row(2), "2": row(3), "3": row(1)}, "cycle"),
        ({"1": row(None), "90": row(91), "91": row(90)}, "cycle"),
        ({"0": row(None)}, "positive integer"),
        ({"01": row(None)}, "invalid taxonomy ID"),
        ({"-1": row(None)}, "invalid taxonomy ID"),
        ({"1.0": row(None)}, "invalid taxonomy ID"),
        ({"１２": row(None)}, "invalid taxonomy ID"),
        ({str(2**53): row(None)}, "positive integer"),
        ({"1": row("2")}, "positive integer"),
        ({"1": row(2.0)}, "positive integer"),
        ({"1": row(True)}, "positive integer"),
        ({"1": row(False)}, "positive integer"),
        ({"1": row(0)}, "positive integer"),
        ({"1": row(-1)}, "positive integer"),
        ({"1": []}, "expected"),
        ({"1": {"parent": None}}, "expected"),
    ],
)
def test_malformed_taxonomy_fails_before_any_traversal(tmp_path, taxa, message):
    with pytest.raises(ValueError, match=message):
        AtlasTaxonomy(cache(tmp_path, taxa))


@pytest.mark.parametrize("raw", [[], {}, {"taxa": []}, {"taxa": None}])
def test_missing_tree_shape_fails_clearly(tmp_path, raw):
    path = tmp_path / "taxonomy.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="taxa object"):
        AtlasTaxonomy(path)


def test_duplicate_json_ids_do_not_silently_overwrite_parent_links(tmp_path):
    path = tmp_path / "taxonomy.json"
    path.write_text('{"taxa":{"1":[null,"","",""],"1":[2,"","",""]}}')
    with pytest.raises(ValueError, match="duplicate taxonomy key"):
        AtlasTaxonomy(path)


def test_deep_partial_tree_has_no_recursion_or_false_completeness(tmp_path):
    tree = AtlasTaxonomy(cache(tmp_path, {str(i): row(i + 1) for i in range(1, 3500)}))
    ancestry = tree.lineage(1)
    assert ancestry["ancestor_taxon_ids"] == list(range(1, 3501))
    assert ancestry["taxonomy_complete"] is False
    assert membership(ancestry, [3499]) is True
    assert membership(ancestry, [4000]) is None


@pytest.mark.parametrize("value", [True, False, 0, -1, 1.0, 1.5, "1", float("nan"), 2**53])
def test_observation_ids_do_not_coerce_noninteger_or_unsafe_values(tmp_path, value):
    tree = AtlasTaxonomy(cache(tmp_path, {}))
    with pytest.raises(ValueError, match="observation taxon_id.*positive integer"):
        tree.lineage(value)


@pytest.mark.parametrize(
    "source",
    [
        "http://example.org/taxonomy.json",
        "taxonomy.json",
        "https:///taxonomy.json",
        "https://user:secret@example.org/taxonomy.json",
        "https://example.org/taxonomy.json#fragment",
        "https://example.org/a b.json",
    ],
)
def test_source_provenance_rejects_nonpublic_or_malformed_urls(tmp_path, source):
    with pytest.raises(ValueError, match="absolute HTTPS URL"):
        AtlasTaxonomy(cache(tmp_path, {}), source_url=source)


def inputs(tmp_path):
    ids = np.array([11, 12, 13])
    vectors = np.eye(3, dtype=np.float32)
    embeddings = tmp_path / "Plantae.npz"
    np.savez(embeddings, ids=ids, E=vectors, backbone="fixture")
    pool = pd.DataFrame(
        {
            "id": [13, 11, 12],
            "iconic_taxon": "Plantae",
            "lon": -123,
            "lat": 49,
            "taxon_name": "Recorded taxon",
            "photo_url": "",
            "observed_on": "2026-09-11",
            "taxon_id": pd.array([None, 311249, 999], dtype="Int64"),
        }
    )
    return pool, embeddings


def test_payload_preserves_embedding_order_and_explicit_missing_ids(tmp_path):
    pool, embeddings = inputs(tmp_path)
    path = cache(tmp_path, {"1": row(None), "311249": row(1)})
    taxonomy = AtlasTaxonomy(path)
    original = group_payload(pool, embeddings, "Plantae")
    actual = group_payload(pool, embeddings, "Plantae", taxonomy=taxonomy)
    assert "taxonomy" not in original
    assert all("taxon_id" not in record for record in original["records"])
    assert [r["id"] for r in actual["records"]] == [11, 12, 13]
    assert [r["taxon_id"] for r in actual["records"]] == [311249, 999, None]
    assert [r["taxonomy_complete"] for r in actual["records"]] == [True, False, False]
    assert actual["taxonomy"]["source_url"] is None
    assert actual["taxonomy"]["complete_count"] == 1
    assert actual["taxonomy"]["incomplete_count"] == 2
    for before, after in zip(original["records"], actual["records"], strict=True):
        assert all(after[key] == value for key, value in before.items())
    pool.drop(columns="taxon_id", inplace=True)
    with pytest.raises(ValueError, match="requires taxon_id"):
        group_payload(pool, embeddings, "Plantae", taxonomy=taxonomy)


def test_build_exports_the_requested_offline_cache_and_source(tmp_path):
    pool, embeddings = inputs(tmp_path)
    pool_path = tmp_path / "pool.parquet"
    pool.to_parquet(pool_path)
    path = cache(tmp_path, {"311249": row(None)})
    out = tmp_path / "site"
    source = "https://example.org/taxonomy.json"
    build(
        pool_path,
        str(embeddings),
        out,
        snapshot_date="2026-09-11",
        taxonomy_path=path,
        taxonomy_source=source,
    )
    actual = json.loads((out / "embeddings-data/Plantae.json").read_text())
    assert actual["taxonomy"]["source_url"] == source
    assert actual["taxonomy"]["cache_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual["records"][0]["ancestor_taxon_ids"] == [311249]
    with pytest.raises(ValueError, match="source requires a taxonomy cache"):
        build(pool_path, str(embeddings), out, snapshot_date="2026-09-11", taxonomy_source=source)
    pool.drop(columns="taxon_id").to_parquet(pool_path)
    with pytest.raises(ValueError, match="requires taxon_id"):
        build(pool_path, str(embeddings), out, snapshot_date="2026-09-11", taxonomy_path=path)


def test_cli_offline_taxonomy_flags_reach_the_published_payload(tmp_path, monkeypatch):
    import sys

    from what_to_id.embedding_atlas import main

    pool, embeddings = inputs(tmp_path)
    pool_path = tmp_path / "pool.parquet"
    pool.to_parquet(pool_path)
    taxonomy = cache(tmp_path, {"311249": row(None)})
    out = tmp_path / "site"
    source = "https://example.org/taxonomy.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "atlas",
            "--pool",
            str(pool_path),
            "--embeddings",
            str(embeddings),
            "--out",
            str(out),
            "--snapshot-date",
            "2026-09-11",
            "--taxonomy",
            str(taxonomy),
            "--taxonomy-source",
            source,
        ],
    )
    main()
    payload = json.loads((out / "embeddings-data/Plantae.json").read_text())
    assert payload["taxonomy"]["source_url"] == source
    assert payload["taxonomy"]["presets"][1]["approximate"] is True


def test_exclusion_inverts_only_known_membership_and_preserves_unknown(tmp_path):
    tree = AtlasTaxonomy(cache(tmp_path, {"1": row(None), "2": row(1), "3": row(9)}))
    # Taxon 3 reaches a known target before its ancestry ends at the missing parent.
    records = [
        tree.lineage(2),
        tree.lineage(3),
        tree.lineage(1),
        tree.lineage(99),
        tree.lineage(None),
    ]
    roots = [2, 3]
    assert [membership(r, roots) for r in records] == [True, True, False, None, None]
    assert [membership(r, roots, exclude=True) for r in records] == [False, False, True, None, None]
    with pytest.raises(ValueError, match="exclude must be a boolean"):
        membership(records[0], roots, exclude="true")


def test_fungal_metadata_appends_an_explicit_approximate_exclusion_without_reordering(tmp_path):
    tree = AtlasTaxonomy(cache(tmp_path, {"1": row(None), "54743": row(1), "118252": row(999)}))
    records = [tree.lineage(54743), tree.lineage(118252), tree.lineage(1), tree.lineage(98)]
    original = tree.metadata(records)
    fungi = tree.metadata(records, group="Fungi")
    plants = tree.metadata(records, group="Plantae")
    assert fungi["presets"][:2] == original["presets"] == plants["presets"]
    included, outside = fungi["presets"][1:]
    assert included["exclude"] is False and outside["exclude"] is True
    assert outside["label"] == "Outside listed lichen-forming groups"
    assert outside["taxon_ids"] == included["taxon_ids"]
    assert outside["approximate"] is True
    assert outside["match_count"] == 1
    assert outside["nonmatch_count"] == 2
    assert included["match_count"] == 2
    assert included["nonmatch_count"] == 1
    assert outside["unknown_count"] == included["unknown_count"] == 1


def test_fungal_payload_passes_group_context_without_changing_observations(tmp_path):
    pool, embeddings = inputs(tmp_path)
    pool["iconic_taxon"] = "Fungi"
    pool["taxon_id"] = pd.array([None, 54743, 1], dtype="Int64")
    tree = AtlasTaxonomy(cache(tmp_path, {"1": row(None), "54743": row(1)}))
    baseline = group_payload(pool, embeddings, "Fungi")
    actual = group_payload(pool, embeddings, "Fungi", taxonomy=tree)
    assert len(actual["taxonomy"]["presets"]) == 3
    assert actual["taxonomy"]["presets"][2]["match_count"] == 1
    assert actual["taxonomy"]["presets"][2]["unknown_count"] == 1
    for before, after in zip(baseline["records"], actual["records"], strict=True):
        assert all(after[key] == value for key, value in before.items())
