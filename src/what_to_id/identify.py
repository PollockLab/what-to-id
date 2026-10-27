"""Score every pool record for the Identify pane, at any rank (see `levels` for the species rules).

`identify_scores` runs one chunked pass of E against the species text prototypes, whose columns
are ordered depth-first over the taxonomy tree so each clade is a contiguous column range
[lo, hi). A species-ranked row gets `own` / `other` as in `confusion.text_scores`; a row labelled
above species whose clade holds a prototype gets its in-clade best, second best and the best
outside the clade. Every row gets `top`, its best cosine to any prototype.

`identify_levels` turns that into one row per record (`IDENTIFY_COLUMNS`): weird first at any
rank, then easy / taxonomist at species rank with no per-species or per-group cap, then narrow
for a higher rank whose clade has a prototype. Everything else is level 0.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from what_to_id.confusion import CHUNK, FIR_SLICE
from what_to_id.levels import WEIRD_SHARE, species_masks

IDENTIFY_COLUMNS = ("id", "taxon_id", "level", "score", "score2", "looks_like")
NONE, EASY, TAXONOMIST, NARROW, WEIRD = 0, 1, 2, 3, 4
LEVEL_NAMES = ("none", "easy", "taxonomist", "narrow", "weird")


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
    in_second and out_best are NaN when the clade has one species or all of them).
    """
    is_species = (taxa.str.split().str.len() == 2).to_numpy()
    names = taxa[is_species].drop_duplicates()
    protos = np.asarray(T, dtype=np.float32)[names.index.to_numpy()]
    order, clades = clade_columns(tree, names.tolist())
    protos = protos[pd.Series(np.arange(len(names)), index=names.to_numpy())[order].to_numpy()]
    order = np.array(order, dtype=object)
    col = pd.Series(np.arange(len(order)), index=order)
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
                    r["in_second"][c + i] = np.partition(seg, -2)[-2]
                out = np.concatenate([sims[i, :lo], sims[i, hi:]])
                if len(out):
                    r["out_best"][c + i] = out.max()
        parts.append(q.drop(columns="pos").assign(**r).reset_index(drop=True))
    if not parts:
        return p.drop(columns="pos").assign(
            **{k: pd.Series(dtype=float) for k in ("top", "own", "other", "in_best")},
            **{k: pd.Series(dtype=float) for k in ("in_second", "out_best")},
            other_name=pd.Series(dtype=object),
            in_name=pd.Series(dtype=object),
        )
    return pd.concat(parts, ignore_index=True).astype({"id": np.int64, "taxon_id": np.int64})


def identify_levels(scores: pd.DataFrame, bc_counts: pd.Series | None = None) -> pd.DataFrame:
    """`IDENTIFY_COLUMNS` rows from `identify_scores`, one per record, in score order of `scores`.

    `score` is `own` for easy, the margin for taxonomist, in-clade best minus outside best for
    narrow and `top` for weird; `score2` is best minus second-best in-clade (narrow only);
    `looks_like` is the look-alike species (taxonomist) or the probable species (narrow).
    """
    s = scores.copy()
    s["group"] = s["iconic_taxon"].fillna("")
    weird = s["top"] <= s.groupby("group")["top"].transform(lambda x: x.quantile(WEIRD_SHARE))
    sp = s[(s["rank"] == "species") & s["own"].notna() & s["other"].notna()].assign(
        margin=lambda d: d["own"] - d["other"]
    )
    easy, tax = species_masks(sp, weird.loc[sp.index], bc_counts)
    easy, tax = easy.reindex(s.index, fill_value=False), tax.reindex(s.index, fill_value=False)
    narrow = (s["rank"] != "species") & s["in_best"].notna() & ~weird
    level = np.select([weird, easy, tax, narrow], [WEIRD, EASY, TAXONOMIST, NARROW], NONE)
    score = np.select(
        [weird, easy, tax, narrow],
        [s["top"], s["own"], s["own"] - s["other"], s["in_best"] - s["out_best"]],
        np.nan,
    )
    score2 = np.where(narrow & ~weird, s["in_best"] - s["in_second"], np.nan)
    looks = np.where(tax, s["other_name"], np.where(narrow, s["in_name"], None))
    return pd.DataFrame(
        {
            "id": s["id"].to_numpy(np.int64),
            "taxon_id": s["taxon_id"].to_numpy(np.int64),
            "level": level.astype(np.int8),
            "score": score.astype(np.float32),
            "score2": score2.astype(np.float32),
            "looks_like": pd.Series(looks, dtype="string").astype("category").to_numpy(),
        }
    )


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
