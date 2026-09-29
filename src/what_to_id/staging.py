"""Resumable per-group photo archives for embedding preparation.

Each ``<group>.tar`` is bound by its ``<group>.json`` status to a digest of exactly the
(id, photo_url) rows that name and fetch its files, so a group survives pool changes elsewhere.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pandas as pd

from what_to_id.embed import stage_images, validate_staged_images

KINDS = ("candidate", "reference")


def staged_rows_digest(rows: pd.DataFrame) -> str:
    """sha256 of the sorted (id, photo_url) pairs that stage_images uses to name and fetch."""
    pairs = sorted(
        (int(i), u if isinstance(u, str) else None)
        for i, u in zip(rows["id"], rows["photo_url"], strict=True)
    )
    return hashlib.sha256(json.dumps(pairs, separators=(",", ":")).encode()).hexdigest()


def _status(path: Path) -> dict | None:
    try:
        saved = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return saved if isinstance(saved, dict) else None


def group_is_staged(out: Path, group: str, rows: pd.DataFrame) -> bool:
    """True when the archive and a status bound to these exact rows show no failures."""
    saved = _status(out / f"{group}.json")
    return (
        (out / f"{group}.tar").is_file()
        and saved is not None
        and saved.get("rows_sha256") == staged_rows_digest(rows)
        and saved.get("expected") == len(rows)
        and saved.get("failures") == []
    )


def _archive(cache: Path, archive: Path) -> None:
    partial = archive.with_suffix(".partial")
    subprocess.run(["tar", "cf", str(partial), "-C", str(cache), "photos"], check=True)
    partial.replace(archive)


def stage_group(
    out: Path, group: str, rows: pd.DataFrame, cache: Path, *, workers: int = 4
) -> None:
    """Fetch only missing photos into ``<group>.tar``; any archive present is resumed."""
    if group_is_staged(out, group, rows):
        return
    archive, status = out / f"{group}.tar", out / f"{group}.json"
    # Only a finished archive gets a status, so a stale one never vouches for new bytes.
    status.unlink(missing_ok=True)
    shutil.rmtree(cache, ignore_errors=True)
    cache.mkdir(parents=True)
    if archive.exists():
        subprocess.run(["tar", "xf", str(archive), "-C", str(cache)], check=True)
    failed = validate_staged_images(stage_images(rows, cache, workers=workers))
    _archive(cache, archive)
    status.write_text(
        json.dumps(
            {"expected": len(rows), "rows_sha256": staged_rows_digest(rows), "failures": failed}
        )
    )
    shutil.rmtree(cache)
    if failed:
        raise RuntimeError(f"{group}: {len(failed)} photos failed, rerun staging before GPU")


def stage(run: Path, sources: dict[str, Path], cache: Path) -> None:
    for kind, source in sources.items():
        out = run / "photos" / kind
        out.mkdir(parents=True, exist_ok=True)
        for group, rows in pd.read_parquet(source).groupby("iconic_taxon", sort=True):
            stage_group(out, str(group), rows, cache)


def check(run: Path, sources: dict[str, Path]) -> None:
    """Refuse preparation unless every group archive is complete for its current rows."""
    for kind, source in sources.items():
        for group, rows in pd.read_parquet(source).groupby("iconic_taxon", sort=True):
            if not group_is_staged(run / "photos" / kind, str(group), rows):
                raise ValueError(f"{kind} photo archive for {group} is missing or stale")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("stage", "check"))
    parser.add_argument("run", type=Path)
    parser.add_argument("pool", type=Path)
    parser.add_argument("reference", type=Path)
    parser.add_argument("--cache", type=Path, default=Path("stage"))
    args = parser.parse_args(argv)
    sources = dict(zip(KINDS, (args.pool, args.reference), strict=True))
    if args.command == "stage":
        stage(args.run, sources, args.cache)
    else:
        check(args.run, sources)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
