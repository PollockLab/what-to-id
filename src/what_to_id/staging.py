"""Resumable per-group photo archives for embedding preparation.

Each ``<group>.tar`` is bound by its ``<group>.json`` status to a digest of exactly the
(id, photo_url) rows that name and fetch its files, so a group survives pool changes elsewhere.
Candidate photos unfetchable from either host are excluded before assignment, up to
MAX_UNFETCHABLE_FRACTION of a group; the frozen reference must stage completely.
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
from what_to_id.manifest import sha256_file

KINDS = ("candidate", "reference")
MAX_UNFETCHABLE_FRACTION = 0.001
LIMITS = {"candidate": MAX_UNFETCHABLE_FRACTION, "reference": 0.0}


def staged_rows_digest(rows: pd.DataFrame) -> str:
    """sha256 of the sorted (id, photo_url) pairs that stage_images uses to name and fetch."""
    pairs = sorted(
        (int(i), u if isinstance(u, str) else None)
        for i, u in zip(rows["id"], rows["photo_url"], strict=True)
    )
    return hashlib.sha256(json.dumps(pairs, separators=(",", ":")).encode()).hexdigest()


def within_limit(failed: int, expected: int, fraction: float) -> bool:
    return failed == 0 or failed / expected <= fraction


def _status(path: Path) -> dict | None:
    try:
        saved = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return saved if isinstance(saved, dict) else None


def staged_failures(out: Path, group: str, rows: pd.DataFrame, fraction: float) -> list | None:
    """Failed ids of a complete archive bound to these exact rows, or None if not staged."""
    saved = _status(out / f"{group}.json")
    if (
        not (out / f"{group}.tar").is_file()
        or saved is None
        or saved.get("rows_sha256") != staged_rows_digest(rows)
        or saved.get("expected") != len(rows)
        or not isinstance(saved.get("failures"), list)
    ):
        return None
    failed = sorted({int(obs_id) for obs_id, _ in saved["failures"]})
    if not within_limit(len(failed), len(rows), fraction) or set(failed) - set(rows["id"]):
        return None
    return failed


def _archive(cache: Path, archive: Path) -> None:
    partial = archive.with_suffix(".partial")
    subprocess.run(["tar", "cf", str(partial), "-C", str(cache), "photos"], check=True)
    partial.replace(archive)


def stage_group(
    out: Path,
    group: str,
    rows: pd.DataFrame,
    cache: Path,
    *,
    fraction: float = MAX_UNFETCHABLE_FRACTION,
    workers: int = 4,
) -> None:
    """Fetch only missing photos into ``<group>.tar``; any archive present is resumed."""
    if staged_failures(out, group, rows, fraction) is not None:
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
    if not within_limit(len(failed), len(rows), fraction):
        raise RuntimeError(
            f"{group}: {len(failed)} of {len(rows)} photos failed, above the "
            f"{fraction:.1%} exclusion limit; rerun staging before GPU"
        )


def stage(run: Path, sources: dict[str, Path], cache: Path) -> None:
    for kind, source in sources.items():
        out = run / "photos" / kind
        out.mkdir(parents=True, exist_ok=True)
        for group, rows in pd.read_parquet(source).groupby("iconic_taxon", sort=True):
            stage_group(out, str(group), rows, cache, fraction=LIMITS[kind])


def check(run: Path, sources: dict[str, Path]) -> Path:
    """Refuse stale or incomplete archives; return the candidate pool preparation must cover.

    Unfetchable candidates are listed in ``run/excluded.json`` and dropped from
    ``run/pool.eligible.parquet``; without exclusions the original pool is returned unchanged.
    """
    excluded: dict[str, list[int]] = {}
    for kind, source in sources.items():
        for group, rows in pd.read_parquet(source).groupby("iconic_taxon", sort=True):
            failed = staged_failures(run / "photos" / kind, str(group), rows, LIMITS[kind])
            if failed is None:
                raise ValueError(f"{kind} photo archive for {group} is missing or stale")
            if failed:
                excluded[str(group)] = failed
    pool = eligible = sources["candidate"]
    derived = run / "pool.eligible.parquet"
    if excluded:
        rows = pd.read_parquet(pool)
        dropped = {obs_id for ids in excluded.values() for obs_id in ids}
        partial = derived.with_name(derived.name + ".partial")
        rows[~rows["id"].isin(dropped)].to_parquet(partial, index=False)
        partial.replace(derived)
        eligible = derived
    else:
        derived.unlink(missing_ok=True)
    record = {
        "schema_version": 1,
        "pool_sha256": sha256_file(pool),
        "eligible_pool_sha256": sha256_file(eligible),
        "max_unfetchable_fraction": MAX_UNFETCHABLE_FRACTION,
        "excluded": excluded,
    }
    _write_atomic(run / "excluded.json", json.dumps(record, indent=2, sort_keys=True) + "\n")
    return eligible


def _write_atomic(path: Path, text: str) -> None:
    partial = path.with_name(path.name + ".partial")
    partial.write_text(text)
    partial.replace(path)


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
        print(check(args.run, sources))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
