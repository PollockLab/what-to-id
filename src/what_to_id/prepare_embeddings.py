"""Prepare a new bundle from a pool snapshot, reusing unchanged BioCLIP 2.5 rows.

Run embedding preparation separately from daily serving. References remain frozen;
this command never replaces them or publishes a release.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from what_to_id.arms import load_embeddings
from what_to_id.artifacts import embedding_paths, pack_bundle
from what_to_id.embed import emb_cache_path, embed_group, save_embeddings
from what_to_id.manifest import sha256_file

MODEL_REVISION = "6e3d04e3d6522012c88181085c5ae666e14c45cd"
MODEL_HASHES = {
    "open_clip_config.json": "4c131846348300c77b5bee06690b0e94ee85ca9ce9a30a853b36084d00dcd25c",
    "open_clip_model.safetensors": (
        "ac2e37c2f89ef8e6b889176a9a3f418970ad9db15a218bd29e3321e95c46ae97"
    ),
}


def _verify_snapshot(path: Path) -> dict[str, str]:
    hashes = {name: sha256_file(path / name) for name in MODEL_HASHES}
    if hashes != MODEL_HASHES:
        raise ValueError("model snapshot differs from the frozen BioCLIP 2.5 checkpoint")
    return hashes


def verify_reference_cache(cache: Path, source: Path, model_snapshot: Path) -> None:
    """Refuse to reuse reference vectors without matching source/model attestation."""
    files = sorted(cache.glob("*.npz"))
    if not files:
        return
    record = cache / "provenance.json"
    if not record.is_file():
        raise ValueError("reference cache lacks preparation provenance")
    prior = json.loads(record.read_text())
    if (
        prior.get("pool_sha256") != sha256_file(source)
        or prior.get("model_revision") != MODEL_REVISION
        or prior.get("model_sha256") != _verify_snapshot(model_snapshot)
        or prior.get("reference_sha256") != {p.name: sha256_file(p) for p in files}
    ):
        raise ValueError("reference cache differs from its source/model attestation")


def prepare(
    pool: Path,
    *,
    reference_embeddings: str,
    model_snapshot: Path,
    work_dir: Path,
    out: Path,
    previous_pool: Path | None = None,
    candidate_cache: str | None = None,
    previous_preparation: Path | None = None,
    device: str | None = None,
    batch: int = 64,
    photo_cache: Path | None = None,
    checkpoint_dir: Path | None = None,
    reference_pool: Path | None = None,
) -> Path:
    """Reuse only IDs whose group and image URL match the previous snapshot.

    A work directory resumes only its original inputs. Failed image downloads leave
    the work cache reusable, but complete coverage is required to pack a bundle.
    URL identity cannot detect changed image bytes served at an unchanged URL.
    """
    if (previous_pool is None) != (candidate_cache is None):
        raise ValueError("pass previous_pool and candidate_cache together")
    if (candidate_cache is None) != (previous_preparation is None):
        raise ValueError("cache reuse requires its previous preparation record")
    if out.exists():
        raise ValueError(f"bundle destination already exists: {out}")
    rows = pd.read_parquet(pool)
    required = {"id", "iconic_taxon", "photo_url", "lat", "lon"}
    if required - set(rows):
        raise ValueError(f"pool lacks columns: {sorted(required - set(rows))}")
    if rows.empty or rows.id.duplicated().any() or rows.iconic_taxon.isna().any():
        raise ValueError("pool must be nonempty with unique IDs and known taxon groups")
    groups = sorted(rows.iconic_taxon.unique())
    references = embedding_paths(reference_embeddings, groups)
    if "*" not in references and set(groups) - set(references):
        raise ValueError("frozen reference is missing a pool taxon group")
    for group, path in references.items():
        ids, _, backbone = load_embeddings(path)
        if backbone != "bioclip25" or not len(ids):
            raise ValueError(f"frozen reference for {group} must contain BioCLIP 2.5 rows")
    if reference_pool is not None:
        reference_rows = pd.read_parquet(reference_pool)
        for group, subset in reference_rows[reference_rows.iconic_taxon.isin(groups)].groupby(
            "iconic_taxon", sort=True
        ):
            path = references.get(group, references.get("*"))
            if path is None or not set(subset.id) <= set(load_embeddings(path)[0]):
                raise ValueError(f"frozen reference cache is missing source rows for {group}")
    model_hashes = _verify_snapshot(model_snapshot)
    images = rows[["id", "iconic_taxon", "photo_url"]].sort_values("id")
    runtime = {}
    for package in ("torch", "torchvision", "open_clip_torch", "pillow", "numpy"):
        try:
            runtime[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            runtime[package] = None
    identity = {
        "encoder_runtime": runtime,
        "model_revision": MODEL_REVISION,
        "model_sha256": model_hashes,
        "source_image_identity_sha256": hashlib.sha256(
            images.to_json(orient="records").encode()
        ).hexdigest(),
        "reuse_identity": "observation ID, taxon group and photo URL; image bytes not re-fetched",
        "pool_sha256": sha256_file(pool),
        "reference_pool_sha256": sha256_file(reference_pool) if reference_pool else None,
        "previous_pool_sha256": sha256_file(previous_pool) if previous_pool else None,
        "backbone": "bioclip25",
        "reference_sha256": {g: sha256_file(p) for g, p in references.items()},
    }
    previous = pd.read_parquet(previous_pool) if previous_pool else None
    old_paths = (
        embedding_paths(candidate_cache, sorted(previous.iconic_taxon.unique()))
        if candidate_cache and previous is not None
        else {}
    )
    identity["candidate_sha256"] = {g: sha256_file(p) for g, p in old_paths.items()}
    if previous_preparation is not None:
        prior = json.loads(previous_preparation.read_text())
        if (
            prior.get("model_sha256") != model_hashes
            or prior.get("model_revision") != MODEL_REVISION
            or prior.get("pool_sha256") != identity["previous_pool_sha256"]
            or prior.get("output_candidate_sha256") != identity["candidate_sha256"]
        ):
            raise ValueError("previous cache lacks matching model, pool and output attestation")
    record = work_dir / "preparation.json"
    if work_dir.exists():
        saved = json.loads(record.read_text()) if record.is_file() else {}
        saved.pop("output_candidate_sha256", None)
        if saved != identity:
            raise ValueError("work directory belongs to different preparation inputs")
    else:
        work_dir.mkdir(parents=True)
        record.write_text(json.dumps(identity, indent=2, sort_keys=True) + "\n")
    cache = work_dir / "candidates"
    if photo_cache is not None:
        cache.mkdir(exist_ok=True)
        photos = cache / "photos"
        if not photos.exists():
            photos.symlink_to(photo_cache.resolve(), target_is_directory=True)
    for group, current in rows.groupby("iconic_taxon", sort=True):
        target = emb_cache_path(cache, group, "bioclip25")
        source = old_paths.get(group, old_paths.get("*"))
        if not target.exists() and source is not None and previous is not None:
            ids, vectors, backbone = load_embeddings(source)
            if backbone != "bioclip25":
                raise ValueError(f"previous candidate cache for {group} is not bioclip25")
            unchanged = current.merge(
                previous[["id", "iconic_taxon", "photo_url"]],
                on=["id", "iconic_taxon", "photo_url"],
                how="inner",
                validate="one_to_one",
            ).set_index("id")
            keep = np.isin(ids, unchanged.index)
            if keep.any():
                reused = unchanged.loc[ids[keep]]
                save_embeddings(
                    target,
                    ids=ids[keep],
                    E=vectors[keep],
                    lat=reused.lat.to_numpy(),
                    lon=reused.lon.to_numpy(),
                    backbone="bioclip25",
                    emb_device="reused",
                    failed_ids=[],
                )
        embed_group(
            current,
            backbone="bioclip25",
            cache_dir=cache,
            device=device,
            batch=batch,
            model_snapshot=model_snapshot,
        )
        if checkpoint_dir is not None:
            destination = checkpoint_dir / "candidates" / target.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            partial = destination.with_suffix(".partial")
            shutil.copy2(target, partial)
            partial.replace(destination)
            shutil.copy2(record, checkpoint_dir / record.name)
    candidate_spec = str(cache / "emb_{group}_bioclip25.npz")
    identity["output_candidate_sha256"] = {
        g: sha256_file(p) for g, p in embedding_paths(candidate_spec, groups).items()
    }
    record.write_text(json.dumps(identity, indent=2, sort_keys=True) + "\n")
    return pack_bundle(pool, candidate_spec, reference_embeddings, out, preparation=record)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("pool", "work-dir", "out", "previous-pool", "model-snapshot"):
        parser.add_argument("--" + name, type=Path, required=name != "previous-pool")
    parser.add_argument("--reference-embeddings", required=True)
    parser.add_argument("--reference-pool", type=Path)
    parser.add_argument("--candidate-cache")
    parser.add_argument("--previous-preparation", type=Path)
    parser.add_argument("--device")
    parser.add_argument("--photo-cache", type=Path)
    parser.add_argument("--checkpoint-dir", type=Path)
    parser.add_argument("--batch", type=int, default=64)
    args = parser.parse_args(argv)
    try:
        prepare(**vars(args))
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"embedding preparation: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
