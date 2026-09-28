"""Synthetic four-arm diagnostic, not validation of the prospective study design.

Uses production keyed assignment, capped batches and confirmatory inference. All scores are
flat and all arms use recency composition: similarity/novelty here are explicitly synthetic,
without embeddings. One build, equal records attempted per arm within each participant,
independent Bernoulli responses, no depletion, dropout, outside IDs or daily refresh. Repeated
ID events are included to exercise participant-record deduplication. Participants with no ID
are omitted by the existing analysis. These assumptions do not describe measured pilot effort.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from statistics import NormalDist

import numpy as np
import pandas as pd

from what_to_id.arms import Recency
from what_to_id.assign import assign_keyed
from what_to_id.batches import build_batches
from what_to_id.confirmatory import PRIMARY, confirmatory

ARMS = ("recency", *PRIMARY)
START = "2026-01-01T00:00:00Z"
CUTOFF = "2026-01-02T00:00:00Z"
ASSUMPTIONS = __doc__.strip()


@dataclass(frozen=True)
class Scenario:
    participants: int = 20
    pool_size: int = 1600
    batch_size: int = 20
    max_batches: int = 5
    effect_arm: str = "similarity"
    effect: float = 0.0  # additive response probability, bounded below to prevent clipping
    duplicate_events: bool = True

    def __post_init__(self):
        for name in ("participants", "pool_size", "batch_size", "max_batches"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be >= 1")
        if self.effect_arm not in PRIMARY:
            raise ValueError(f"effect_arm must be one of {tuple(PRIMARY)}")
        if not math.isfinite(self.effect) or not -0.1 <= self.effect <= 0.5:
            raise ValueError("effect must be finite and between -0.1 and 0.5")


def interval(hits: int, reps: int) -> dict:
    """Wilson 95% Monte Carlo interval, including zero/all-rejection boundaries."""
    if reps < 1 or not 0 <= hits <= reps:
        raise ValueError("need reps >= 1 and 0 <= hits <= reps")
    z = NormalDist().inv_cdf(0.975)
    p = hits / reps
    scale = 1 + z * z / reps
    centre = (p + z * z / (2 * reps)) / scale
    radius = z * math.sqrt(p * (1 - p) / reps + z * z / (4 * reps * reps)) / scale
    return {
        "rejections": hits,
        "replicates": reps,
        "rate": p,
        "mc_interval_95": [max(0.0, centre - radius), min(1.0, centre + radius)],
    }


def simulate(sc: Scenario, *, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return synthetic identification events and production-built served composition."""
    rng = np.random.default_rng(seed)
    pool = pd.DataFrame(
        {
            "id": np.arange(1, sc.pool_size + 1),
            "iconic_taxon": "Synthetic",
            "created_at": pd.date_range(
                end=pd.Timestamp(START) - pd.Timedelta(minutes=1),
                periods=sc.pool_size,
                freq="min",
            ),
            "cell_score": 1.0,
        }
    )
    assignment = assign_keyed(pool, ARMS, key=rng.bytes(32))
    batches = build_batches(
        pool,
        assignment,
        {arm: Recency() for arm in ARMS},
        size=sc.batch_size,
        seed=seed,
        max_batches=sc.max_batches,
    )
    if set(batches["arm"]) != set(ARMS):
        raise ValueError("synthetic pool leaves an arm empty; increase pool_size")
    served = batches[["id", "arm"]].assign(cell_score=1.0)
    sequences = {arm: batches.loc[batches["arm"].eq(arm), "id"].to_numpy() for arm in ARMS}
    rows = []
    for user in range(1, sc.participants + 1):
        # Heterogeneous effort and skill are synthetic; equal per-arm attempts, not time.
        effort = min(int(rng.integers(10, 51)), min(map(len, sequences.values())))
        skill = float(rng.uniform(0.1, 0.5))
        for arm, seq in sequences.items():
            start = int(rng.integers(math.ceil(len(seq) / sc.batch_size))) * sc.batch_size
            seen = seq[(start + np.arange(effort)) % len(seq)]
            probability = skill + (sc.effect if arm == sc.effect_arm else 0.0)
            for oid in seen[rng.random(len(seen)) < probability]:
                rows.append((int(oid), user, START, "species"))
    events = pd.DataFrame(rows, columns=["id", "user_id", "created_at", "taxon_rank"])
    if sc.duplicate_events:
        events = pd.concat([events, events.assign(created_at="2026-01-01T01:00:00Z")])
    return events.reset_index(drop=True), served


def diagnose(sc: Scenario, *, reps: int = 500, seed: int = 0, flips: int = 2000) -> dict:
    if reps < 1 or flips < 1:
        raise ValueError("reps and flips must be >= 1")
    rng = np.random.default_rng(seed)
    raw = dict.fromkeys(PRIMARY, 0)
    adjusted = dict.fromkeys(PRIMARY, 0)
    differences = dict.fromkeys(PRIMARY, 0.0)
    any_rejected = omitted = 0
    for _ in range(reps):
        draw = int(rng.integers(2**32))
        events, served = simulate(sc, seed=draw)
        result = confirmatory(
            events,
            served,
            control="recency",
            start=START,
            cutoff=CUTOFF,
            users=list(range(1, sc.participants + 1)),
            reps=flips,
            seed=draw,
        )
        primary = result.loc[result["role"].eq("primary")].set_index("arm")
        omitted += sc.participants - int(primary["n_identifiers"].iloc[0])
        any_rejected += int(primary["p_holm"].lt(0.05).any())
        for arm in PRIMARY:
            raw[arm] += int(primary.loc[arm, "p"] < 0.05)
            adjusted[arm] += int(primary.loc[arm, "p_holm"] < 0.05)
            differences[arm] += float(primary.loc[arm, "mean_diff"])
    return {
        "assumptions": ASSUMPTIONS,
        "scenario": asdict(sc),
        "seed": seed,
        "sign_flip_replicates": flips,
        "alpha": 0.05,
        "interval_method": "Wilson 95%, marginal Monte Carlo uncertainty, not simultaneous",
        "family_any_rejection": interval(any_rejected, reps),
        "omitted_zero_id_participants_across_replicates": omitted,
        "comparisons": {
            arm: {
                "raw": interval(raw[arm], reps),
                "holm": interval(adjusted[arm], reps),
                "mean_participant_difference": differences[arm] / reps,
            }
            for arm in PRIMARY
        },
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reps", type=int, default=500)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--flips", type=int, default=2000)
    ap.add_argument("--effect", type=float, default=0.0)
    ap.add_argument("--participants", type=int, default=20)
    args = ap.parse_args(argv)
    sc = Scenario(participants=args.participants, effect=args.effect)
    print(json.dumps(diagnose(sc, reps=args.reps, seed=args.seed, flips=args.flips), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
