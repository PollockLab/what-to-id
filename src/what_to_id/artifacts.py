"""Resolve and fingerprint the files required to reproduce a batch build."""

from __future__ import annotations

from pathlib import Path

from what_to_id.arms import load_embeddings
from what_to_id.manifest import sha256_file


def embedding_paths(spec: str | None, groups: list[str]) -> dict[str, Path]:
    """Resolve --embeddings (a `{group}` pattern or a directory) to group -> npz path."""
    if spec is None:
        return {}
    out: dict[str, Path] = {}
    if "{group}" in spec:
        for g in groups:
            p = Path(spec.format(group=g))
            if p.exists():
                out[g] = p
    else:
        d = Path(spec)
        if d.is_dir():
            for g in groups:
                # The embed step writes emb_<group>_<backbone>.npz; emb_<group>.npz also works.
                hits = sorted(d.glob(f"emb_{g}_*.npz")) or sorted(d.glob(f"emb_{g}.npz"))
                if len(hits) > 1:
                    names = ", ".join(h.name for h in hits)
                    raise SystemExit(
                        f"{d}: several embedding files for {g} ({names}); pass a {{group}} pattern"
                    )
                if hits:
                    out[g] = hits[0]
        elif d.exists():
            out = {"*": d}
    if not out:
        raise FileNotFoundError(f"no embedding npz files found from {spec!r}")
    return out


def describe_files(paths: dict[str, Path], *, embeddings: bool = False) -> dict[str, dict]:
    """Record content identity, never local paths or experiment assignments."""
    records = {}
    for group, path in sorted(paths.items()):
        entry = {"sha256": sha256_file(path)}
        if embeddings:
            ids, vectors, backbone = load_embeddings(path)
            entry.update(rows=len(ids), dimensions=vectors.shape[1], backbone=backbone or None)
        records[group] = entry
    return records


def build_inputs(
    embeddings: dict[str, Path],
    references: dict[str, Path],
    surprise_scores: str | None = None,
    sinr_scores: str | None = None,
) -> dict[str, dict]:
    inputs = {}
    for role, paths in (("embeddings", embeddings), ("reference_embeddings", references)):
        if paths:
            inputs[role] = describe_files(paths, embeddings=True)
    for role, path in (("surprise_scores", surprise_scores), ("sinr_scores", sinr_scores)):
        if path:
            inputs[role] = describe_files({"*": Path(path)})
    return inputs


def load_bundle(root: str | Path) -> tuple[dict[str, Path], dict[str, Path]]:
    """Verify a portable embedding bundle before exposing its files to a build."""
    import json

    root = Path(root)
    manifest = json.loads((root / "embedding_bundle.json").read_text())
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported embedding bundle schema_version")
    expected = manifest.get("files", {})
    if set(expected) != {"embeddings", "reference_embeddings"}:
        raise ValueError("bundle needs candidate and reference embeddings")
    result = []
    for role in ("embeddings", "reference_embeddings"):
        paths = {}
        if not expected[role]:
            raise ValueError(f"bundle has no {role}")
        for group, info in expected[role].items():
            filename = info["file"]
            if not isinstance(filename, str) or Path(filename).name != filename:
                raise ValueError("bundle files must be plain filenames")
            path = root / filename
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"missing or symlinked embedding bundle file: {filename}")
            if describe_files({group: path}, embeddings=True)[group] != {
                k: v for k, v in info.items() if k != "file"
            }:
                raise ValueError(f"embedding bundle file does not match its record: {filename}")
            paths[group] = path
        result.append(paths)
    candidates, references = (expected[role] for role in ("embeddings", "reference_embeddings"))
    for group in set(candidates) | set(references):
        if group == "*":
            continue
        candidate = candidates.get(group, candidates.get("*"))
        reference = references.get(group, references.get("*"))
        _check_pair(candidate, reference, group)
    if "*" in candidates and "*" in references:
        _check_pair(candidates["*"], references["*"], "*")
    return result[0], result[1]


