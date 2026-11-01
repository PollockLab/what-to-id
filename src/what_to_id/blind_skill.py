"""One-coin Dawid-Skene (1979) skill estimate per login and taxon group for a blind study."""

from __future__ import annotations

import numpy as np
import pandas as pd

SKILL_COLUMNS = ["login", "group", "accuracy", "n_answers", "n_planted"]
CONSENSUS_COLUMNS = ["record_id", "taxon_id", "posterior", "n_answers", "n_abstain", "planted"]


def _estep(acc, key, cid, arec, crec, k, fixed, onehot):
    """Posterior over each record's candidate labels given per-key accuracies."""
    a = acc[key]
    other = np.log((1 - a) / np.maximum(k[arec] - 1, 1))
    lp = np.bincount(arec, other, minlength=len(k))[crec]
    lp = lp + np.bincount(cid, np.log(a) - other, minlength=len(crec))
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
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fit per login and group accuracy by EM; planted records keep their expert truth."""
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
    key, cid, arec = (ans[c].to_numpy() for c in ("key", "cid", "rec"))
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
    n = np.bincount(key)
    acc = None
    for _ in range(iters):
        prev, acc = acc, (np.bincount(key, p[cid]) + 1) / (n + 2)  # Beta(1,1) keeps 0 < acc < 1
        p = _estep(acc, key, cid, arec, crec, k, fixed, onehot)
        if prev is not None and np.abs(acc - prev).max() < tol:
            break
    names = ans.drop_duplicates("key").sort_values("key")[["login", "group"]]
    n_planted = np.bincount(key, fixed[cid], minlength=len(n)).astype(int)
    skill = names.assign(accuracy=acc, n_answers=n, n_planted=n_planted).reset_index(drop=True)
    best = cand.assign(posterior=p).sort_values("posterior", ascending=False, kind="stable")
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


def consensus_at(consensus: pd.DataFrame, threshold: float = 0.9) -> pd.DataFrame:
    """Keep consensus rows whose posterior is at least the threshold."""
    return consensus[consensus["posterior"] >= threshold].reset_index(drop=True)
