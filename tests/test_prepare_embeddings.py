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


def _photo_archive(path, members):
    import io
    import tarfile

    path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path, "w") as archive:
        for name, content in members.items():
            member = tarfile.TarInfo(name)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))


def test_archive_preparation_cleans_each_group_and_resumes_checkpoint(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from what_to_id.embed import photo_path

    rows = pd.DataFrame(
        {
            "id": [1, 2],
            "iconic_taxon": ["Aves", "Mammalia"],
            "photo_url": ["a", "b"],
            "lat": [0.0, 0.0],
            "lon": [0.0, 0.0],
        }
    )
    pool = tmp_path / "pool.parquet"
    rows.to_parquet(pool)
    reference = tmp_path / "reference.npz"
    _cache(reference, [99])
    archives = tmp_path / "archives"
    ordinary = tmp_path / "ordinary"
    ordinary.mkdir()
    for row in rows.itertuples():
        name = photo_path(tmp_path, row.id, row.photo_url).name
        content = str(row.id).encode()
        _photo_archive(archives / f"{row.iconic_taxon}.tar", {f"photos/{name}": content})
        (ordinary / name).write_bytes(content)
    monkeypatch.setattr(prep.shutil, "disk_usage", lambda _: SimpleNamespace(free=100 * 1024**3))
    interrupted = True
    archive_mode = True

    def encode(current, *, cache_dir, backbone, **kwargs):
        target = emb_cache_path(cache_dir, current.iconic_taxon.iloc[0], backbone)
        if target.exists():
            assert set(current.id) <= set(load_embeddings(target)[0])
            if archive_mode:
                assert not (cache_dir / "photos").exists()
            return target
        assert len(list((cache_dir / "photos").iterdir())) == (1 if archive_mode else 2)
        for row in current.itertuples():
            assert photo_path(cache_dir, row.id, row.photo_url).read_bytes() == str(row.id).encode()
        if interrupted and current.id.iloc[0] == 2:
            raise RuntimeError("interrupted second taxon")
        _cache(target, current.id)
        return target

    monkeypatch.setattr(prep, "embed_group", encode)
    args = dict(pool=pool, reference_embeddings=str(reference), model_snapshot=tmp_path / "model")
    work = tmp_path / "work"
    checkpoint = tmp_path / "checkpoint"
    with pytest.raises(RuntimeError, match="interrupted"):
        prep.prepare(
            **args,
            work_dir=work,
            out=tmp_path / "bundle",
            photo_archive_dir=archives,
            checkpoint_dir=checkpoint,
        )
    assert not (work / "candidates/photos").is_symlink()
    assert not list((work / "candidates").glob("photo-group-*"))
    assert load_embeddings(checkpoint / "candidates/emb_Aves_bioclip25.npz")[0].tolist() == [1]
    (archives / "Aves.tar").unlink()  # Completed groups must resume without extracting photos.
    interrupted = False
    prep.prepare(**args, work_dir=work, out=tmp_path / "bundle", photo_archive_dir=archives)
    archive_mode = False
    prep.prepare(
        **args,
        work_dir=tmp_path / "ordinary-work",
        out=tmp_path / "ordinary-bundle",
        photo_cache=ordinary,
    )
    candidates, _ = load_bundle(tmp_path / "bundle")
    expected, _ = load_bundle(tmp_path / "ordinary-bundle")
    for group in candidates:
        actual_ids, actual_vectors, _ = load_embeddings(candidates[group])
        expected_ids, expected_vectors, _ = load_embeddings(expected[group])
        np.testing.assert_array_equal(actual_ids, expected_ids)
        np.testing.assert_array_equal(actual_vectors, expected_vectors)
    assert not (work / "candidates/photos").is_symlink()
    assert not list((work / "candidates").glob("photo-group-*"))


def test_archive_disk_preflight_preserves_existing_link(tmp_path, monkeypatch):
    from types import SimpleNamespace

    archive = tmp_path / "group.tar"
    _photo_archive(archive, {"photos/a.jpg": b"photo"})
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "photos").symlink_to("prior-photos", target_is_directory=True)
    monkeypatch.setattr(prep.shutil, "disk_usage", lambda _: SimpleNamespace(free=14))
    with (
        pytest.raises(ValueError, match="insufficient local disk"),
        prep.extracted_photos(archive, cache, headroom_bytes=10),
    ):
        pytest.fail("insufficient space must not reach the encoder")
    assert (cache / "photos").readlink() == Path("prior-photos")
    assert not list(cache.glob("photo-group-*"))
    monkeypatch.setattr(prep.shutil, "disk_usage", lambda _: SimpleNamespace(free=15))
    with (
        pytest.raises(RuntimeError, match="encoder failed"),
        prep.extracted_photos(archive, cache, headroom_bytes=10),
    ):
        assert (cache / "photos/a.jpg").read_bytes() == b"photo"
        raise RuntimeError("encoder failed")
    assert (cache / "photos").readlink() == Path("prior-photos")
    assert not list(cache.glob("photo-group-*"))


@pytest.mark.parametrize("name", ["../escape.jpg", "/photos/a.jpg", "photos/../escape.jpg"])
def test_archive_rejects_unsafe_paths_before_extraction(tmp_path, name):
    archive = tmp_path / "group.tar"
    _photo_archive(archive, {name: b"photo"})
    with (
        pytest.raises(ValueError, match="unsafe photo archive member"),
        prep.extracted_photos(archive, tmp_path / "cache", headroom_bytes=0),
    ):
        pytest.fail("unsafe archive reached the encoder")
    assert not list((tmp_path / "cache").iterdir())


def test_archive_rejects_links(tmp_path):
    import tarfile

    archive = tmp_path / "group.tar"
    with tarfile.open(archive, "w") as out:
        member = tarfile.TarInfo("photos/link.jpg")
        member.type = tarfile.SYMTYPE
        member.linkname = "../../outside"
        out.addfile(member)
    with (
        pytest.raises(ValueError, match="unsafe photo archive member"),
        prep.extracted_photos(archive, tmp_path / "cache", headroom_bytes=0),
    ):
        pytest.fail("archive link reached the encoder")


def test_photo_cache_and_archives_are_mutually_exclusive(tmp_path):
    with pytest.raises(ValueError, match="not both"):
        prep.prepare(
            tmp_path / "unused",
            reference_embeddings="unused",
            model_snapshot=tmp_path / "model",
            work_dir=tmp_path / "work",
            out=tmp_path / "bundle",
            photo_cache=tmp_path,
            photo_archive_dir=tmp_path,
        )
