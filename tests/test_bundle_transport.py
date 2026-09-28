import json

import numpy as np
import pandas as pd
import pytest

from what_to_id.artifacts import load_bundle, pack_bundle
from what_to_id.bundle_transport import MANIFEST, restore, stage_release


@pytest.fixture
def bundle(tmp_path):
    pool = tmp_path / "source.parquet"
    pd.DataFrame({"id": [1], "iconic_taxon": ["Aves"]}).to_parquet(pool)
    vectors = tmp_path / "vectors.npz"
    np.savez(vectors, ids=[1], E=np.array([[1.0, 0.0]]), backbone="bioclip25")
    preparation = tmp_path / "preparation.json"
    preparation.write_text('{"model_revision": "fixture"}')
    return pack_bundle(
        pool, str(vectors), str(vectors), tmp_path / "bundle", preparation=preparation
    )


def test_transport_roundtrip_is_byte_identical_and_excludes_strays(bundle, tmp_path):
    originals = {path.name: path.read_bytes() for path in bundle.iterdir()}
    (bundle / "private-stray.txt").write_text("must not export")
    assets = stage_release(bundle, tmp_path / "assets", part_bytes=257)
    record = json.loads((assets / MANIFEST).read_text())
    assert {file["file"] for file in record["files"]} == set(originals)
    assert any(len(file["parts"]) > 1 for file in record["files"])
    assert all(path.stat().st_size <= 257 for path in assets.glob("*.part"))
    restored = restore(assets, tmp_path / "restored")
    assert {path.name: path.read_bytes() for path in restored.iterdir()} == originals
    load_bundle(restored)


@pytest.mark.parametrize(
    "damage",
    ["missing", "corrupt", "original_hash", "part_path", "file_path", "symlink", "duplicate"],
)
def test_restore_refuses_damaged_or_unsafe_transport(bundle, tmp_path, damage):
    assets = stage_release(bundle, tmp_path / "assets", part_bytes=257)
    record = json.loads((assets / MANIFEST).read_text())
    file = record["files"][0]
    part = file["parts"][0]
    path = assets / part["file"]
    if damage == "missing":
        path.unlink()
    elif damage == "corrupt":
        data = bytearray(path.read_bytes())
        data[0] ^= 1
        path.write_bytes(data)
    elif damage == "original_hash":
        file["sha256"] = "0" * 64
    elif damage == "part_path":
        part["file"] = "../outside"
    elif damage == "file_path":
        file["file"] = "../outside"
    elif damage == "symlink":
        outside = tmp_path / "outside"
        path.rename(outside)
        path.symlink_to(outside)
    else:
        record["files"].append(file)
    (assets / MANIFEST).write_text(json.dumps(record))
    out = tmp_path / "restored"
    with pytest.raises(ValueError):
        restore(assets, out)
    assert not out.exists()
    assert not (tmp_path / "outside").exists() or damage == "symlink"


def test_transport_refuses_existing_destinations(bundle, tmp_path):
    assets = stage_release(bundle, tmp_path / "assets")
    with pytest.raises(ValueError, match="already exists"):
        stage_release(bundle, assets)
    with pytest.raises(ValueError, match="already exists"):
        restore(assets, bundle)


def test_restore_checks_embedded_bundle_manifest(bundle, tmp_path):
    assets = stage_release(bundle, tmp_path / "assets")
    record = json.loads((assets / MANIFEST).read_text())
    record["files"] = [file for file in record["files"] if file["file"] != "pool.parquet"]
    (assets / MANIFEST).write_text(json.dumps(record))
    with pytest.raises(ValueError, match="pool.parquet"):
        restore(assets, tmp_path / "restored")
