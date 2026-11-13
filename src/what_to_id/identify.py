"""Score every pool record for the Identify pane, at any rank (see `levels` for the species rules).

`identify_scores` runs one chunked pass of E against the species text prototypes, whose columns
are ordered depth-first over the taxonomy tree so each clade is a contiguous column range
[lo, hi). A species-ranked row gets `own` / `other` as in `confusion.text_scores`; a row labelled
above species whose clade holds a prototype gets its in-clade best, second best and the best
outside the clade. Every row gets `top`, its best cosine to any prototype.

`identify_levels` turns that into one row per record (`IDENTIFY_COLUMNS`): weird first at any
rank, then easy / taxonomist at species rank with no per-species or per-group cap, then narrow
for a higher rank whose clade has a prototype, then mislabel: a species-ranked margin below
`-TAXONOMIST_MARGIN` with a look-alike of `MIN_LOOKALIKE_RECORDS` records. Everything else is
level 0.

`identify_delta` brings a base table up to the pool (the daily atlas run) against cut-offs frozen
from that table (`freeze_cutoffs`): the per-group weird cut and, per species, the lowest `own` of
its Clear matches. A species with fewer than `MIN_PER_CLASS` base records never gets a Clear
match, as in the full run. It drops records that left the pool (or lost their taxon), rescores
records whose pool taxon_id differs from the stored one, and scores pool records the base lacks
(new, or in the index but never scored). Other base rows are untouched. A record with no vector
keeps its old row (or gets none). Vectors come from the raw deltas where present, else
`atlas_index_io.reconstruct` rebuilds them from the index's refine codes. Levels of rescored
Fir-era records come from 3-bit refine reconstructions, 97.7% level agreement with true vectors.
A Fir rerun replaces the file.

    python -m what_to_id.identify --live DIR --index DIR --pool pool.parquet --tree taxonomy.json \\
        --taxa DIR --vectors raw-delta-*.npz [--bc-counts bc-verifiable-counts.parquet]

DIR for --live holds the host's current manifest.json and identify.parquet; --index gets the merged
identify.parquet and its manifest's ``"identify"`` entry, taken from the live one.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd

from what_to_id.atlas_index_io import read_manifest, reconstruct, write_manifest
from what_to_id.confusion import CHUNK, FIR_SLICE, MIN_PER_CLASS, read_taxa_vectors
from what_to_id.levels import TAXONOMIST_MARGIN, WEIRD_SHARE, lookalike_known, species_masks

IDENTIFY_COLUMNS = ("id", "taxon_id", "level", "score", "score2", "looks_like")
NONE, EASY, TAXONOMIST, NARROW, WEIRD, MISLABEL = 0, 1, 2, 3, 4, 5
CATEGORIES = ("looks_like", "runner_up")
LEVEL_NAMES = ("none", "easy", "taxonomist", "narrow", "weird", "mislabel")


class Frozen(NamedTuple):
    weird: pd.Series  # iconic group ("" for none) -> highest `top` that is weird
    easy: pd.Series  # taxon id -> lowest `own` among its Clear matches
    n: pd.Series  # taxon id -> species-ranked records in the base


def freeze_cutoffs(base: pd.DataFrame, pool: pd.DataFrame) -> Frozen:
    """Cut-offs read back from `base` (`identify_levels` output); `pool` adds rank, iconic_taxon."""
    m = base.merge(pool[["id", "rank", "iconic_taxon"]].drop_duplicates("id"), on="id")
    weird = m[m["level"] == WEIRD]
    easy = m[m["level"] == EASY]
    return Frozen(
        weird["score"].groupby(weird["iconic_taxon"].fillna("")).max(),
        easy["score"].groupby(easy["taxon_id"]).min(),
        m[m["rank"] == "species"].groupby("taxon_id").size(),
    )


def clade_columns(
    tree: dict[int, list], proto_names: list[str]
) -> tuple[list[str], dict[int, tuple[int, int]]]:
    """(prototype names in depth-first order, {taxon id: (lo, hi)} for clades with a prototype).

    Prototypes the tree does not know come last, in no clade. Children are visited by id.
    """
    wanted = set(proto_names)
    children: dict[int, list[int]] = {}
    for tid, node in tree.items():
        children.setdefault(node[0] if node[0] in tree else 0, []).append(tid)
    order: list[str] = []
    clades: dict[int, tuple[int, int]] = {}
    seen: set[int] = set()
    stack = [(t, None) for t in sorted(children.get(0, ()), reverse=True)]
    while stack:
        tid, lo = stack.pop()
        if lo is not None:  # leaving tid: its subtree has been visited
            if len(order) > lo:
                clades[tid] = (lo, len(order))
            continue
        if tid in seen:
            continue
        seen.add(tid)
        stack.append((tid, len(order)))
        node = tree[tid]
        if node[3] == "species" and node[1] in wanted:
            order.append(node[1])
            wanted.discard(node[1])
        stack.extend((c, None) for c in sorted(children.get(tid, ()), reverse=True))
    return order + [n for n in proto_names if n in wanted], clades


def identify_scores(
    pool: pd.DataFrame, E: np.ndarray, ids: np.ndarray, taxa: pd.Series, T: np.ndarray, tree: dict
) -> pd.DataFrame:
    """Scores per pool row that has an embedding row in `ids`, read from `E` in `FIR_SLICE` slices.

    Columns: id, taxon_id, taxon_name, rank, iconic_taxon, top, own, other, other_name (species
    rank), in_best, in_second, out_best, in_name (rank above species, clade with a prototype;
    in_second_name; in_second and out_best are NaN when the clade has one species or all of them).
    """
    is_species = (taxa.str.split().str.len() == 2).to_numpy()
    names = taxa[is_species].drop_duplicates()
    protos = np.asarray(T, dtype=np.float32)[names.index.to_numpy()]
    order, clades = clade_columns(tree, names.tolist())
    protos = protos[pd.Series(np.arange(len(names)), index=names.to_numpy())[order].to_numpy()]
    order = np.array(order, dtype=object)
    col = pd.Series(np.arange(len(order)), index=order)
    in_tree = max((hi for _, hi in clades.values()), default=0)  # the rest has no clade
    p = pool[["id", "taxon_id", "taxon_name", "rank", "iconic_taxon"]].dropna(
        subset=["id", "taxon_id"]
    )
    pos = pd.Series(np.arange(len(ids)), index=ids).reindex(p["id"].to_numpy()).to_numpy()
    p = p.assign(pos=pos).dropna(subset=["pos"]).sort_values("pos")
    nan = np.float32(np.nan)
    parts = []
    for s in range(0, len(p), FIR_SLICE):
        q = p.iloc[s : s + FIR_SLICE]
        X = np.asarray(E[q["pos"].to_numpy().astype(np.int64)], dtype=np.float32)
        species = (q["rank"] == "species").to_numpy()
        own_col = np.where(species, q["taxon_name"].map(col).fillna(-1), -1).astype(int)
        span = np.array([clades.get(t, (0, 0)) for t in q["taxon_id"].astype(np.int64)])
        span = span.reshape(-1, 2)
        n = len(q)
        r = {
            k: np.full(n, nan) for k in ("top", "own", "other", "in_best", "in_second", "out_best")
        }
        r["other_name"] = np.full(n, None, dtype=object)
        r["in_name"] = np.full(n, None, dtype=object)
        r["in_second_name"] = np.full(n, None, dtype=object)
        for c in range(0, n, CHUNK):
            sims = (
                X[c : c + CHUNK] @ protos.T if len(order) else np.empty((len(X[c : c + CHUNK]), 0))
            )
            ar, sl = np.arange(len(sims)), slice(c, c + len(sims))
            r["top"][sl] = sims.max(1) if sims.shape[1] else nan
            oc = own_col[sl]
            ok = oc >= 0
            r["own"][sl][ok] = sims[ar[ok], oc[ok]]
            sp = sims[ok].copy()
            sp[np.arange(len(sp)), oc[ok]] = -np.inf
            if sp.shape[1] > 1:
                best = sp.argmax(1)
                other = r["other"][sl]
                other[ok] = sp[np.arange(len(sp)), best]
                other[ok & ~np.isfinite(other)] = nan
                r["other_name"][sl][ok] = order[best]
            for i in np.flatnonzero(span[sl, 1] > span[sl, 0]):
                lo, hi = span[c + i]
                seg = sims[i, lo:hi]
                j = int(seg.argmax())
                r["in_best"][c + i], r["in_name"][c + i] = seg[j], order[lo + j]
                if hi - lo > 1:
                    k = int(np.argpartition(seg, -2)[-2])
                    r["in_second"][c + i], r["in_second_name"][c + i] = seg[k], order[lo + k]
                # outside means elsewhere in the tree: the root's clade has no outside
                if lo > 0 or hi < in_tree:
                    r["out_best"][c + i] = max(
                        sims[i, :lo].max(initial=-np.inf), sims[i, hi:in_tree].max(initial=-np.inf)
                    )
        parts.append(q.drop(columns="pos").assign(**r).reset_index(drop=True))
    if not parts:
        return p.drop(columns="pos").assign(
            **{k: pd.Series(dtype=float) for k in ("top", "own", "other", "in_best")},
            **{k: pd.Series(dtype=float) for k in ("in_second", "out_best")},
            other_name=pd.Series(dtype=object),
            in_name=pd.Series(dtype=object),
            in_second_name=pd.Series(dtype=object),
        )
    return pd.concat(parts, ignore_index=True).astype({"id": np.int64, "taxon_id": np.int64})


def identify_levels(
    scores: pd.DataFrame, bc_counts: pd.Series | None = None, frozen: Frozen | None = None
) -> pd.DataFrame:
    """`IDENTIFY_COLUMNS` rows from `identify_scores`, one per record, in score order of `scores`.

    `score` is `own` for easy, the margin for taxonomist and mislabel, the smaller of in-clade
    best minus outside best and `score2` for narrow (most confident first) and `top` for weird;
    `score2` is best minus second-best in-clade (narrow only); `looks_like` is the look-alike
    species (taxonomist, mislabel) or the probable species (narrow); a trailing `runner_up` column
    holds narrow's second-best species in the clade, the one `score2` is the margin over.

    With `frozen`, the weird cut and the easy share come from it, not from `scores`; a group or
    species it lacks gets neither level. `bc_counts` should then cover the whole pool.
    """
    s = scores.copy()
    s["group"] = s["iconic_taxon"].fillna("")
    if frozen is None:
        weird = s["top"] <= s.groupby("group")["top"].transform(lambda x: x.quantile(WEIRD_SHARE))
    else:
        weird = s["top"] <= s["group"].map(frozen.weird).astype(float)
    sp = s[(s["rank"] == "species") & s["own"].notna() & s["other"].notna()].assign(
        margin=lambda d: d["own"] - d["other"]
    )
    easy, tax = species_masks(sp, weird.loc[sp.index], bc_counts)
    if frozen is not None:
        easy = (
            (sp["margin"] > 0)
            & (sp["taxon_id"].map(frozen.n).astype(float).fillna(0) >= MIN_PER_CLASS)
            & (sp["own"] >= sp["taxon_id"].map(frozen.easy).astype(float))
            & ~weird.loc[sp.index]
        )
    easy, tax = easy.reindex(s.index, fill_value=False), tax.reindex(s.index, fill_value=False)
    narrow = (s["rank"] != "species") & s["in_best"].notna() & ~weird
    # species rank only, so disjoint from narrow; the margin test is disjoint from easy and tax
    mislabel = (
        (sp["margin"] < -TAXONOMIST_MARGIN) & lookalike_known(sp, bc_counts) & ~weird.loc[sp.index]
    ).reindex(s.index, fill_value=False)
    conds = [weird, easy, tax, narrow, mislabel]
    level = np.select(conds, [WEIRD, EASY, TAXONOMIST, NARROW, MISLABEL], NONE)
    score = np.select(
        conds,
        [
            s["top"],
            s["own"],
            s["own"] - s["other"],
            # the weaker of "in this clade" and "this species of it"
            np.minimum(s["in_best"] - s["out_best"], s["in_best"] - s["in_second"]),
            s["own"] - s["other"],
        ],
        np.nan,
    )
    score2 = np.where(narrow & ~weird, s["in_best"] - s["in_second"], np.nan)
    looks = np.where(tax | mislabel, s["other_name"], np.where(narrow, s["in_name"], None))
    return pd.DataFrame(
        {
            "id": s["id"].to_numpy(np.int64),
            "taxon_id": s["taxon_id"].to_numpy(np.int64),
            "level": level.astype(np.int8),
            "score": score.astype(np.float32),
            "score2": score2.astype(np.float32),
            "looks_like": pd.Series(looks, dtype="string").astype("category").to_numpy(),
            "runner_up": pd.Series(np.where(narrow, s.get("in_second_name"), None), dtype="string")
            .astype("category")
            .to_numpy(),
        }
    )


def identify_delta(
    base: pd.DataFrame,
    pool: pd.DataFrame,
    E: np.ndarray,
    ids: np.ndarray,
    taxa: pd.Series,
    T: np.ndarray,
    tree: dict,
    bc_counts: pd.Series | None = None,
    reconstruct: Callable[[np.ndarray], tuple[np.ndarray, np.ndarray]] | None = None,
) -> pd.DataFrame:
    """`base` brought up to `pool`: see the module docstring.

    `E` holds vectors for `ids`; `reconstruct(ids)` returns (ids, vectors) for the ones to score
    that `E` lacks.
    """
    frozen = freeze_cutoffs(base, pool)
    pool = pool.dropna(subset=["id", "taxon_id"]).drop_duplicates("id")  # a full run skips the rest
    current = base["id"].map(pool.set_index("id")["taxon_id"])
    stale = base["id"].isin(pool["id"]) & (current != base["taxon_id"])
    todo = pool[~pool["id"].isin(base.loc[~stale, "id"])]
    if bc_counts is None:  # the whole pool, as a full run counts look-alikes
        bc_counts = pool.loc[pool["rank"] == "species", "taxon_name"].value_counts()
    ids = np.asarray(ids, dtype=np.int64)
    missing = todo.loc[~todo["id"].isin(ids), "id"].to_numpy(np.int64)
    if reconstruct is not None and len(missing):
        rids, rE = reconstruct(missing)
        ids, E = np.concatenate([ids, rids]), np.concatenate([E.astype(np.float32), rE])
    add = identify_levels(identify_scores(todo, E, ids, taxa, T, tree), bc_counts, frozen)
    kept = base[base["id"].isin(pool["id"]) & ~base["id"].isin(add["id"])]
    out = pd.concat([kept, add], ignore_index=True)
    cat = {k: out[k].astype("string").astype("category").to_numpy() for k in CATEGORIES}
    return out.assign(**cat)


def _one(folder: str, pattern: str) -> Path:
    found = sorted(Path(folder).glob(pattern))
    if len(found) != 1:
        raise ValueError(f"expected one {pattern} in {folder}, found {len(found)}")
    return found[0]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m what_to_id.identify", description=__doc__)
    ap.add_argument(
        "--live", required=True, help="dir with the host's manifest and identify.parquet"
    )
    ap.add_argument(
        "--index", required=True, help="index dir to write identify.parquet and manifest"
    )
    ap.add_argument("--pool", required=True, help="pool parquet: id, taxon_id, taxon_name, rank")
    ap.add_argument("--tree", required=True, help="map-state taxonomy.json")
    ap.add_argument("--taxa", required=True, help="dir with taxa-<sha>.tsv.gz and .f16")
    ap.add_argument("--vectors", nargs="*", default=[], help="raw-*.npz (ids, E) of new records")
    ap.add_argument("--bc-counts", help="as levels.py; default counts look-alikes in the pool")
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)
    from what_to_id.taxonomy import load_tree

    live = Path(args.live)
    registered = json.loads((live / "manifest.json").read_text()).get("identify")
    if not (live / "identify.parquet").exists() or not registered:
        print("no live identify.parquet; run levels_fir.sbatch first, nothing to extend")
        return 0
    base = pd.read_parquet(live / "identify.parquet")
    tree = load_tree(args.tree)
    if not tree:
        raise ValueError(f"{args.tree!r} has no taxa")
    pool = pd.read_parquet(
        args.pool, columns=["id", "taxon_id", "taxon_name", "rank", "iconic_taxon"]
    )
    taxa, T = read_taxa_vectors(_one(args.taxa, "taxa-*.tsv.gz"), _one(args.taxa, "taxa-*.f16"))
    zs = [np.load(v) for v in args.vectors]
    ids = np.concatenate([z["ids"] for z in zs]) if zs else np.empty(0, np.int64)
    E = np.concatenate([z["E"] for z in zs]) if zs else np.empty((0, T.shape[1]), np.float16)
    if E.shape[1] != T.shape[1]:
        raise ValueError(f"vectors have {E.shape[1]} dims, taxa vectors {T.shape[1]}")
    bc = pd.read_parquet(args.bc_counts).set_index("name")["count"] if args.bc_counts else None
    out_dir = Path(args.index)
    manifest = read_manifest(out_dir)  # this run's, with its new parts; only "identify" is live's

    def from_index(want):
        return reconstruct(out_dir, manifest, want)

    ids, first = np.unique(ids.astype(np.int64), return_index=True)  # a record in two deltas
    out = identify_delta(base, pool, E[first], ids, taxa, T, tree, bc, from_index)
    tmp = out_dir / "identify.parquet.tmp"
    out.to_parquet(tmp, index=False)
    tmp.replace(out_dir / "identify.parquet")
    manifest["identify"] = {
        **registered,
        "count": len(out),
        "delta_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    write_manifest(out_dir, manifest)
    print(f"{len(out)} records from {len(base)}: {len(out) - len(base):+d}")
    return 0


def describe(scores: pd.DataFrame, out: pd.DataFrame) -> str:
    """Records per level, and per iconic group and level."""
    lvl = pd.Series(np.array(LEVEL_NAMES)[out["level"].to_numpy()], name="level")
    group = scores["iconic_taxon"].fillna("(none)").to_numpy()
    counts = pd.crosstab(pd.Series(group, name="group"), lvl).reindex(
        columns=LEVEL_NAMES, fill_value=0
    )
    return "\n".join(
        [
            f"{len(out)} records",
            "records per level:",
            lvl.value_counts().reindex(LEVEL_NAMES, fill_value=0).to_string(),
            "records per group and level:",
            counts.to_string(),
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
