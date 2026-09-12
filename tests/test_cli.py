import json

import numpy as np
import pandas as pd
import pytest

from what_to_id.cli import main
from what_to_id.manifest import validate_manifest

from .conftest import make_pool


def test_build_end_to_end(tmp_path, webapp_dir):
    pool = make_pool(300, seed=5)
    pool_path = tmp_path / "pool.parquet"
    pool.to_parquet(pool_path, index=False)
    out = tmp_path / "out"
    rc = main(
        [
            "build",
            "--pool",
            str(pool_path),
            "--freeze",
            "2026-09-01",
            "--d1",
            "2026-09-15",
            "--seed",
            "3",
            "--batch-size",
            "25",
            "--arms",
            "recency,gap_first",
            "--webapp-dir",
            str(webapp_dir),
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    d = json.loads((out / "manifest.json").read_text())
    validate_manifest(d)
    assert d["pool_rows"] == 300 and d["seed"] == 3 and d["arms"] == ["recency", "gap_first"]
    assert sum(len(b["ids"]) for b in d["batches"].values()) == 300
    a = pd.read_parquet(out / "assign.parquet")
    b = pd.read_parquet(out / "batches.parquet")
    assert len(a) == 300 and len(b) == 300 and b["id"].is_unique
    for name in ["index.html", "arm_A.html", "arm_B.html"]:
        assert (out / "site" / name).exists()
    assert "recency" not in (out / "site" / "index.html").read_text()


def test_build_rejects_bad_date(tmp_path):
    with pytest.raises(SystemExit):
        main(["build", "--freeze", "2026-13-01", "--d1", "2026-09-15", "--pool", "x"])


def test_novelty_requires_reference(tmp_path, webapp_dir):
    pool_path = tmp_path / "pool.parquet"
    pool = make_pool(20)
    pool.to_parquet(pool_path, index=False)
    emb = tmp_path / "emb.npz"
    rng = np.random.default_rng(0)
    E = rng.normal(size=(20, 8)).astype(np.float32)
    E /= np.linalg.norm(E, axis=1, keepdims=True)
    np.savez(emb, ids=pool["id"].to_numpy(), E=E, backbone="synthetic")
    args = [
        "build",
        "--pool",
        str(pool_path),
        "--freeze",
        "2026-09-01",
        "--d1",
        "2026-09-15",
        "--arms",
        "recency,novelty",
        "--embeddings",
        str(emb),
        "--webapp-dir",
        str(webapp_dir),
        "--out",
        str(tmp_path / "o"),
    ]
    with pytest.raises(SystemExit, match="reference"):
        main(args)
    main([*args, "--reference-embeddings", str(emb)])
    d = json.loads((tmp_path / "o" / "manifest.json").read_text())
    assert d["arms"] == ["recency", "novelty"]
    assert d["reference_sha256"] == d["embeddings_sha256"] and d["backbone"] == "synthetic"
    for b in d["batches"].values():
        assert b["n_embedded"] == len(b["ids"])
        assert 0.0 <= b["novelty"] <= 2.0
        if b["n_embedded"] >= 2:
            assert 0.0 <= b["cohesion"] <= 1.0
        else:
            assert b["cohesion"] is None
    label = {v: k for k, v in d["arm_labels"].items()}
    for lab in label:
        html = (tmp_path / "o" / "site" / f"arm_{lab}.html").read_text()
        assert "look-alike 0." in html and "unfamiliar 0." in html and "Look-alike</b>" in html


def test_similarity_requires_embeddings(tmp_path, webapp_dir):
    pool_path = tmp_path / "pool.parquet"
    make_pool(20).to_parquet(pool_path, index=False)
    with pytest.raises((SystemExit, FileNotFoundError)):
        main(
            [
                "build",
                "--pool",
                str(pool_path),
                "--freeze",
                "2026-09-01",
                "--d1",
                "2026-09-15",
                "--arms",
                "recency,similarity",
                "--webapp-dir",
                str(webapp_dir),
                "--out",
                str(tmp_path / "o"),
            ]
        )


def test_embeddings_directory_finds_embed_step_output(tmp_path):
    from what_to_id.cli import _embedding_paths

    (tmp_path / "emb_Aves_bioclip25.npz").touch()
    (tmp_path / "emb_Insecta.npz").touch()
    out = _embedding_paths(str(tmp_path), ["Aves", "Insecta", "Fungi"])
    assert out == {
        "Aves": tmp_path / "emb_Aves_bioclip25.npz",
        "Insecta": tmp_path / "emb_Insecta.npz",
    }
    (tmp_path / "emb_Aves_dinov2.npz").touch()
    with pytest.raises(SystemExit, match="several embedding files for Aves"):
        _embedding_paths(str(tmp_path), ["Aves"])
    with pytest.raises(FileNotFoundError):
        _embedding_paths(str(tmp_path / "empty"), ["Aves"])
