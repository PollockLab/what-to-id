"""A four-list build is reproducible from content-identified embedding inputs."""

import json

import numpy as np
import pytest

from what_to_id.cli import main as build
from what_to_id.replay import ReplayError, replay

from .conftest import make_pool

KEY = bytes.fromhex("ab" * 32)


@pytest.fixture
def embedding_build(tmp_path, webapp_dir, monkeypatch):
    pytest.importorskip("labelfirst")
    monkeypatch.setenv("WHAT_TO_ID_KEY", KEY.hex())
    pool = make_pool(96, groups=["Aves", "Insecta"])
    pool_path = tmp_path / "pool.parquet"
    pool.to_parquet(pool_path, index=False)
    candidates, references = tmp_path / "candidates", tmp_path / "references"
    candidates.mkdir()
    references.mkdir()
    rng = np.random.default_rng(91)
    for group, rows in pool.groupby("iconic_taxon"):
        X = rng.normal(size=(len(rows), 8)).astype("float32")
        X /= np.linalg.norm(X, axis=1, keepdims=True)
        np.savez(candidates / f"emb_{group}.npz", ids=rows["id"].to_numpy(), E=X, backbone="test")
        np.savez(
            references / f"emb_{group}.npz", ids=rows["id"].to_numpy()[:8], E=X[:8], backbone="test"
        )
    out, served = tmp_path / "build", tmp_path / "served.parquet"
    assert (
        build(
            [
                "build",
                "--pool",
                str(pool_path),
                "--freeze",
                "2026-09-28",
                "--d1",
                "2026-11-01",
                "--arms",
                "recency,gap_first,similarity,novelty",
                "--design",
                "rotation",
                "--embeddings",
                str(candidates),
                "--reference-embeddings",
                str(references),
                "--webapp-dir",
                str(webapp_dir),
                "--batch-size",
                "6",
                "--max-batches",
                "2",
                "--key-env",
                "WHAT_TO_ID_KEY",
                "--served-log",
                str(served),
                "--out",
                str(out),
            ]
        )
        == 0
    )
    return pool_path, out / "build_record.json", served, candidates, references


def test_replay_four_lists_and_record_each_group(embedding_build, webapp_dir):
    pool, record, served, candidates, references = embedding_build
    data = json.loads(record.read_text())
    assert set(data["input_files"]["embeddings"]) == {"Aves", "Insecta"}
    assert set(data["input_files"]["reference_embeddings"]) == {"Aves", "Insecta"}
    for files in data["input_files"].values():
        for metadata in files.values():
            assert len(metadata["sha256"]) == 64
    assert str(candidates) not in record.read_text()
    result = replay(
        pool,
        record,
        served,
        webapp_dir,
        key=KEY,
        embeddings=str(candidates),
        reference_embeddings=str(references),
    )
    assert result.ok and result.expected_rows > 0


@pytest.mark.parametrize("change", ["modified", "missing", "omitted"])
def test_replay_rejects_different_embedding_inputs(embedding_build, webapp_dir, change):
    pool, record, served, candidates, references = embedding_build
    path = candidates / "emb_Aves.npz"
    if change == "modified":
        with path.open("ab") as f:
            f.write(b"changed")
    elif change == "missing":
        path.unlink()
    with pytest.raises(ReplayError, match="embedding"):
        replay(
            pool,
            record,
            served,
            webapp_dir,
            key=KEY,
            embeddings=None if change == "omitted" else str(candidates),
            reference_embeddings=str(references),
        )


def test_portable_bundle_replays_and_detects_tampering(embedding_build, webapp_dir, tmp_path):
    from what_to_id.artifacts import load_bundle, pack_bundle

    pool, record, served, candidates, references = embedding_build
    bundle = pack_bundle(pool, str(candidates), str(references), tmp_path / "bundle")
    moved = tmp_path / "moved"
    bundle.rename(moved)
    result = replay(pool, record, served, webapp_dir, key=KEY, embedding_bundle=str(moved))
    assert result.ok
    info = json.loads((moved / "embedding_bundle.json").read_text())
    item = info["files"]["embeddings"]["Aves"]
    (moved / item["file"]).write_bytes(b"not an embedding")
    with pytest.raises((ValueError, OSError)):
        load_bundle(moved)


def test_bundle_rejects_missing_groups(embedding_build, tmp_path):
    from what_to_id.artifacts import pack_bundle

    pool, _, _, candidates, references = embedding_build
    (candidates / "emb_Insecta.npz").unlink()
    with pytest.raises(ValueError, match="missing a pool taxon group"):
        pack_bundle(pool, str(candidates), str(references), tmp_path / "incomplete")
    assert not (tmp_path / "incomplete").exists()


