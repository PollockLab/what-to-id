"""Usage: python -m what_to_id.blind_report --consensus consensus.parquet --obs obs.parquet
--idents idents.parquet [--public pool.parquet] [--levels levels.parquet] [--threshold 0.9]

The first table is the error of CV-accepted versus typed first identifications, measured against
a blind consensus, which a public record cannot give because later identifiers see the suggestion.
With ``--public`` a second table divides the public overturn rate by that error: the community's
detection rate per source, the size of the agreement bias. With ``--levels`` a third table checks
the Identify levels: settled share and abstain share per level. With both, the three
pre-registered tests (H1 error, H2 detection, H3 levels) follow.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

REPORT_COLUMNS = ["group", "source", "n", "wrong", "error", "lo", "hi"]
DETECT_COLUMNS = ["group", "source", "n", "error", "overturn", "detection", "lo", "hi"]
LEVEL_COLUMNS = ["level", "n", "settled", "posterior", "abstain"]
TEST_COLUMNS = ["hypothesis", "statistic", "p", "n"]
FIRST_COLUMNS = ["record_id", "group", "taxon_id", "vision"]
Z = 1.959964


def first_own_ids(obs: pd.DataFrame, idents: pd.DataFrame) -> pd.DataFrame:
    """Earliest identification by each observation's own observer. Needs ``iconic_taxon`` in obs."""
    if "iconic_taxon" not in obs.columns:
        raise ValueError("obs needs an iconic_taxon column (readback obs frames do not carry it)")
    own = idents[idents["user_id"] == idents["observer_id"]]
    first = own.sort_values("created_at", kind="stable").drop_duplicates("id")
    out = first.merge(obs[["id", "iconic_taxon"]].drop_duplicates("id"), on="id")
    out = out.rename(columns={"id": "record_id", "iconic_taxon": "group"})
    return out[FIRST_COLUMNS].reset_index(drop=True)


def _wilson(wrong, n):
    p = wrong / n
    d = 1 + Z**2 / n
    c = (p + Z**2 / (2 * n)) / d
    h = Z * np.sqrt(p * (1 - p) / n + Z**2 / (4 * n**2)) / d
    return np.clip(c - h, 0, 1), np.clip(c + h, 0, 1)


def cv_error(consensus: pd.DataFrame, firsts: pd.DataFrame, threshold: float = 0.9):
    """Error of first own IDs against the blind consensus, by group and CV/typed source."""
    j = _scored(consensus, firsts, threshold)
    if j.empty:
        return pd.DataFrame(columns=REPORT_COLUMNS)
    out = j.groupby(["group", "source"]).agg(n=("wrong", "size"), wrong=("wrong", "sum"))
    out = out.reset_index()
    out["error"] = out["wrong"] / out["n"]
    out["lo"], out["hi"] = _wilson(out["wrong"].to_numpy(float), out["n"].to_numpy(float))
    return out.sort_values(["group", "source"], ignore_index=True)[REPORT_COLUMNS]


def _scored(consensus, firsts, threshold):
    keep = consensus[(consensus["posterior"] >= threshold) & consensus["taxon_id"].notna()]
    j = keep[["record_id", "taxon_id"]].merge(firsts, on="record_id", suffixes=("_c", ""))
    j["source"] = np.where(j["vision"].fillna(False).astype(bool), "cv", "typed")
    j["wrong"] = (j["taxon_id"] != j["taxon_id_c"]).astype(int)
    return pd.concat([j, j.assign(group="all")])


def detection_rate(
    consensus, firsts, public, threshold: float = 0.9, boot: int = 1000, seed: int = 0
) -> pd.DataFrame:
    """Public overturn rate over blind error rate, by group and source, with a bootstrap 95% CI.

    ``public`` has ``record_id`` and the current public ``taxon_id``; give it only records that
    carry at least one identification besides the observer's, or detection is biased down.
    The ratio is d in overturn = e x d. Above 1 means the public caught errors the consensus
    missed, which is a check on the consensus, not a detection rate.
    """
    j = _scored(consensus, firsts, threshold)
    j = j.merge(public[["record_id", "taxon_id"]].rename(columns={"taxon_id": "taxon_id_p"}))
    if j.empty:
        return pd.DataFrame(columns=DETECT_COLUMNS)
    # shortcut: taxon_id equality, so a public refinement to a descendant counts as overturned
    j["over"] = (j["taxon_id"] != j["taxon_id_p"]).astype(int)
    rng = np.random.default_rng(seed)
    rows = []
    for (group, source), g in j.groupby(["group", "source"]):
        w, o = g["wrong"].to_numpy(), g["over"].to_numpy()
        idx = rng.integers(0, len(g), (boot, len(g)))
        with np.errstate(divide="ignore", invalid="ignore"):
            d = o.mean() / w.mean()
            ds = o[idx].mean(1) / w[idx].mean(1)
        lo, hi = np.nanpercentile(ds, [2.5, 97.5]) if np.isfinite(ds).any() else (np.nan, np.nan)
        rows.append((group, source, len(g), w.mean(), o.mean(), d, lo, hi))
    return pd.DataFrame(rows, columns=DETECT_COLUMNS)


