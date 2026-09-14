"""what-to-id command line: `what-to-id build` composes batches from a frozen pool."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from what_to_id.arms import Arm, build_arm, load_embeddings
from what_to_id.assign import assign, assign_keyed
from what_to_id.batches import build_batches, identify_url
from what_to_id.cells import WEBAPP_DIR, score_records
from what_to_id.embed import emb_cache_path
from what_to_id.manifest import (
    Manifest,
    blind_labels,
    blind_labels_keyed,
    key_fingerprint,
    key_from_env,
    sha256_file,
    write_manifest,
)
from what_to_id.page import write_site
from what_to_id.page_rotation import write_rotation_site
from what_to_id.served_log import append_served, served_rows
from what_to_id.signals import batch_signals, signals_by_batch

log = logging.getLogger("what_to_id")


def _iso_date(s: str) -> str:
    try:
        return date.fromisoformat(s).isoformat()
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got {s!r}") from e


def _embedding_paths(spec: str | None, groups: list[str]) -> dict[str, Path]:
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
                hits = sorted(d.glob(emb_cache_path(d, g, "*").name)) or sorted(
                    d.glob(f"emb_{g}.npz")
                )
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


def _make_arms(
    names: list[str], batch_size: int, emb: dict[str, Path], ref: dict[str, Path]
) -> dict[str, Arm]:
    arms: dict[str, Arm] = {}
    for n in names:
        if n == "similarity":
            if not emb:
                raise SystemExit("--embeddings is required for the similarity arm")
            arms[n] = build_arm(n, embeddings=emb, batch_size=batch_size)
        elif n == "novelty":
            if not emb or not ref:
                raise SystemExit(
                    "--embeddings and --reference-embeddings are required for the novelty arm"
                )
            arms[n] = build_arm(n, embeddings=emb, reference=ref)
        else:
            arms[n] = build_arm(n)
    return arms


def _sha_if_single(paths: dict[str, Path]) -> str | None:
    """sha256 of the embedding file when there is exactly one; per-group files are not hashed."""
    if len(paths) != 1:
        return None
    return sha256_file(next(iter(paths.values())))


def build(args: argparse.Namespace) -> Path:
    pool_path = Path(args.pool)
    out = Path(args.out)
    pool = pd.read_parquet(pool_path)
    if pool.empty:
        raise SystemExit(f"{pool_path}: pool is empty")
    if pool["id"].duplicated().any():
        raise SystemExit(f"{pool_path}: duplicate ids")
    arm_names = [a.strip() for a in args.arms.split(",") if a.strip()]
    log.info("pool %s: %d rows", pool_path, len(pool))

    pool["cell_score"] = score_records(pool, webapp_dir=Path(args.webapp_dir)).to_numpy()
    log.info("cell_score present for %d rows", int(pool["cell_score"].notna().sum()))

    key = key_from_env(args.key_env) if args.key_env else None
    if key is None:
        assign_df = assign(pool, arm_names, seed=args.seed)
        labels = blind_labels(arm_names, args.seed)
    else:
        assign_df = assign_keyed(pool, arm_names, key=key)
        labels = blind_labels_keyed(arm_names, key)
    # A keyed build runs in public CI next to a public served log: per-arm counts in the log
    # would give the letter-to-list map away, so it names lists by letter only.
    shown = labels if key is not None else {a: a for a in arm_names}
    groups = sorted(pool["iconic_taxon"].dropna().astype(str).unique())
    emb = _embedding_paths(args.embeddings, groups)
    ref = _embedding_paths(args.reference_embeddings, groups)
    arms = _make_arms(arm_names, args.batch_size, emb, ref)
    batches_df = build_batches(
        pool, assign_df, arms, size=args.batch_size, seed=args.seed, max_batches=args.max_batches
    )

    for (arm, group), n in batches_df.groupby(["arm", "group"])["id"].size().items():
        nb = batches_df[(batches_df["arm"] == arm) & (batches_df["group"] == group)][
            "batch_id"
        ].nunique()
        log.info("%-11s %-16s %5d records in %3d batches", shown[arm], group, n, nb)

    emb_sha = _sha_if_single(emb)
    ref_sha = _sha_if_single(ref)
    backbone = None
    if emb:
        first = next(iter(sorted(emb.values(), key=str)))
        backbone = load_embeddings(first)[2] or None
    signals: dict[str, dict] = {}
    if emb:
        sig_df = batch_signals(batches_df, emb, ref or None)
        signals = signals_by_batch(sig_df)
        per_arm = sig_df.merge(
            batches_df[["batch_id", "arm"]].drop_duplicates(), on="batch_id"
        ).groupby("arm")[["cohesion", "novelty"]]
        for arm, row in per_arm.mean().iterrows():
            log.info(
                "%-11s mean cohesion %.3f  mean novelty %.3f",
                shown[arm],
                row["cohesion"],
                row["novelty"],
            )
    batches = {}
    for bid, sub in batches_df.groupby("batch_id", sort=True):
        ids = [int(i) for i in sub.sort_values("position")["id"]]
        batches[bid] = {
            "arm": str(sub["arm"].iloc[0]),
            "group": str(sub["group"].iloc[0]),
            "url": identify_url(ids),
            "ids": ids,
            **signals.get(bid, {}),
        }
    m = Manifest(
        freeze=args.freeze,
        d1=args.d1,
        seed=int(args.seed),
        batch_size=int(args.batch_size),
        arms=arm_names,
        arm_labels=labels,
        pool_sha256=sha256_file(pool_path),
        pool_rows=int(len(pool)),
        embeddings_sha256=emb_sha,
        reference_sha256=ref_sha,
        backbone=backbone,
        max_batches=args.max_batches,
        served_rows=int(len(batches_df)),
        batches=batches,
        design=args.design,
        assignment="keyed" if key is not None else "stratified",
        key_fingerprint=key_fingerprint(key) if key is not None else None,
    )
    out.mkdir(parents=True, exist_ok=True)
    write_manifest(m, out / "manifest.json")
    assign_df.to_parquet(out / "assign.parquet", index=False)
    batches_df.to_parquet(out / "batches.parquet", index=False)
    if args.design == "rotation":
        write_rotation_site(out / "site", m)
    else:
        write_site(out / "site", m, batches_df, pool=pool)
    if args.served_log:
        rows = served_rows(batches_df, labels, pool, args.freeze)
        total = append_served(args.served_log, rows)
        log.info("served log %s: %d rows today, %d in all", args.served_log, len(rows), len(total))
    log.info("wrote %s (%d batches)", out, len(batches))
    return out


def make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="what-to-id")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="compose batches, manifest and site from a frozen pool")
    b.add_argument("--pool", default="data/pool.parquet")
    b.add_argument("--freeze", type=_iso_date, required=True, help="pool freeze date YYYY-MM-DD")
    b.add_argument("--d1", type=_iso_date, required=True, help="first blitz day YYYY-MM-DD")
    b.add_argument("--seed", type=int, default=0)
    b.add_argument("--batch-size", type=int, default=120)
    b.add_argument(
        "--max-batches",
        type=int,
        default=None,
        help="serve only the first N batches per arm and taxon group",
    )
    b.add_argument("--arms", default="recency,gap_first", help="comma-separated arm names")
    b.add_argument("--embeddings", default=None, help="npz path pattern with {group}, or a dir")
    b.add_argument(
        "--reference-embeddings",
        default=None,
        help="Research Grade reference npz pattern with {group}, or a dir (novelty arm)",
    )
    b.add_argument(
        "--webapp-dir", default=str(WEBAPP_DIR), help="where-to-blitz cluster_results/ca"
    )
    b.add_argument(
        "--design",
        choices=["sets", "rotation"],
        default="sets",
        help="'sets' (default) pages one list per browser; 'rotation' cycles every identifier "
        "through all lists",
    )
    b.add_argument(
        "--key-env",
        default=None,
        metavar="NAME",
        help="assign lists by a keyed hash of the record id, with the hex key read from the "
        "environment variable NAME, so a record keeps its list across daily builds",
    )
    b.add_argument(
        "--served-log",
        default=None,
        help="append this build's served records, by list letter, to this parquet",
    )
    b.add_argument("--out", default="out")
    b.set_defaults(func=build)
    return p


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be >= 1")
    if args.max_batches is not None and args.max_batches < 1:
        raise SystemExit("--max-batches must be >= 1")
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
