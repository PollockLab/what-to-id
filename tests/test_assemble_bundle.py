"""The daily bundle is assembled from a float16 base and the atlas deltas, latest vector winning."""

import json

import numpy as np
import pytest

from what_to_id.arms import load_embeddings
from what_to_id.artifacts import load_bundle
from what_to_id.assemble_bundle import assemble, main

from .conftest import make_pool

DIM = 8


def vec(seed: int, scale: float = 3.0) -> np.ndarray:
    return (np.random.default_rng(seed).normal(size=DIM) * scale).astype(np.float16)


def unit(v: np.ndarray) -> np.ndarray:
    v = v.astype(np.float32)
    return v / np.linalg.norm(v)


def save(path, ids, seeds) -> None:
    np.savez(path, ids=np.asarray(ids, dtype=np.int64), E=np.stack([vec(s) for s in seeds]))


@pytest.fixture
def inputs(tmp_path):
    pool = make_pool(60, groups=["Aves", "Insecta"])
    pool_path = tmp_path / "pool.parquet"
    pool.to_parquet(pool_path, index=False)
    aves = sorted(pool.loc[pool["iconic_taxon"] == "Aves", "id"])
    insecta = sorted(pool.loc[pool["iconic_taxon"] == "Insecta", "id"])
    base, deltas, ref = tmp_path / "base", tmp_path / "deltas", tmp_path / "ref"
    for d in (base, deltas, ref):
        d.mkdir()
    (base / "base_manifest.json").write_text('{"files": {}}')
    # Base holds every Aves id but the last three (one of them also lands in the deltas), and
    # every Insecta id; the very last Aves id is in no source.
    save(base / "base_Aves.npz", aves[:-3], [i for i in aves[:-3]])
    save(base / "base_Insecta.npz", insecta, [i for i in insecta])
    overlap, twice, delta_only, missing = aves[0], aves[-3], aves[-2], aves[-1]
    # Seeds 10_000+ mark delta vectors, so a wrong winner is a different vector.
    save(deltas / "raw-delta-20261001.npz", [overlap, twice, delta_only], [10_001, 10_002, 10_003])
    save(deltas / "raw-delta-20261002-0900.npz", [twice, 5], [10_004, 10_005])
    for group in ("Aves", "Insecta"):
        np.savez(
            ref / f"emb_{group}_bioclip25.npz",
            ids=np.arange(3),
            E=np.eye(DIM, dtype=np.float32)[:3],
            backbone="bioclip25",
        )
    return {
        "pool": pool_path,
        "base": base,
        "deltas": deltas,
        "reference": str(ref / "emb_{group}_bioclip25.npz"),
        "out": tmp_path / "work" / "bundle",
        "ids": {
            "overlap": overlap,
            "twice": twice,
            "delta_only": delta_only,
            "missing": missing,
            "aves": aves,
        },
    }


def run(inputs, **kwargs):
    return assemble(
        inputs["pool"],
        inputs["base"],
        inputs["deltas"],
        inputs["reference"],
        inputs["out"],
        **kwargs,
    )


def test_assembles_latest_vector_as_float32_unit_rows(inputs):
    ids = inputs["ids"]
    counts = run(inputs, max_uncovered_share=0.5)
    assert counts == {"Aves": 1, "Insecta": 0}
    candidates, _ = load_bundle(inputs["out"])
    got_ids, E, backbone = load_embeddings(candidates["Aves"])
    assert E.dtype == np.float32 and backbone == "bioclip25"
    row = dict(zip(got_ids.tolist(), E, strict=True))
    assert np.allclose(row[ids["overlap"]], unit(vec(10_001)), atol=1e-6)  # delta beats base
    assert np.allclose(row[ids["twice"]], unit(vec(10_004)), atol=1e-6)  # later delta wins
    assert np.allclose(row[ids["delta_only"]], unit(vec(10_003)), atol=1e-6)
    other = ids["aves"][1]
    assert np.allclose(row[other], unit(vec(other)), atol=1e-6)  # untouched base row
    assert ids["missing"] not in row


