"""Taxon text vectors: table from the pool, file layout, manifest entry (fake tower, no torch)."""

import gzip
import json

import numpy as np
import pandas as pd
import pytest

from what_to_id import atlas_taxa
from what_to_id.atlas_index_io import write_manifest

DIMS = 8


def fake_embed(prompts):
    """Deterministic non-unit vectors keyed by the prompt text."""
    out = np.zeros((len(prompts), DIMS), dtype=np.float32)
    for i, prompt in enumerate(prompts):
        out[i] = np.random.default_rng(sum(map(ord, prompt))).standard_normal(DIMS) + 3.0
    return out


@pytest.fixture
def pool(tmp_path):
    path = tmp_path / "pool.parquet"
    pd.DataFrame(
        {
            "taxon_id": [3, 1, 1, 2, 4, 5, None],
            "taxon_name": ["Lobaria  pulmonaria", "Acer", "Acer", "Zea mays", "acer", "Poa", None],
            "common_name": ["Lungwort", None, "Maple", "Corn", "", "", "Ghost"],
        }
    ).to_parquet(path)
    return path


@pytest.fixture
def index(tmp_path):
    out = tmp_path / "idx"
    out.mkdir()
    write_manifest(out, {"version": 2, "dims": DIMS, "parts": []})
    return out


def test_table_is_distinct_sorted_and_prefers_a_common_name(pool):
    assert atlas_taxa.taxa_table(pool) == [
        ("Acer", "Maple"),
        ("Lobaria pulmonaria", "Lungwort"),
        ("Poa", ""),
        ("Zea mays", "Corn"),
    ]


def test_build_writes_consistent_files_and_manifest(pool, index):
    entry = atlas_taxa.build(pool, index, fake_embed)
    manifest = json.loads((index / "manifest.json").read_text())
    assert manifest["version"] == 2 and manifest["taxa"] == entry
    assert entry["count"] == 4 and entry["dims"] == DIMS and entry["prompt"] == "a photo of {}"
    assert entry["names"].startswith("taxa-") and entry["vectors"].startswith("taxa-")
    lines = gzip.decompress((index / entry["names"]).read_bytes()).decode().split("\n")
    assert lines == ["Acer\tMaple", "Lobaria pulmonaria\tLungwort", "Poa\t", "Zea mays\tCorn", ""]
    raw = np.fromfile(index / entry["vectors"], dtype="<f2")
    assert raw.size == 4 * DIMS
    vectors = raw.reshape(4, DIMS).astype(np.float32)
    np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-3)
    want = fake_embed(["a photo of Lobaria pulmonaria"])[0]
    np.testing.assert_allclose(vectors[1], want / np.linalg.norm(want), atol=1e-3)


def test_rebuild_is_deterministic_and_removes_replaced_files(pool, index):
    first = atlas_taxa.build(pool, index, fake_embed)
    assert atlas_taxa.build(pool, index, fake_embed) == first
    assert sorted(p.name for p in index.glob("taxa-*")) == sorted(
        [first["names"], first["vectors"]]
    )
    changed = atlas_taxa.build(pool, index, lambda p: fake_embed(p)[::-1])
    assert changed["vectors"] != first["vectors"] and changed["names"] == first["names"]
    assert sorted(p.name for p in index.glob("taxa-*")) == sorted(
        [changed["names"], changed["vectors"]]
    )
    assert not list(index.glob("*.tmp"))


def test_build_rejects_bad_input(tmp_path, pool, index):
    with pytest.raises(ValueError, match="expected"):
        atlas_taxa.build(pool, index, lambda p: np.ones((len(p), DIMS + 1), "f4"))
    with pytest.raises(ValueError, match="zero-length"):
        atlas_taxa.build(pool, index, lambda p: np.zeros((len(p), DIMS), "f4"))
    empty = tmp_path / "empty.parquet"
    pd.DataFrame({"taxon_name": [None], "common_name": [None]}).to_parquet(empty)
    with pytest.raises(ValueError, match="no taxon_name"):
        atlas_taxa.build(empty, index, fake_embed)
    assert "taxa" not in json.loads((index / "manifest.json").read_text())
    with pytest.raises(FileNotFoundError):
        atlas_taxa.build(pool, tmp_path / "missing", fake_embed)
