from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from what_to_id import prepare_embeddings as prep
from what_to_id.arms import load_embeddings
from what_to_id.artifacts import load_bundle
from what_to_id.embed import emb_cache_path, save_embeddings
from what_to_id.manifest import sha256_file


@pytest.fixture(autouse=True)
def frozen_model(monkeypatch):
    monkeypatch.setattr(prep, "_verify_snapshot", lambda path: prep.MODEL_HASHES)


def _cache(path, ids):
    save_embeddings(
        path,
        ids=np.asarray(ids),
        E=np.tile([1.0, 0.0], (len(ids), 1)),
        lat=np.zeros(len(ids)),
        lon=np.zeros(len(ids)),
        backbone="bioclip25",
        emb_device="fixture",
        failed_ids=[],
    )


def test_prepare_reuses_only_unchanged_rows_and_preserves_reference(tmp_path, monkeypatch):
    old = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "iconic_taxon": ["Aves"] * 3,
            "photo_url": ["a", "b", "c"],
            "lat": [0.0] * 3,
            "lon": [0.0] * 3,
        }
    )
    current = old.copy()
    current.loc[1, "photo_url"] = "changed"
    current.loc[2, ["id", "photo_url"]] = [4, "new"]
    previous, pool = tmp_path / "old.parquet", tmp_path / "pool.parquet"
    old.to_parquet(previous)
    current.to_parquet(pool)
    candidates, references = tmp_path / "old.npz", tmp_path / "reference.npz"
    _cache(candidates, [1, 2, 3])
    _cache(references, [99])
    ref_hash = sha256_file(references)
    attestation = tmp_path / "prior.json"
    attestation.write_text(
        json.dumps(
            {
                "model_sha256": prep.MODEL_HASHES,
                "model_revision": prep.MODEL_REVISION,
                "pool_sha256": sha256_file(previous),
                "output_candidate_sha256": {"*": sha256_file(candidates)},
            }
        )
    )
    encoded = []

    def embed(rows, *, backbone, cache_dir, device, batch, model_snapshot):
        target = emb_cache_path(cache_dir, "Aves", backbone)
        retained, _, _ = load_embeddings(target)
        assert retained.tolist() == [1]
        encoded.extend(sorted(set(rows.id) - set(retained)))
        _cache(target, rows.id.tolist())
        return target

    monkeypatch.setattr(prep, "embed_group", embed)
    out = prep.prepare(
        pool,
        model_snapshot=tmp_path / "model",
        previous_pool=previous,
        candidate_cache=str(candidates),
        previous_preparation=attestation,
        reference_embeddings=str(references),
        work_dir=tmp_path / "work",
        out=tmp_path / "bundle",
    )
    assert encoded == [2, 4]
    cand, ref = load_bundle(out)
    assert set(load_embeddings(cand["Aves"])[0]) == {1, 2, 4}
    assert sha256_file(ref["*"]) == ref_hash == sha256_file(references)
    record = json.loads((tmp_path / "work/preparation.json").read_text())
    assert record["pool_sha256"] == sha256_file(pool)


def test_prepare_refuses_reusing_workspace_for_changed_input(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "preparation.json").write_text("{}")
    pool = tmp_path / "pool.parquet"
    pd.DataFrame(
        {"id": [1], "iconic_taxon": ["Aves"], "photo_url": ["a"], "lat": [0.0], "lon": [0.0]}
    ).to_parquet(pool)
    reference = tmp_path / "ref.npz"
    _cache(reference, [99])
    with pytest.raises(ValueError, match="different preparation inputs"):
        prep.prepare(
            pool,
            model_snapshot=tmp_path / "model",
            reference_embeddings=str(reference),
            work_dir=work,
            out=tmp_path / "bundle",
        )


def test_prepare_requires_previous_snapshot_with_cache(tmp_path):
    with pytest.raises(ValueError, match="together"):
        prep.prepare(
            Path("unused"),
            model_snapshot=tmp_path / "model",
            candidate_cache="unused",
            reference_embeddings="unused",
            work_dir=tmp_path / "work",
            out=tmp_path / "bundle",
        )


def test_frozen_snapshot_rejects_changed_weights(tmp_path, monkeypatch):
    monkeypatch.undo()
    for filename in prep.MODEL_HASHES:
        (tmp_path / filename).write_bytes(b"untrusted checkpoint")
    with pytest.raises(ValueError, match="frozen BioCLIP"):
        prep._verify_snapshot(tmp_path)


def test_cache_requires_attestation(tmp_path):
    with pytest.raises(ValueError, match="preparation record"):
        prep.prepare(
            tmp_path / "pool",
            previous_pool=tmp_path / "previous",
            candidate_cache="old.npz",
            reference_embeddings="refs.npz",
            model_snapshot=tmp_path / "model",
            work_dir=tmp_path / "work",
            out=tmp_path / "bundle",
        )


def test_pinned_loader_uses_snapshot_config_and_weights(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    from what_to_id import embed

    config = {"model_cfg": {"embed_dim": 1024}, "preprocess_cfg": {"mean": [0.4]}}
    (tmp_path / "open_clip_config.json").write_text(json.dumps(config))
    seen = {}

    def register(path):
        seen["architecture"] = json.loads(path.read_text())

    def create(name, **kwargs):
        seen.update(kwargs)
        return model, None, "transform"

    model = SimpleNamespace(to=lambda device: model, eval=lambda: model, encode_image="encoder")
    monkeypatch.setattr(embed, "_require_embed_deps", lambda: None)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace())
    monkeypatch.setitem(
        sys.modules,
        "open_clip",
        SimpleNamespace(add_model_config=register, create_model_and_transforms=create),
    )
    assert embed.load_backbone("bioclip25", "cpu", model_snapshot=tmp_path) == (
        "encoder",
        "transform",
    )
    assert seen == {
        "architecture": {"embed_dim": 1024},
        "pretrained": str(tmp_path / "open_clip_model.safetensors"),
        "pretrained_hf": False,
        "image_mean": [0.4],
    }


def test_reference_cache_refuses_unattested_or_changed_source(tmp_path):
    source = tmp_path / "reference.parquet"
    source.write_bytes(b"frozen source")
    cache = tmp_path / "reference"
    cache.mkdir()
    _cache(cache / "Aves.npz", [99])
    with pytest.raises(ValueError, match="lacks preparation provenance"):
        prep.verify_reference_cache(cache, source, tmp_path / "model")
    record = {
        "pool_sha256": sha256_file(source),
        "model_revision": prep.MODEL_REVISION,
        "model_sha256": prep.MODEL_HASHES,
        "reference_sha256": {"Aves.npz": sha256_file(cache / "Aves.npz")},
    }
    (cache / "provenance.json").write_text(json.dumps(record))
    prep.verify_reference_cache(cache, source, tmp_path / "model")
    source.write_bytes(b"changed source")
    with pytest.raises(ValueError, match="source/model attestation"):
        prep.verify_reference_cache(cache, source, tmp_path / "model")
