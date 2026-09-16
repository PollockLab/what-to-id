"""Power of the weighted comparison, data-poor places first against newest first, by simulation.

The pre-registered outcome for the data-poor list is the weighted count: each distinct record a
participant gave a species-level ID adds its where-to-blitz cell score, and a record with no
score adds 0 (analysis._by_arm_weighted, analysis.record_totals). A participant's total on a
list is the sum of the scores of the records they identified there, so a lift comes from two
places.

- Exposure: which scores the page deals a participant on each list. Batches are cut from each
  list's order and, with a cap, only the first ``max_batches`` of each list and group are kept
  (batches.build_batches). The rotation page starts every browser at a uniform random batch of
  each list and group, wraps at the end, and cycles the lists in turn (page_rotation.ROTATION_JS).
  When every record is served, a random start makes the expected scores met the same on every
  list whatever the order. When the cap binds, the data-poor list serves only its highest scores
  (arms.GapFirst) and the control its newest records (arms.Recency).
- ID rate: the share of reviewed records a participant identifies. ``id_factor`` scales it on
  the data-poor list relative to control, for every record that list serves.

Exposure cases:

- ``preview``: one frozen pool (``pool``), each record put on a list uniformly at random, as the
  keyed hash does (assign.assign_keyed), each list and group ordered by the real arm code, cut
  into batches and capped. The split is redrawn every replicate.
- ``blitz``: group g holds ``group_counts[g]`` records. Each list of a group draws its scores
  with replacement from that group's scores in ``pool`` and serves the first ``max_batches``
  batches of its order. The control's served scores are a plain draw, which assumes a record's
  score is unrelated to its age.

Participants: a group drawn in proportion to ``group_counts``; effort and skill as in power.py
(``_depths``, and ``_effort`` in the rotation design); each list's effort worked from a random
start batch, whole batches in turn, records within a batch in random order (Identify shows a
batch newest first, not in list order). Each reviewed record is identified with probability
skill on the control and skill * id_factor on the data-poor list, capped at 1. The test is
analysis.sign_flip_p on per-participant differences at Holm's first-step level,
alpha / (n_arms - 1). A p below that level is always rejected by Holm, so this is a lower bound
on Holm-adjusted power over the n_arms - 1 comparisons.
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from what_to_id.analysis import sign_flip_p
from what_to_id.arms import GapFirst, Recency
from what_to_id.power import (
    BC_GROUP_COUNTS,
    BC_GROUPS,
    Scenario,
    _depths,
    _effort,
    _floats,
    identifier_power,
)

EXPOSURES = ("preview", "blitz")
BATCH_SIZE = 120  # cli.py --batch-size default
MAX_BATCHES = 20  # scripts/daily.sh MAX_BATCHES; the preview was built with --max-batches 20
POOL_NEEDS = ("id", "iconic_taxon", "created_at", "cell_score")


@dataclass(frozen=True)
class WeightedScenario:
    n_identifiers: int
    id_factor: float = 1.0
    exposure: str = "preview"
    n_arms: int = 4
    batch_size: int = BATCH_SIZE
    max_batches: int | None = MAX_BATCHES
    groups: tuple[str, ...] = BC_GROUPS
    group_counts: tuple[int, ...] = BC_GROUP_COUNTS
    depth_median: float = 100.0
    depth_sigma: float = 1.5
    depths: tuple[int, ...] | None = None
    skill_a: float = 2.0
    skill_b: float = 3.0

    def __post_init__(self):
        if self.exposure not in EXPOSURES:
            raise ValueError(f"exposure must be one of {EXPOSURES}, got {self.exposure!r}")
        if self.n_identifiers < 1 or self.n_arms < 2:
            raise ValueError("need n_identifiers >= 1 and n_arms >= 2")
        if not (math.isfinite(self.id_factor) and self.id_factor > 0):
            raise ValueError(f"id_factor must be a finite number > 0, got {self.id_factor!r}")
        if self.batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        if self.max_batches is not None and self.max_batches < 1:
            raise ValueError("max_batches must be >= 1 or None")
        if not self.groups or len(self.groups) != len(self.group_counts):
            raise ValueError("groups and group_counts must be non-empty and the same length")
        if min(self.group_counts) < 1:
            raise ValueError("every group count must be >= 1")
        if self.depths is not None and len(self.depths) == 0:
            raise ValueError("depths, when given, must hold at least one value")

    def base(self) -> Scenario:
        """The power.py scenario with the same effort and skill model, rotation design."""
        return Scenario(
            self.n_identifiers,
            0.0,
            "rotation",
            dealing="random-start",
            n_arms=self.n_arms,
            group_counts=self.group_counts,
            depth_median=self.depth_median,
            depth_sigma=self.depth_sigma,
            depths=self.depths,
            skill_a=self.skill_a,
            skill_b=self.skill_b,
        )


def pool_frames(pool: pd.DataFrame, groups: Sequence[str]) -> dict[str, pd.DataFrame]:
    """Per group: the pool rows the arms need (id, created_at, cell_score), with a clear error."""
    missing = [c for c in POOL_NEEDS if c not in pool.columns]
    if missing:
        raise ValueError(f"pool missing columns {missing}")
    out: dict[str, pd.DataFrame] = {}
    for g in groups:
        sub = pool.loc[pool["iconic_taxon"] == g, ["id", "created_at", "cell_score"]]
        out[g] = sub.reset_index(drop=True)
    empty = [g for g, sub in out.items() if sub.empty]
    if empty:
        raise ValueError(f"pool has no records for groups {empty}")
    return out


def _cut(seq: np.ndarray, sc: WeightedScenario, rng) -> np.ndarray:
    """Keep the served batches, then put each batch's records in random order."""
    if sc.max_batches is not None:
        seq = seq[: sc.max_batches * sc.batch_size]
    batch = np.arange(seq.size) // sc.batch_size
    return seq[np.lexsort((rng.random(seq.size), batch))]


