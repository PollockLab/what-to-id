"""Usage: python -m what_to_id.blind_report --consensus consensus.parquet --obs obs.parquet
--idents idents.parquet [--public pool.parquet] [--levels levels.parquet] [--threshold 0.9]
[--answers answers.parquet --planted planted.parquet]

The first table is the error of CV-accepted versus typed first identifications, measured against
a blind consensus, which a public record cannot give because later identifiers see the suggestion.
With ``--public`` a second table divides the public overturn rate by that error: the community's
detection rate per source, the size of the agreement bias. With ``--levels`` a third table checks
the Identify levels: settled share and abstain share per level. With both, the three
pre-registered tests (H1 error, H2 detection, H3 levels) follow. With ``--answers`` and
``--planted`` the consensus error c is measured on held-out planted records and removed from
e and d: a settled consensus that is itself wrong counts a correct first ID as wrong, which
inflates e and deflates d = overturn / e.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from .blind_skill import fit

REPORT_COLUMNS = ["group", "source", "n", "wrong", "error", "lo", "hi"]
DETECT_COLUMNS = ["group", "source", "n", "error", "overturn", "detection", "lo", "hi"]
LEVEL_COLUMNS = ["level", "n", "settled", "posterior", "abstain"]
TEST_COLUMNS = ["hypothesis", "statistic", "p", "n"]
FIRST_COLUMNS = ["record_id", "group", "taxon_id", "vision"]
EXPERIENCE = ["<10 ids", "10-99 ids", "100+ ids"]
HARD_COLUMNS = [
    "record_id",
    "group",
    "source",
    "first",
    "consensus",
    "posterior",
    "n_answers",
    "why",
]
Z = 1.959964


def first_own_ids(obs: pd.DataFrame, idents: pd.DataFrame) -> pd.DataFrame:
    """Earliest identification by each observation's own observer. Needs ``iconic_taxon`` in obs.

    When obs carries ``observer_idents`` (the observer's lifetime identification count at
    read-back, as :mod:`readback` writes it) an ``experience`` column bins it by ``EXPERIENCE``.
    """
    if "iconic_taxon" not in obs.columns:
        raise ValueError("obs needs an iconic_taxon column (readback obs frames do not carry it)")
    extra = ["observer_idents"] if "observer_idents" in obs.columns else []
    own = idents[idents["user_id"] == idents["observer_id"]]
    first = own.sort_values("created_at", kind="stable").drop_duplicates("id")
    out = first.merge(obs[["id", "iconic_taxon", *extra]].drop_duplicates("id"), on="id")
    out = out.rename(columns={"id": "record_id", "iconic_taxon": "group"})
    out = out[FIRST_COLUMNS + extra].reset_index(drop=True)
    if extra:
        cuts = [-np.inf, 9, 99, np.inf]
        out["experience"] = pd.cut(out.pop("observer_idents"), cuts, labels=EXPERIENCE).astype(str)
    return out


def _wilson(wrong, n):
    p = wrong / n
    d = 1 + Z**2 / n
    c = (p + Z**2 / (2 * n)) / d
    h = Z * np.sqrt(p * (1 - p) / n + Z**2 / (4 * n**2)) / d
    return np.clip(c - h, 0, 1), np.clip(c + h, 0, 1)


def _correct(wrong_share, c):
    """First-ID error from the disagreement share, with consensus error c removed.

    Disagreement happens when exactly one of the two is wrong, so w = e + c - 2ec when the two
    errors are independent; this inverts that and floors at zero.
    """
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.clip((wrong_share - c) / (1 - 2 * c), 0, 1)


def _c_draws(rng, c, n, boot):
    """c per bootstrap replicate from its Jeffreys posterior when the held-out count n is given."""
    if not n or not np.isfinite(c):
        return c
    return rng.beta(c * n + 0.5, (1 - c) * n + 0.5, boot)


def held_out_consensus(answers, planted, threshold=0.9, folds=2, seed=0) -> pd.DataFrame:
    """Settled consensus of planted records fitted with their truth withheld, fold by fold.

    Columns: record_id, taxon_id (the consensus), truth, wrong, and kind when ``planted`` has it
    (``blind_planted``'s cv_fail, cv_hold, typed_fail, typed_hold).
    """
    planted = planted.drop_duplicates("record_id")
    ids = planted["record_id"].to_numpy().copy()
    np.random.default_rng(seed).shuffle(ids)
    parts = []
    for held in np.array_split(ids, folds):
        _, cons = fit(answers, planted[~planted["record_id"].isin(held)])
        got = cons[cons["record_id"].isin(held) & (cons["posterior"] >= threshold)]
        parts.append(got[got["taxon_id"].notna()][["record_id", "taxon_id"]])
    keep = ["record_id", "taxon_id"] + (["kind"] if "kind" in planted.columns else [])
    out = pd.concat(parts).merge(planted[keep].rename(columns={"taxon_id": "truth"}))
    out["wrong"] = (out["taxon_id"] != out["truth"]).astype(int)
    return out.reset_index(drop=True)


def consensus_error(answers, planted, threshold: float = 0.9, folds: int = 2, seed: int = 0):
    """Share of settled consensus taxa that are wrong, measured on held-out planted records.

    Returns ``(c, n_settled)``; c is NaN when nothing settles.
    """
    held = held_out_consensus(answers, planted, threshold, folds, seed)
    return (held["wrong"].mean() if len(held) else np.nan), len(held)


def kind_table(held: pd.DataFrame, firsts: pd.DataFrame) -> pd.DataFrame:
    """Per planted kind: held-out settled records, consensus error, and the share of those whose
    consensus is the observer's own wrong first name (students confirming the CV's mistake)."""
    j = held.merge(firsts[["record_id", "taxon_id"]], on="record_id", suffixes=("", "_first"))
    j["confirmed_first"] = (j["taxon_id"] == j["taxon_id_first"]) & (j["truth"] != j["taxon_id"])
    out = j.groupby("kind").agg(n=("wrong", "size"), c=("wrong", "mean"))
    out["confirmed_first"] = j.groupby("kind")["confirmed_first"].mean()
    return out.reset_index()


def cv_error(
    consensus,
    firsts,
    threshold=0.9,
    consensus_error=0.0,
    by="group",
    consensus_n=0,
    boot=4000,
    seed=0,
):
    """Error of first own IDs against the blind consensus, by group and CV/typed source.

    ``consensus_error`` is c from :func:`consensus_error`. Without ``consensus_n`` the interval
    is the Wilson interval of the disagreement share shifted with the point estimate; with it
    (the held-out count) the interval is the 2.5 and 97.5 percentiles of e over ``boot`` draws of
    the share and of c from their Jeffreys posteriors, so it carries c's uncertainty the way
    :func:`detection_rate` does. ``by`` names another firsts column to split
    on instead of group, such as ``experience`` from :func:`first_own_ids`; the public record
    shows the CV-typed gap closing with observer experience, so the split is reported as a
    descriptive check, not a test.
    """
    j = _scored(consensus, firsts, threshold, by)
    if j.empty:
        return pd.DataFrame(columns=[by, *REPORT_COLUMNS[1:]])
    out = j.groupby([by, "source"]).agg(n=("wrong", "size"), wrong=("wrong", "sum"))
    out = out.reset_index()
    w, n = out["wrong"].to_numpy(float), out["n"].to_numpy(float)
    out["error"] = _correct(w / n, consensus_error)
    if consensus_n:
        rng = np.random.default_rng(seed)
        cs = _c_draws(rng, consensus_error, consensus_n, boot)
        ps = rng.beta(w[:, None] + 0.5, n[:, None] - w[:, None] + 0.5, (len(w), boot))
        out["lo"], out["hi"] = np.percentile(_correct(ps, cs), [2.5, 97.5], axis=1)
    else:
        lo, hi = _wilson(w, n)
        out["lo"], out["hi"] = _correct(lo, consensus_error), _correct(hi, consensus_error)
    return out.sort_values([by, "source"], ignore_index=True)[[by, *REPORT_COLUMNS[1:]]]


def _scored(consensus, firsts, threshold, by="group"):
    keep = consensus[(consensus["posterior"] >= threshold) & consensus["taxon_id"].notna()]
    j = keep[["record_id", "taxon_id"]].merge(firsts, on="record_id", suffixes=("_c", ""))
    j["source"] = np.where(j["vision"].fillna(False).astype(bool), "cv", "typed")
    j["wrong"] = (j["taxon_id"] != j["taxon_id_c"]).astype(int)
    return pd.concat([j, j.assign(**{by: "all"})])


def detection_rate(
    consensus, firsts, public, threshold=0.9, boot=1000, seed=0, consensus_error=0.0, consensus_n=0
) -> pd.DataFrame:
    """Public overturn rate over blind error rate, by group and source, with a bootstrap 95% CI.

    ``public`` has ``record_id`` and the current public ``taxon_id``; give it only records that
    carry at least one identification besides the observer's, or detection is biased down.
    The ratio is d in overturn = e x d. Above 1 means the public caught errors the consensus
    missed, which is a check on the consensus, not a detection rate. ``consensus_error`` is c
    from :func:`consensus_error`, removed from e before the division; with ``consensus_n`` (its
    held-out count) each resample draws its own c, so the interval carries c's uncertainty.
    """
    j = _scored(consensus, firsts, threshold)
    j = j.merge(public[["record_id", "taxon_id"]].rename(columns={"taxon_id": "taxon_id_p"}))
    if j.empty:
        return pd.DataFrame(columns=DETECT_COLUMNS)
    # shortcut: taxon_id equality, so a public refinement to a descendant counts as overturned
    j["over"] = (j["taxon_id"] != j["taxon_id_p"]).astype(int)
    rng = np.random.default_rng(seed)
    cs = _c_draws(rng, consensus_error, consensus_n, boot)
    rows = []
    for (group, source), g in j.groupby(["group", "source"]):
        w, o = g["wrong"].to_numpy(), g["over"].to_numpy()
        idx = rng.integers(0, len(g), (boot, len(g)))
        with np.errstate(divide="ignore", invalid="ignore"):
            e = _correct(w.mean(), consensus_error)
            d = o.mean() / e
            ds = o[idx].mean(1) / _correct(w[idx].mean(1), cs)
        lo, hi = np.nanpercentile(ds, [2.5, 97.5]) if np.isfinite(ds).any() else (np.nan, np.nan)
        rows.append((group, source, len(g), e, o.mean(), d, lo, hi))
    return pd.DataFrame(rows, columns=DETECT_COLUMNS)


def hard_cases(consensus, firsts, threshold: float = 0.9) -> pd.DataFrame:
    """Records a model should learn from: a settled consensus that overturns the first own ID
    (``why`` = overturned, labelled with the consensus) or no consensus at ``threshold`` after at
    least one answer (``why`` = unsettled, ``consensus`` empty). Planted records are left out."""
    cons = consensus[
        ~consensus.get("planted", pd.Series(False, index=consensus.index)).astype(bool)
    ]
    j = cons.merge(firsts, on="record_id", suffixes=("", "_first"))
    settled = (j["posterior"] >= threshold) & j["taxon_id"].notna()
    keep = j[(settled & (j["taxon_id"] != j["taxon_id_first"])) | (~settled & (j["n_answers"] > 0))]
    out = keep.rename(columns={"taxon_id_first": "first", "taxon_id": "consensus"})
    out["source"] = np.where(out["vision"].fillna(False).astype(bool), "cv", "typed")
    out["why"] = np.where(settled[keep.index], "overturned", "unsettled")
    out.loc[out["why"] == "unsettled", "consensus"] = pd.NA
    return out[HARD_COLUMNS].sort_values(["why", "record_id"], ignore_index=True)


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


def hypothesis_tests(
    consensus,
    firsts,
    public,
    levels,
    threshold=0.9,
    boot=4000,
    seed=0,
    consensus_error=0.0,
    consensus_n=0,
):
    """The three pre-registered tests of the blind student track, one row each.

    H1 error: two-sided z test of e_cv against e_typed on settled records (statistic: difference).
    H2 detection: one-sided bootstrap over records of d_cv - d_typed, H1 is d_cv < d_typed
    (statistic: difference, p: share of resamples at or above zero).
    H3 levels: Spearman correlation between level order and the settled indicator, one-sided,
    H1 is negative (settled share falls from easy to weird). ``consensus_error`` and
    ``consensus_n`` enter H2 only, as in :func:`detection_rate`, one c draw shared by both arms
    per resample; H1 compares disagreement shares, which c shifts equally in both arms.
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
        cs = _c_draws(rng, consensus_error, consensus_n, boot)

        def d(g, idx, c):
            w, o = g["wrong"].to_numpy()[idx], g["over"].to_numpy()[idx]
            with np.errstate(divide="ignore", invalid="ignore"):
                return o.mean(-1) / _correct(w.mean(-1), c)

        diff = d(cvj, slice(None), consensus_error) - d(tyj, slice(None), consensus_error)
        bs = d(cvj, rng.integers(0, len(cvj), (boot, len(cvj))), cs) - d(
            tyj, rng.integers(0, len(tyj), (boot, len(tyj))), cs
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
    ap.add_argument("--answers", help="answers.parquet from blind_answers, for consensus error")
    ap.add_argument("--planted", help="planted.parquet from blind_sample, for consensus error")
    ap.add_argument("--hard-cases", help="write overturned and unsettled records to this parquet")
    a = ap.parse_args(argv)
    idents = pd.read_parquet(a.idents)
    firsts = first_own_ids(pd.read_parquet(a.obs), idents)
    consensus = pd.read_parquet(a.consensus)
    c, n_c = 0.0, 0
    if a.answers and a.planted:
        held = held_out_consensus(
            pd.read_parquet(a.answers), pd.read_parquet(a.planted), a.threshold
        )
        c, n_c = (held["wrong"].mean() if len(held) else 0.0), len(held)
        print(f"consensus error c = {c:.4f} on {n_c} held-out settled planted records")
        if "kind" in held.columns:
            print(kind_table(held, firsts).to_string(index=False))
        print()
    print(cv_error(consensus, firsts, a.threshold, c, consensus_n=n_c).to_string(index=False))
    if "experience" in firsts.columns:
        print()
        exp = cv_error(consensus, firsts, a.threshold, c, "experience", n_c)
        print(exp.to_string(index=False))
    if a.public:
        others = idents.loc[idents["user_id"] != idents["observer_id"], "id"].unique()
        public = pd.read_parquet(a.public, columns=["id", "taxon_id"])
        public = public[public["id"].isin(others)].rename(columns={"id": "record_id"})
        print()
        det = detection_rate(
            consensus, firsts, public, a.threshold, consensus_error=c, consensus_n=n_c
        )
        print(det.to_string(index=False))
    if a.levels:
        levels = pd.read_parquet(a.levels)
        print()
        print(level_table(consensus, levels, a.threshold).to_string(index=False))
    if a.hard_cases:
        hard = hard_cases(consensus, firsts, a.threshold)
        hard.to_parquet(a.hard_cases, index=False)
        over = (hard["why"] == "overturned").sum()
        print(f"\n{len(hard)} hard cases ({over} overturned) -> {a.hard_cases}")
    if a.public and a.levels:
        print()
        tests = hypothesis_tests(
            consensus, firsts, public, levels, a.threshold, consensus_error=c, consensus_n=n_c
        )
        print(tests.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
