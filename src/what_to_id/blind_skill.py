"""One-coin Dawid-Skene (1979) skill estimate per login and taxon group for a blind study.

With ``ancestry`` an answer agrees with a candidate when it names the candidate or one of its
ancestors, so a cautious genus answer supports every species in that genus instead of voting
against them, and the consensus is the finest taxon whose summed posterior passes ``threshold``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SKILL_COLUMNS = ["login", "group", "accuracy", "n_answers", "n_planted"]
CONSENSUS_COLUMNS = ["record_id", "taxon_id", "posterior", "n_answers", "n_abstain", "planted"]


def _estep(acc, key, k, crec, fixed, onehot, pa, pc, agree):
    """Posterior over each record's candidate labels given per-key accuracies; ``pa``, ``pc``
    and ``agree`` list every (answer, candidate of the same record) pair."""
    a = acc[key][pa]
    other = np.log((1 - a) / np.maximum(k[crec[pc]] - 1, 1))
    lp = np.bincount(pc, np.where(agree, np.log(a), other), minlength=len(crec))
    mx = np.full(len(k), -np.inf)
    np.maximum.at(mx, crec, lp)
    e = np.exp(lp - mx[crec])
    p = e / np.bincount(crec, e, minlength=len(k))[crec]
    return np.where(fixed, onehot, p)


def fit(
    answers: pd.DataFrame,
    planted: pd.DataFrame | None = None,
    iters: int = 50,
    tol: float = 1e-4,
    ancestry: dict | None = None,
    threshold: float = 0.9,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fit per login and group accuracy by EM; planted records keep their expert truth.

    ``ancestry`` maps a taxon id to the set of its ancestor ids (:func:`ancestry_from_taxa`);
    without it every taxon is its own class and ``threshold`` is unused.
    """
    if answers.empty:
        return pd.DataFrame(columns=SKILL_COLUMNS), pd.DataFrame(columns=CONSENSUS_COLUMNS)
    truth = (
        planted.drop_duplicates("record_id")[["record_id", "taxon_id"]]
        if planted is not None
        else pd.DataFrame({"record_id": [], "taxon_id": []})
    )
    voted = answers[answers["taxon_id"] >= 0]
    abstain = answers[answers["taxon_id"] < 0].groupby("record_id").size()
    cand = pd.concat([voted[["record_id", "taxon_id"]], truth]).drop_duplicates()
    cand = cand.reset_index(drop=True)
    cand["rec"] = pd.factorize(cand["record_id"])[0]
    cand["cid"] = cand.index
    ans = voted.merge(cand, on=["record_id", "taxon_id"])
    ans["key"] = ans.groupby(["login", "group"]).ngroup()
    key, cid = ans["key"].to_numpy(), ans["cid"].to_numpy()
    crec = cand["rec"].to_numpy()
    k = np.bincount(crec)
    truth_of = cand["record_id"].map(truth.set_index("record_id")["taxon_id"])
    fixed = truth_of.notna().to_numpy()
    onehot = (cand["taxon_id"] == truth_of).to_numpy(float)
    # majority vote start, ties broken by first candidate
    votes = cand.assign(n=np.bincount(cid, minlength=len(cand)))
    top = votes.sort_values("n", ascending=False, kind="stable").drop_duplicates("rec").index
    p = np.zeros(len(cand))
    p[top] = 1.0
    p = np.where(fixed, onehot, p)
    anc = ancestry or {}
    pairs = ans[["rec", "taxon_id"]].reset_index(drop=True).reset_index(names="pa")
    pairs = pairs.merge(cand[["rec", "cid", "taxon_id"]], on="rec", suffixes=("", "_c"))
    pa, pc = pairs["pa"].to_numpy(), pairs["cid"].to_numpy()
    agree = np.fromiter(
        (
            t == c or t in anc.get(c, ())
            for t, c in zip(pairs["taxon_id"], pairs["taxon_id_c"], strict=True)
        ),
        bool,
        len(pairs),
    )
    n = np.bincount(key)
    acc = None
    for _ in range(iters):
        hit = np.bincount(pa, np.where(agree, p[pc], 0.0), minlength=len(key))
        prev, acc = acc, (np.bincount(key, hit) + 1) / (n + 2)  # Beta(1,1) keeps 0 < acc < 1
        p = _estep(acc, key, k, crec, fixed, onehot, pa, pc, agree)
        if prev is not None and np.abs(acc - prev).max() < tol:
            break
    names = ans.drop_duplicates("key").sort_values("key")[["login", "group"]]
    n_planted = np.bincount(key, fixed[cid], minlength=len(n)).astype(int)
    skill = names.assign(accuracy=acc, n_answers=n, n_planted=n_planted).reset_index(drop=True)
    best = cand.assign(posterior=p)
    if ancestry is not None:
        best = _roll_up(best, anc, threshold)
    best = best.sort_values("posterior", ascending=False, kind="stable")
    best = best.drop_duplicates("record_id").set_index("record_id")
    ids = pd.concat([answers["record_id"], truth["record_id"]]).unique()
    recs = pd.Index(ids, name="record_id")
    cons = pd.DataFrame(index=recs)
    cons["taxon_id"] = best["taxon_id"].reindex(recs).astype("Int64")
    cons["posterior"] = best["posterior"].reindex(recs)
    cons["n_answers"] = voted.groupby("record_id").size().reindex(recs, fill_value=0)
    cons["n_abstain"] = abstain.reindex(recs, fill_value=0)
    cons["planted"] = recs.isin(truth["record_id"])
    return skill, cons.reset_index()[CONSENSUS_COLUMNS]


def _roll_up(cand: pd.DataFrame, anc: dict, threshold: float) -> pd.DataFrame:
    """Per record, the finest taxon (candidate or ancestor) whose summed candidate posterior
    passes ``threshold``, with that sum as its posterior; else the candidates unchanged."""
    out = []
    for rid, g in cand.groupby("record_id", sort=False):
        support: dict = {}
        for t, q in zip(g["taxon_id"], g["posterior"], strict=True):
            for x in {t, *anc.get(t, ())}:
                support[x] = support.get(x, 0.0) + q
        ok = [x for x, q in support.items() if q >= threshold - 1e-12]
        if ok:
            t = max(ok, key=lambda x: (len(anc.get(x, ())), support[x]))
            out.append(
                pd.DataFrame({"record_id": [rid], "taxon_id": [t], "posterior": [support[t]]})
            )
        else:
            out.append(g[["record_id", "taxon_id", "posterior"]])
    return pd.concat(out, ignore_index=True)


def ancestry_from_taxa(taxa: pd.DataFrame) -> dict:
    """Taxon id to its set of ancestor ids, from ``taxon_id`` and slash-separated ``ancestry``
    (the iNaturalist taxa export)."""
    return {
        int(t): frozenset(int(x) for x in a.split("/") if x) if isinstance(a, str) else frozenset()
        for t, a in zip(taxa["taxon_id"], taxa["ancestry"], strict=True)
    }


def consensus_at(consensus: pd.DataFrame, threshold: float = 0.9) -> pd.DataFrame:
    """Keep consensus rows whose posterior is at least the threshold."""
    return consensus[consensus["posterior"] >= threshold].reset_index(drop=True)