def _scores(sub: pd.DataFrame) -> np.ndarray:
    return sub["cell_score"].astype("float64").fillna(0.0).to_numpy()


def preview_lists(frames, sc: WeightedScenario, rng) -> list[tuple[np.ndarray, np.ndarray]]:
    """Per group (sc.groups order): served scores of the control and the data-poor list."""
    out = []
    for g in sc.groups:
        sub = frames[g]
        arm = rng.integers(sc.n_arms, size=len(sub))
        ctl = sub[arm == 0].reset_index(drop=True)
        trt = sub[arm == 1].reset_index(drop=True)
        c = _scores(ctl)[Recency().order(ctl, seed=0)]
        t = _scores(trt)[GapFirst().order(trt, seed=0)]
        out.append((_cut(c, sc, rng), _cut(t, sc, rng)))
    return out


def blitz_lists(frames, sc: WeightedScenario, rng) -> list[tuple[np.ndarray, np.ndarray]]:
    """Per group: served scores when each list holds a draw of group_counts / n_arms records."""
    cap = None if sc.max_batches is None else sc.max_batches * sc.batch_size
    out = []
    for g, n in zip(sc.groups, sc.group_counts, strict=True):
        pooled = _scores(frames[g])
        n_c, n_t = rng.binomial(n, 1.0 / sc.n_arms, size=2)
        k_c = n_c if cap is None else min(n_c, cap)
        k_t = n_t if cap is None else min(n_t, cap)
        c = rng.choice(pooled, size=k_c)
        t = rng.choice(pooled, size=n_t)
        t = np.sort(np.partition(t, n_t - k_t)[n_t - k_t :])[::-1] if k_t else t[:0]
        out.append((_cut(c, sc, rng), _cut(t, sc, rng)))
    return out


