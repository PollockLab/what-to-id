"""Three levels of what to identify, from the BioCLIP text prototypes `confusion.fir_scores` uses.

Each species-ranked Needs ID record has `own` (cosine to its labelled species' text vector),
`other` (best cosine to any other species) and `margin = own - other`. The levels:

- easy: margin above zero and `own` in the top `EASY_TOP_SHARE` of its species, the records that
  sit squarely in their labelled species, for ticking off many quickly;
- taxonomist: margin just below zero, down to `-TAXONOMIST_MARGIN`, where one look-alike species
  is barely ahead of the label: believable, ambiguous between the two, and the look-alike
  has at least `MIN_LOOKALIKE_RECORDS` records (rarer ones are noise for identifiers), counted
  over all BC verifiable observations when `--bc-counts` is given, else over the pool;
- weird: the lowest `WEIRD_SHARE` of max(own, other) within the iconic group, records far from
  every species (hands, eggs, extreme close-ups).

Weird wins over the other two; easy and taxonomist are disjoint by the sign of the margin. Each
level keeps at most `PER_SPECIES` records per species and `CAP` per iconic group, so one species
or group does not fill the page. Rows come in display order: easy and taxonomist interleave
species (one random record of each species, then a second, ...), weird runs farthest first
within each group, the groups taking turns.

    python -m what_to_id.levels --emb E.npy --ids ids.npy --pool pool.parquet \\
        --taxa-names taxa-<sha>.tsv.gz --taxa-vectors taxa-<sha>.f16 --atlas-dir DIR \\
        [--bc-counts bc-verifiable-counts.parquet] [--range-notes range-notes.parquet]

writes `levels.parquet` (`LEVEL_COLUMNS`) next to the atlas index and registers it in its
manifest under ``"levels"``, as `confusion fir` does for the confused pairs.

`--tree taxonomy.json --identify` instead scores every pool record with `what_to_id.identify`
and writes `identify.parquet` under the manifest key ``"identify"``, leaving `levels` alone.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from what_to_id.atlas_index_io import read_manifest, write_manifest
from what_to_id.confusion import MIN_PER_CLASS, fir_scores, read_taxa_vectors

# (key, name, one line for the page)
LEVELS = (
    ("easy", "Clear matches", "These look just like their label. Confirm many in one go."),
    (
        "taxonomist",
        "Close calls",
        "Another species looks almost as likely, or it may be something else. Take a careful look.",
    ),
    ("weird", "Odd shots", "Hard photos: hands, eggs, close-ups. Feeling lucky?"),
)
LEVEL_COLUMNS = (
    "id",
    "taxon_id",
    "taxon_name",
    "iconic_taxon",
    "level",
    "score",
    "looks_like_name",
    "photo_url",
)
# Cut-offs read from the BC Needs ID bundle (1.44M scored rows, `describe` prints them).
# A species' top quarter by `own`: 91.5% of it already has margin > 0, and a quarter still lets
# a species of 4 photos contribute its best one.
EASY_TOP_SHARE = 0.25
# The quarter of negative margins nearest zero (their 75th percentile is -0.020); at the median
# negative margin, -0.047, the look-alike clearly leads and the label stops being believable.
TAXONOMIST_MARGIN = 0.02
# The bottom 2% per group by max(own, other) (0.42 for Aves to 0.56 for Fungi, against a median
# of 0.64): only the small groups reach this cut, the big ones fill `CAP` farthest first.
WEIRD_SHARE = 0.02
# A look-alike with fewer records is dropped: 5x `MIN_PER_CLASS`, so the card names a species
# an identifier can actually meet (a 2-record Ostrya "look-alike" of Betula is noise).
MIN_LOOKALIKE_RECORDS = 20
PER_SPECIES = 3  # records per species per level, so a common species does not fill a level
CAP = 1500  # records per level per iconic group; keeps levels-data.bin well under 3 MB gzipped


def species_masks(s: pd.DataFrame, weird: pd.Series, bc_counts: pd.Series | None = None):
    """(easy, taxonomist) masks over scored species rows `s`, outside the `weird` rows.

    `s` has `taxon_id`, `taxon_name`, `own`, `margin`, `other_name`; `bc_counts` as in `assign`.
    """
    by_species = s.groupby("taxon_id")["own"]
    n_species = by_species.transform("size")
    own_share = by_species.rank(ascending=False, pct=True, method="first")
    easy = (s["margin"] > 0) & (n_species >= MIN_PER_CLASS) & (own_share <= EASY_TOP_SHARE) & ~weird
    # a name can map to two taxa (species and complex), so counts are summed by name
    counts = (
        s["taxon_name"].value_counts() if bc_counts is None else bc_counts.groupby(level=0).sum()
    )
    n_lookalike = s["other_name"].map(counts).fillna(0)
    taxonomist = (
        (s["margin"] < 0)
        & (s["margin"] >= -TAXONOMIST_MARGIN)
        & (n_lookalike >= MIN_LOOKALIKE_RECORDS)
        & ~weird
    )
    return easy, taxonomist


def assign(
    scores: pd.DataFrame,
    cap: int = CAP,
    per_species: int = PER_SPECIES,
    seed: int = 0,
    bc_counts: pd.Series | None = None,
) -> pd.DataFrame:
    """`LEVEL_COLUMNS` rows from `fir_scores` output, in display order (see the module docstring).

    `score` is the value each level is cut on: `own` for easy, `margin` for taxonomist and
    max(own, other) for weird. `bc_counts` (records by species name) replaces the pool as the
    source of a look-alike's record count; a name missing from it counts 0.
    Rows without a text prototype for their label are left out.
    """
    for c in ("own", "other", "margin", "other_name", "iconic_taxon", "photo_url"):
        if c not in scores.columns:
            raise ValueError(f"scores have no {c!r} column, needed for the levels")
    s = scores[scores["margin"].notna() & scores["other"].notna()].copy()
    s["group"] = s["iconic_taxon"].fillna("")
    s["top"] = np.fmax(s["own"], s["other"])
    weird = s["top"] <= s.groupby("group")["top"].transform(lambda x: x.quantile(WEIRD_SHARE))
    easy, taxonomist = species_masks(s, weird, bc_counts)
    rng = np.random.default_rng(seed)
    parts = []
    for key, mask, score in (
        ("easy", easy, "own"),
        ("taxonomist", taxonomist, "margin"),
        ("weird", weird, "top"),
    ):
        rows = s[mask].assign(level=key, score=s.loc[mask, score], draw=rng.random(int(mask.sum())))
        if key == "weird":
            # farthest first within each group, the groups taking turns
            rows = rows.sort_values(["top", "id"]).groupby("taxon_id").head(per_species)
            rows = rows.assign(turn=rows.groupby("group").cumcount())
            order = ["turn", "top", "id"]
        else:
            # one random record of each species in a random order, then a second, ...
            rows = rows.sort_values(["draw", "id"]).groupby("taxon_id").head(per_species)
            first = rows.groupby("taxon_id")["draw"].transform("min")
            rows = rows.assign(turn=rows.groupby("taxon_id").cumcount(), first=first)
            order = ["turn", "first", "draw"]
        parts.append(rows.sort_values(order).groupby("group", sort=False).head(cap))
    out = pd.concat(parts, ignore_index=True)
    out = out.rename(columns={"other_name": "looks_like_name"})
    out = out.astype({"taxon_id": np.int64, "score": np.float32})
    return out[list(LEVEL_COLUMNS)].reset_index(drop=True)


def add_range_notes(levels: pd.DataFrame, notes: pd.DataFrame) -> pd.DataFrame:
    """`levels` with a `range_note` column (string or null) looked up by id in `notes`.

    Only Close calls cards carry a note; `notes` has `id`, `range_note` (null for no line) and
    optionally `lat`, `lon` (the record's point) and `out_km`, which come through for every level.
    """
    for c in ("id", "range_note"):
        if c not in notes.columns:
            raise ValueError(f"range notes have no {c!r} column")
    notes = notes.drop_duplicates("id").set_index("id")
    keep = levels["level"] == "taxonomist"
    point = [c for c in ("lat", "lon", "out_km") if c in notes.columns]
    return levels.assign(
        range_note=levels["id"].map(notes["range_note"]).where(keep),
        **{c: levels["id"].map(notes[c]) for c in point},
    )


def describe(scores: pd.DataFrame, levels: pd.DataFrame) -> str:
    """The distributions the cut-offs were read from, and the rows per level per group."""
    s = scores[scores["margin"].notna() & scores["other"].notna()]
    q = [0.01, 0.02, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9]
    top = np.fmax(s["own"], s["other"])
    lines = [
        f"{len(s)} scored rows, {int((s['margin'] > 0).sum())} with margin > 0",
        "margin quantiles " + _quantiles(s["margin"], q),
        "own quantiles " + _quantiles(s["own"], q),
        "max(own, other) quantiles " + _quantiles(top, q),
        f"share with margin in [-{TAXONOMIST_MARGIN}, 0): "
        f"{((s['margin'] < 0) & (s['margin'] >= -TAXONOMIST_MARGIN)).mean():.3f}",
        f"max(own, other) at the {WEIRD_SHARE:.0%} cut per group:",
    ]
    cut = top.groupby(s["iconic_taxon"].fillna("")).quantile(WEIRD_SHARE)
    lines += [f"  {g or '(none)'}: {v:.4f}" for g, v in cut.items()]
    counts = (
        levels.groupby([levels["iconic_taxon"].fillna(""), "level"]).size().unstack(fill_value=0)
    )
    lines += ["rows per group and level:", counts.to_string()]
    return "\n".join(lines)


def _quantiles(x: pd.Series, q: list[float]) -> str:
    return " ".join(f"{p:g}:{v:.4f}" for p, v in zip(q, x.quantile(q), strict=True))


def _identify_main(args, manifest: dict) -> int:
    from what_to_id import identify  # imports this module, so not at the top
    from what_to_id.pool_levels import RANGE_FILES
    from what_to_id.taxonomy import load_tree

    tree = load_tree(args.tree)
    if not tree:
        raise ValueError(f"--identify needs a non-empty --tree, {args.tree!r} has no taxa")
    cols = ["id", "taxon_id", "taxon_name", "rank", "iconic_taxon"]
    missing = [c for c in cols if c not in pq.read_schema(args.pool).names]
    if missing:
        raise ValueError(f"pool {args.pool} has no column {missing[0]!r}")
    pool = pd.read_parquet(args.pool, columns=cols)
    taxa, T = read_taxa_vectors(args.taxa_names, args.taxa_vectors)
    scores = identify.identify_scores(
        pool, np.load(args.emb, mmap_mode="r"), np.load(args.ids), taxa, T, tree
    )
    bc = pd.read_parquet(args.bc_counts).set_index("name")["count"] if args.bc_counts else None
    out = identify.identify_levels(scores, bc_counts=bc)
    out.to_parquet(Path(args.atlas_dir) / "identify.parquet", index=False)
    built_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    # the range tables (`level_ranges`, keyed by record id) stay registered across a rescore
    keep = {k: v for k, v in manifest.get("identify", {}).items() if k in RANGE_FILES}
    manifest["identify"] = {
        "name": "identify.parquet",
        "built_at": built_at,
        "count": len(out),
        "emb": str(args.emb),  # its bulk download's date goes into the Identify About
    }
    manifest["identify"].update(keep)
    write_manifest(args.atlas_dir, manifest)
    print(identify.describe(scores, out))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m what_to_id.levels", description=__doc__)
    ap.add_argument("--emb", required=True, help="E.npy, float32 (n x d), memory-mapped")
    ap.add_argument("--ids", required=True, help="ids.npy, int64 observation ids, rows of E")
    ap.add_argument(
        "--pool", required=True, help="pool parquet with id, taxon_id, taxon_name, rank"
    )
    ap.add_argument("--taxa-names", required=True, help="atlas taxa-<sha>.tsv.gz")
    ap.add_argument("--taxa-vectors", required=True, help="atlas taxa-<sha>.f16")
    ap.add_argument("--atlas-dir", required=True, help="atlas index dir holding manifest.json")
    ap.add_argument(
        "--bc-counts",
        help="parquet with name, count (`python -m what_to_id.bc_counts`); look-alike records "
        "are counted there instead of in the pool",
    )
    ap.add_argument("--tree", help="map-state taxonomy.json; with --identify, finds the clades")
    ap.add_argument(
        "--identify",
        action="store_true",
        help="score every pool record into identify.parquet (needs --tree), not levels.parquet",
    )
    ap.add_argument(
        "--range-notes",
        help="`python -m what_to_id.level_ranges` range-notes.parquet (id, range_note, lat, lon): "
        "adds a range line to cards; the level-ranges and level-range-cells files beside it "
        "go to the atlas for the range maps",
    )
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)
    manifest = read_manifest(args.atlas_dir)
    if args.identify:
        return _identify_main(args, manifest)
    cols = ["id", "taxon_id", "taxon_name", "rank", "iconic_taxon", "photo_url"]
    missing = [c for c in cols if c not in pq.read_schema(args.pool).names]
    if missing:
        raise ValueError(f"pool {args.pool} has no column {missing[0]!r}")
    pool = pd.read_parquet(args.pool, columns=cols)
    taxa, T = read_taxa_vectors(args.taxa_names, args.taxa_vectors)
    scores = fir_scores(pool, np.load(args.emb, mmap_mode="r"), np.load(args.ids), taxa, T)
    bc = None
    if args.bc_counts:
        bc = pd.read_parquet(args.bc_counts).set_index("name")["count"]
    out = assign(scores, bc_counts=bc)
    if args.range_notes:
        out = add_range_notes(out, pd.read_parquet(args.range_notes))
    built_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    out.to_parquet(Path(args.atlas_dir) / "levels.parquet", index=False)
    manifest["levels"] = {"name": "levels.parquet", "built_at": built_at, "count": len(out)}
    if args.range_notes:
        for key, name in (
            ("ranges", "level-ranges.parquet"),
            ("range_cells", "level-range-cells.parquet"),
        ):
            src = Path(args.range_notes).parent / name
            if src.exists():
                shutil.copyfile(src, Path(args.atlas_dir) / name)
                manifest["levels"][key] = name
    write_manifest(args.atlas_dir, manifest)
    print(describe(scores, out))
    print(f"{len(out)} records in {out['level'].nunique()} levels")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