def _check_pair(candidate: dict | None, reference: dict | None, group: str) -> None:
    if candidate is None or reference is None:
        raise ValueError(f"bundle is missing paired embeddings for {group}")
    if candidate["dimensions"] != reference["dimensions"]:
        raise ValueError(f"candidate and reference dimensions differ for {group}")
    if (
        candidate["backbone"]
        and reference["backbone"]
        and candidate["backbone"] != reference["backbone"]
    ):
        raise ValueError(f"candidate and reference backbones differ for {group}")


def resolve_embeddings(
    groups: list[str], embeddings: str | None, reference: str | None, bundle: str | None
) -> tuple[dict[str, Path], dict[str, Path]]:
    if bundle:
        if embeddings or reference:
            raise ValueError("use --embedding-bundle or individual embedding inputs, not both")
        candidates, references = load_bundle(bundle)
        for paths in (candidates, references):
            if "*" not in paths and set(groups) - set(paths):
                raise ValueError("embedding bundle is missing a pool taxon group")
        return candidates, references
    return embedding_paths(embeddings, groups), embedding_paths(reference, groups)


def validate_coverage(pool, candidates: dict[str, Path], references: dict[str, Path]) -> None:
    """A production bundle must support every pool row without ranking fallbacks."""
    if pool["iconic_taxon"].isna().any():
        raise ValueError("embedding bundle requires a known taxon group for every pool row")
    for group, rows in pool.groupby("iconic_taxon"):
        candidate_ids, _, _ = load_embeddings(candidates.get(group, candidates.get("*")))
        reference_ids, _, _ = load_embeddings(references.get(group, references.get("*")))
        missing = set(rows["id"]) - set(candidate_ids)
        if missing:
            raise ValueError(
                f"embedding bundle lacks {len(missing)} pool IDs for {group}; "
                "prepare a fresh bundle"
            )
        if not len(reference_ids):
            raise ValueError(f"embedding bundle has no reference rows for {group}")


def pack_bundle(pool: str | Path, embeddings: str, reference: str, out: str | Path) -> Path:
    """Copy complete prepared caches into a portable, fingerprinted release asset set."""
    import json
    import re
    import shutil
    import tempfile

    import pandas as pd

    out = Path(out)
    if out.exists():
        raise ValueError(f"bundle destination already exists: {out}")
    groups = sorted(
        pd.read_parquet(pool, columns=["iconic_taxon"])["iconic_taxon"].dropna().unique()
    )
    if not groups:
        raise ValueError("pool has no taxon groups")
    candidates, references = resolve_embeddings(groups, embeddings, reference, None)
    for paths in (candidates, references):
        if "*" not in paths and set(groups) - set(paths):
            raise ValueError("embedding bundle is missing a pool taxon group")
    validate_coverage(pd.read_parquet(pool), candidates, references)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent) as tmp:
        stage = Path(tmp) / "bundle"
        stage.mkdir()
        files = {}
        for role, paths in (("embeddings", candidates), ("reference_embeddings", references)):
            if "*" not in paths and set(groups) - set(paths):
                raise ValueError(f"{role} is missing a pool taxon group")
            files[role] = {}
            for group, path in sorted(paths.items()):
                tag = "all" if group == "*" else group
                if not re.fullmatch(r"[A-Za-z0-9_]+", tag):
                    raise ValueError(f"invalid taxon group filename: {tag!r}")
                filename = f"{role}_{tag}.npz"
                shutil.copyfile(path, stage / filename)
                files[role][group] = {
                    "file": filename,
                    **describe_files({group: stage / filename}, embeddings=True)[group],
                }
        (stage / "embedding_bundle.json").write_text(
            json.dumps({"schema_version": 1, "files": files}, indent=2, sort_keys=True) + "\n"
        )
        load_bundle(stage)
        stage.rename(out)
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    pack = sub.add_parser("pack", help="package precomputed caches for a versioned release")
    for flag in ("pool", "embeddings", "reference-embeddings", "out"):
        pack.add_argument("--" + flag, required=True)
    verify = sub.add_parser("verify", help="verify all files in a downloaded bundle")
    verify.add_argument("bundle")
    args = parser.parse_args(argv)
    try:
        if args.command == "pack":
            pack_bundle(args.pool, args.embeddings, args.reference_embeddings, args.out)
        else:
            load_bundle(args.bundle)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"embedding bundle: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