def worked(seq: np.ndarray, effort: int, batch_size: int, rng) -> np.ndarray:
    """Scores of the records one participant reviews on one list, from a random start batch.

    Batches are consecutive slices of ``seq``, so opening batches in turn from a random batch
    and wrapping at the end is a run of positions from that batch's first record. No record is
    served twice, so effort beyond the list's length is lost.
    """
    n = min(int(effort), seq.size)
    if n <= 0:
        return seq[:0]
    n_batches = -(-seq.size // batch_size)
    start = int(rng.integers(n_batches)) * batch_size
    return seq[(start + np.arange(n)) % seq.size]


def weighted_power(
    sc: WeightedScenario,
    pool: pd.DataFrame,
    *,
    reps: int = 1000,
    seed: int = 0,
    alpha: float = 0.05,
    flips: int = 1000,
) -> dict:
    """Share of replicates where the data-poor list is ahead (or behind) at Holm's first step."""
    if reps < 1 or flips < 1:
        raise ValueError("reps and flips must be >= 1")
    if not 0 < alpha < 1:
        raise ValueError(f"alpha must be in (0, 1), got {alpha!r}")
    frames = pool_frames(pool, sc.groups)
    build = preview_lists if sc.exposure == "preview" else blitz_lists
    base = sc.base()
    counts = np.asarray(sc.group_counts, dtype=np.float64)
    shares = counts / counts.sum()
    level = alpha / (sc.n_arms - 1)
    rng = np.random.default_rng(seed)
    n = sc.n_identifiers
    ahead = behind = 0
    met = np.zeros((2, 2))  # rows: control, data-poor; columns: score sum, records reviewed
    totals = np.zeros(2)
    for _ in range(reps):
        lists = build(frames, sc, rng)
        group = rng.choice(len(sc.groups), size=n, p=shares)
        depth = _depths(base, n, rng)
        skill = rng.beta(sc.skill_a, sc.skill_b, n)
        effort = _effort(base, depth, rng)
        total = np.zeros((n, 2))
        for j in range(n):
            for arm, factor in ((0, 1.0), (1, sc.id_factor)):
                seen = worked(lists[group[j]][arm], effort[j, arm], sc.batch_size, rng)
                hit = rng.random(seen.size) < min(1.0, skill[j] * factor)
                total[j, arm] = seen[hit].sum()
                met[arm] += (seen.sum(), seen.size)
        diff = total[:, 1] - total[:, 0]
        totals += total.sum(axis=0)
        p = sign_flip_p(diff, reps=flips, seed=int(rng.integers(2**32)))
        if p < level:
            ahead += diff.sum() > 0
            behind += diff.sum() < 0
    per = totals / (reps * n)
    return {
        "scenario": {k: v for k, v in asdict(sc).items() if k != "depths"},
        "power": ahead / reps,
        "behind": behind / reps,
        "level": level,
        "score_met_control": float(met[0, 0] / max(met[0, 1], 1.0)),
        "score_met_data_poor": float(met[1, 0] / max(met[1, 1], 1.0)),
        "mean_total_control": float(per[0]),
        "mean_total_data_poor": float(per[1]),
    }


def _load_pool(path: Path, webapp_dir: Path | None) -> pd.DataFrame:
    pool = pd.read_parquet(path)
    if "cell_score" not in pool.columns:
        if webapp_dir is None:
            raise SystemExit(f"{path} has no cell_score; pass --webapp-dir to score it")
        from what_to_id.cells import score_records

        pool["cell_score"] = score_records(pool, webapp_dir=webapp_dir).to_numpy()
    return pool


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Simulated power of the confirmatory comparisons.")
    ap.add_argument("--pool", type=Path, required=True, help="pool parquet, the score source")
    ap.add_argument("--webapp-dir", type=Path, help="where-to-blitz grid, if the pool is unscored")
    ap.add_argument("--identifiers", default="10,15,20,25,30,40,50")
    ap.add_argument("--factors", default="0.6,0.8,1.0", help="data-poor ID rate over control")
    ap.add_argument("--exposures", default=",".join(EXPOSURES))
    ap.add_argument(
        "--lifts", default="0.1,0.2,0.3", help="plain-count lifts: planning values, no source"
    )
    ap.add_argument(
        "--max-batches", type=int, default=MAX_BATCHES, help="cap per list and group; 0: no cap"
    )
    ap.add_argument("--reps", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--depths", type=Path, help="JSON list of per-identifier record counts")
    ap.add_argument("--out", type=Path, help="write all results as JSON")
    a = ap.parse_args(argv)
    pool = _load_pool(a.pool, a.webapp_dir)
    depths = tuple(int(x) for x in json.loads(a.depths.read_text())) if a.depths else None
    idents = [int(x) for x in _floats(a.identifiers)]
    rows = []
    print(
        "| exposure | ID-rate factor | participants | power (ahead) | power (behind) | "
        "score met, control | score met, data-poor |"
    )
    print("|---|---|---|---|---|---|---|")
    for exposure in (e.strip() for e in a.exposures.split(",") if e.strip()):
        for factor in _floats(a.factors):
            for n in idents:
                sc = WeightedScenario(
                    n, factor, exposure, max_batches=a.max_batches or None, depths=depths
                )
                r = weighted_power(sc, pool, reps=a.reps, seed=a.seed)
                rows.append({"outcome": "weighted", **r})
                print(
                    f"| {exposure} | {factor:.2f} | {n} | {r['power']:.2f} | {r['behind']:.2f} | "
                    f"{r['score_met_control']:.3f} | {r['score_met_data_poor']:.3f} |"
                )
    print("\n| plain-count lift (planning value) | participants | power |")
    print("|---|---|---|")
    for lift in _floats(a.lifts):
        for n in idents:
            sc = Scenario(n, lift, "rotation", dealing="random-start", depths=depths)
            pw = identifier_power(sc, reps=a.reps, seed=a.seed)
            rows.append({"outcome": "plain", "lift": lift, "n_identifiers": n, "power": pw})
            print(f"| {lift:.2f} | {n} | {pw:.2f} |")
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(rows, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