def test_uncovered_ids_are_reported_and_left_out_of_the_pool(inputs):
    import pandas as pd

    run(inputs, max_uncovered_share=0.5)
    report = json.loads((inputs["out"].parent / "uncovered.json").read_text())
    assert report == {
        "schema_version": 1,
        "ids": [inputs["ids"]["missing"]],
        "by_group": {"Aves": 1},
    }
    served = pd.read_parquet(inputs["out"] / "pool.parquet")
    assert inputs["ids"]["missing"] not in set(served["id"])
    assert len(served) == len(pd.read_parquet(inputs["pool"])) - 1
    preparation = json.loads((inputs["out"] / "preparation.json").read_text())
    assert set(preparation["deltas"]) == {"raw-delta-20261001.npz", "raw-delta-20261002-0900.npz"}
    assert len(preparation["base_manifest_sha256"]) == 64


def test_too_many_uncovered_fails_naming_the_group(inputs):
    with pytest.raises(SystemExit, match=r"Aves has 1 of \d+ .*atlas is behind"):
        run(inputs)
    assert not inputs["out"].exists()
    assert (inputs["out"].parent / "uncovered.json").exists()


def test_zero_vector_is_rejected(inputs):
    np.savez(
        inputs["deltas"] / "raw-delta-20261003.npz",
        ids=np.array([inputs["ids"]["overlap"]]),
        E=np.zeros((1, DIM), dtype=np.float16),
    )
    with pytest.raises(ValueError, match="finite and nonzero"):
        run(inputs, max_uncovered_share=0.5)


def test_cli_exits_nonzero_on_failure(inputs, capsys):
    argv = [
        "--pool",
        str(inputs["pool"]),
        "--base",
        str(inputs["base"]),
        "--deltas",
        str(inputs["deltas"]),
        "--reference-embeddings",
        inputs["reference"],
        "--out",
        str(inputs["out"]),
    ]
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code != 0
    assert main([*argv, "--max-uncovered-share", "0.5"]) == 0


def test_daily_fetch_embeddings_assembles_from_release_assets(inputs, tmp_path):
    import os
    import shutil
    import subprocess
    import sys
    from pathlib import Path

    save(inputs["deltas"] / "raw-delta-20261003.npz", [inputs["ids"]["missing"]], [10_006])
    state = tmp_path / "state"
    state.mkdir()
    shutil.copyfile(inputs["pool"], state / "pool.parquet")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    gh = binaries / "gh"
    gh.write_text(
        f"#!{sys.executable}\n"
        "import fnmatch, os, shutil, sys\nfrom pathlib import Path\n"
        "assert sys.argv[1:3] == ['release', 'download']\n"
        "destination = Path(sys.argv[sys.argv.index('-D') + 1])\n"
        "pattern = sys.argv[sys.argv.index('-p') + 1]\n"
        "for directory in os.environ['TEST_ASSET_DIRS'].split(os.pathsep):\n"
        "    for source in Path(directory).iterdir():\n"
        "        if fnmatch.fnmatch(source.name, pattern):\n"
        "            shutil.copyfile(source, destination / source.name)\n"
    )
    gh.chmod(0o755)
    bundle = tmp_path / "bundle"
    env = {
        **os.environ,
        "PATH": str(binaries) + os.pathsep + os.environ["PATH"],
        "PYTHON": sys.executable,
        "OFFLINE": "1",
        "STATE_DIR": str(state),
        "EMBEDDING_RELEASE": "test-release",
        "EMBEDDING_BUNDLE": str(bundle),
        "TEST_ASSET_DIRS": os.pathsep.join(
            str(d) for d in (inputs["base"], inputs["deltas"], Path(inputs["reference"]).parent)
        ),
    }
    env.pop("REFERENCE_EMBEDDINGS", None)
    result = subprocess.run(
        ["bash", "scripts/daily.sh", "fetch-embeddings"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    candidates, _ = load_bundle(bundle)
    assert set(candidates) == {"Aves", "Insecta"}