def test_offline_daily_four_list_build(embedding_build, webapp_dir, tmp_path):
    import os
    import shutil
    import subprocess
    import sys
    from pathlib import Path

    from what_to_id.artifacts import pack_bundle
    from what_to_id.manifest import WHERE_TO_BLITZ_REF

    pool, _, _, candidates, references = embedding_build
    bundle = pack_bundle(pool, str(candidates), str(references), tmp_path / "bundle")
    state, output = tmp_path / "state", tmp_path / "out"
    state.mkdir()
    shutil.copyfile(pool, state / "pool.parquet")
    (webapp_dir / "provenance.json").write_text(json.dumps({"manifest_hash": "synthetic"}))
    # Only the remote grid checkout check is stubbed; the full build/replay code runs.
    binaries = tmp_path / "bin"
    binaries.mkdir()
    git = binaries / "git"
    git.write_text('#!/bin/sh\nprintf "%s\\n" ' + WHERE_TO_BLITZ_REF.split("@")[1] + "\n")
    git.chmod(0o755)
    env = {
        **os.environ,
        "PATH": str(binaries) + os.pathsep + os.environ["PATH"],
        "PYTHON": sys.executable,
        "STATE_DIR": str(state),
        "OUT_DIR": str(output),
        "TODAY": "2026-09-28",
        "BLITZ_D1": "2026-11-01",
        "OFFLINE": "1",
        "WTB_DIR": str(webapp_dir),
        "WHAT_TO_ID_KEY": KEY.hex(),
        "EMBEDDING_BUNDLE": str(bundle),
        "MAX_BATCHES": "2",
        "ARMS": "recency,gap_first,similarity,novelty",
    }
    root = Path(__file__).resolve().parents[1]
    run = subprocess.run(
        ["bash", "scripts/daily.sh", "build"],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        timeout=90,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    record = json.loads((state / "days/build-2026-09-28.json").read_text())
    assert len(record["arms"]) == 4 and record["design"] == "rotation"
    assert KEY.hex() not in run.stdout + run.stderr
    assert "arm_labels" not in record
    assert (output / "final/site/index.html").is_file()


@pytest.mark.parametrize("field", ["dimensions", "backbone"])
def test_bundle_rejects_incompatible_reference(embedding_build, tmp_path, field):
    from what_to_id.artifacts import pack_bundle

    pool, _, _, candidates, references = embedding_build
    path = references / "emb_Aves.npz"
    with np.load(path) as data:
        ids, vectors = data["ids"], data["E"]
    if field == "dimensions":
        vectors = np.ones((len(ids), 3), dtype="float32") / np.sqrt(3)
    np.savez(path, ids=ids, E=vectors, backbone="different" if field == "backbone" else "test")
    with pytest.raises(ValueError, match=field):
        pack_bundle(pool, str(candidates), str(references), tmp_path / "bundle")
    assert not (tmp_path / "bundle").exists()


def test_replay_rejects_different_library(embedding_build, webapp_dir, monkeypatch):
    pool, record, served, candidates, references = embedding_build
    data = json.loads(record.read_text())
    assert data["labelfirst"]["version"]
    monkeypatch.setattr("what_to_id.replay.labelfirst_provenance", lambda: {"version": "wrong"})
    with pytest.raises(ReplayError, match="LabelFirst"):
        replay(
            pool,
            record,
            served,
            webapp_dir,
            key=KEY,
            embeddings=str(candidates),
            reference_embeddings=str(references),
        )


def test_bundle_requires_current_pool_coverage(embedding_build, tmp_path):
    from what_to_id.artifacts import pack_bundle

    pool, _, _, candidates, references = embedding_build
    path = candidates / "emb_Aves.npz"
    with np.load(path) as data:
        ids, vectors = data["ids"][1:], data["E"][1:]
    np.savez(path, ids=ids, E=vectors, backbone="test")
    with pytest.raises(ValueError, match="lacks 1 pool IDs"):
        pack_bundle(pool, str(candidates), str(references), tmp_path / "bundle")


def test_bundle_rejects_unknown_taxon_group(embedding_build, tmp_path):
    import pandas as pd

    from what_to_id.artifacts import pack_bundle

    pool, _, _, candidates, references = embedding_build
    rows = pd.read_parquet(pool)
    rows.loc[0, "iconic_taxon"] = None
    rows.to_parquet(pool, index=False)
    with pytest.raises(ValueError, match="known taxon group"):
        pack_bundle(pool, str(candidates), str(references), tmp_path / "bundle")