def level_table(consensus, levels, threshold: float = 0.9) -> pd.DataFrame:
    """Per Identify level: records, share settled at ``threshold``, mean posterior, abstain share.

    The levels claim an ordering of difficulty; settled share should fall and abstain share rise
    from easy to weird. ``levels`` is the ``levels.parquet`` that ``blind_sample`` writes.
    """
    j = consensus.merge(levels[["record_id", "level"]], on="record_id")
    if j.empty:
        return pd.DataFrame(columns=LEVEL_COLUMNS)
    j["settled"] = (j["posterior"] >= threshold) & j["taxon_id"].notna()
    j["abstain"] = j["n_abstain"] / (j["n_answers"] + j["n_abstain"])
    out = j.groupby("level").agg(
        n=("record_id", "size"),
        settled=("settled", "mean"),
        posterior=("posterior", "mean"),
        abstain=("abstain", "mean"),
    )
    return out.reset_index()[LEVEL_COLUMNS]


def hypothesis_tests(consensus, firsts, public, levels, threshold=0.9, boot=4000, seed=0):
    """The three pre-registered tests of the blind student track, one row each.

    H1 error: two-sided z test of e_cv against e_typed on settled records (statistic: difference).
    H2 detection: one-sided bootstrap over records of d_cv - d_typed, H1 is d_cv < d_typed
    (statistic: difference, p: share of resamples at or above zero).
    H3 levels: Spearman correlation between level order and the settled indicator, one-sided,
    H1 is negative (settled share falls from easy to weird).
    """
    from scipy import stats

    j = _scored(consensus, firsts, threshold)
    j = j[j["group"] == "all"]
    rows = []
    cv, ty = j.loc[j["source"] == "cv", "wrong"], j.loc[j["source"] == "typed", "wrong"]
    if len(cv) and len(ty):
        p = stats.ttest_ind(cv, ty, equal_var=False).pvalue
        p = 1.0 if np.isnan(p) else p  # no variance in either arm: no evidence either way
        rows.append(("H1 error cv != typed", cv.mean() - ty.mean(), p, len(j)))
    j = j.merge(public[["record_id", "taxon_id"]].rename(columns={"taxon_id": "taxon_id_p"}))
    j["over"] = (j["taxon_id"] != j["taxon_id_p"]).astype(int)
    cvj, tyj = j[j["source"] == "cv"], j[j["source"] == "typed"]
    if cvj["wrong"].sum() and tyj["wrong"].sum():
        rng = np.random.default_rng(seed)

        def d(g, idx):
            w, o = g["wrong"].to_numpy()[idx], g["over"].to_numpy()[idx]
            with np.errstate(divide="ignore", invalid="ignore"):
                return o.sum(-1) / w.sum(-1)

        diff = d(cvj, slice(None)) - d(tyj, slice(None))
        bs = d(cvj, rng.integers(0, len(cvj), (boot, len(cvj)))) - d(
            tyj, rng.integers(0, len(tyj), (boot, len(tyj)))
        )
        rows.append(("H2 detection cv < typed", diff, np.nanmean(bs >= 0), len(j)))
    lv = consensus.merge(levels[["record_id", "level"]], on="record_id")
    if lv["level"].nunique() > 1:
        settled = ((lv["posterior"] >= threshold) & lv["taxon_id"].notna()).astype(int)
        r = stats.spearmanr(lv["level"], settled, alternative="less")
        rows.append(("H3 settled falls with level", r.statistic, r.pvalue, len(lv)))
    return pd.DataFrame(rows, columns=TEST_COLUMNS)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="CV versus typed first-ID error vs blind consensus")
    ap.add_argument("--consensus", required=True)
    ap.add_argument("--obs", required=True)
    ap.add_argument("--idents", required=True)
    ap.add_argument("--public", help="pool parquet with id and the current public taxon_id")
    ap.add_argument("--levels", help="levels.parquet from blind_sample")
    ap.add_argument("--threshold", type=float, default=0.9)
    a = ap.parse_args(argv)
    idents = pd.read_parquet(a.idents)
    firsts = first_own_ids(pd.read_parquet(a.obs), idents)
    consensus = pd.read_parquet(a.consensus)
    print(cv_error(consensus, firsts, a.threshold).to_string(index=False))
    if a.public:
        others = idents.loc[idents["user_id"] != idents["observer_id"], "id"].unique()
        public = pd.read_parquet(a.public, columns=["id", "taxon_id"])
        public = public[public["id"].isin(others)].rename(columns={"id": "record_id"})
        print()
        print(detection_rate(consensus, firsts, public, a.threshold).to_string(index=False))
    if a.levels:
        levels = pd.read_parquet(a.levels)
        print()
        print(level_table(consensus, levels, a.threshold).to_string(index=False))
    if a.public and a.levels:
        print()
        tests = hypothesis_tests(consensus, firsts, public, levels, a.threshold)
        print(tests.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
