"""Power of the arm comparison under two page designs, by simulation.

Records are randomised to arms, but identifiers are the scarce, heavy-tailed resource. In the
``sets`` design (the current page) each identifier is dealt one set, so an arm's total effort
depends on which identifiers happened to land on it. In the ``rotation`` design every
identifier's batches cycle through all arms, so each arm gets an equal share of everyone's effort.

Model, per taxon group and arm: a queue of records worked top-down. Identifier j works
``depth_j`` records of each queue it is on. A record at a position reached by identifiers J is
resolved by the blitz with probability 1 - prod_{j in J}(1 - skill_j * lift_arm), and otherwise
by background activity with probability ``background``. The statistic is the difference in
resolved records between one treatment arm and the control arm, counted over the whole arm
(``pool``, what readback.outcomes does today) or over the first ``window`` positions of each
queue (``window``, a denominator fixed before the blitz). Its null distribution is simulated
under the same design with no lift, so the test is calibrated to the design. That is an oracle
test: a real analysis must estimate the null spread, which is harder with few identifier
clusters, so power for ``sets`` is an upper bound.

Within a queue, ``dealing`` controls how identifiers share out the records they work.
``stacked`` (default) has every identifier work the top ``depth_j`` records of the queue, so
identifiers overlap completely (the model above). ``random-start`` matches the served page
(page_rotation): each identifier gets an independent random start offset within the queue's
served window and works ``effort`` consecutive positions from there, wrapping around, so
identifiers spread out and overlap only where their stretches happen to meet.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np

from what_to_id.analysis import sign_flip_p

DESIGNS = ("sets", "rotation")
DEALINGS = ("stacked", "random-start")

# BC needs-ID records with photos created 2025-01-01 to 2026-09-11, iNaturalist API counts
# per iconic group taken 2026-09-12 (Plantae, Insecta, Fungi, Arachnida, Mollusca, Aves,
# Mammalia, Actinopterygii, Reptilia, Amphibia).
BC_GROUP_COUNTS = (605259, 286993, 218592, 42923, 30061, 26184, 12869, 4047, 2472, 2080)


@dataclass(frozen=True)
class Scenario:
    n_identifiers: int
    lift: float
    design: str = "sets"
    dealing: str = "stacked"
    n_arms: int = 4
    group_counts: tuple[int, ...] = BC_GROUP_COUNTS
    window: int = 3000
    depth_median: float = 100.0
    depth_sigma: float = 1.5
    depths: tuple[int, ...] | None = None
    skill_a: float = 2.0
    skill_b: float = 3.0
    background: float = 0.05

    def __post_init__(self):
        if self.design not in DESIGNS:
            raise ValueError(f"design must be one of {DESIGNS}, got {self.design!r}")
        if self.dealing not in DEALINGS:
            raise ValueError(f"dealing must be one of {DEALINGS}, got {self.dealing!r}")
        if self.n_identifiers < 1 or self.n_arms < 2 or self.window < 1:
            raise ValueError("need n_identifiers >= 1, n_arms >= 2, window >= 1")
        if self.lift <= -1 or not 0 <= self.background < 1:
            raise ValueError("need lift > -1 and 0 <= background < 1")


def _queue(depths, p, n, window, rng) -> tuple[int, int]:
    """Blitz-resolved records in one queue of n: (whole queue, first `window` positions)."""
    if depths.size == 0:
        return 0, 0
    order = np.argsort(-depths, kind="stable")
    d = np.minimum(depths[order], n)
    lo = np.append(d[1:], 0)
    # Positions (lo_i, d_i] are reached by the i + 1 deepest identifiers.
    p_res = 1.0 - np.cumprod(1.0 - p[order])
    inside = np.clip(np.minimum(d, window) - lo, 0, None)
    a = int(rng.binomial(inside, p_res).sum())
    b = int(rng.binomial(d - lo - inside, p_res).sum())
    return a + b, a


def _queue_random_start(effort: np.ndarray, p: np.ndarray, window: int, rng) -> int:
    """Blitz-resolved records within the served window, each identifier from a random start.

    Each identifier works a contiguous, ``effort``-long stretch of window positions from an
    independent uniform start, wrapping around at ``window``, as page_rotation deals each
    browser. Unlike ``_queue``, no identified work reaches past the window, since the page only
    ever serves a ``window``-sized list.
    """
    if effort.size == 0 or window <= 0:
        return 0
    length = np.minimum(effort, window)
    total = int(length.sum())
    if total == 0:
        return 0
    starts = rng.integers(window, size=length.size)
    within = np.arange(total) - np.repeat(np.cumsum(length) - length, length)
    positions = (np.repeat(starts, length) + within) % window
    log_survive = np.zeros(window)
    with np.errstate(divide="ignore"):
        # log1p(-1) = -inf for p == 1 (certain resolution), which is a legitimate skill value.
        np.add.at(log_survive, positions, np.repeat(np.log1p(-p), length))
        p_res = -np.expm1(log_survive)
    return int(rng.binomial(1, p_res).sum())


def _depths(sc: Scenario, n: int, rng) -> np.ndarray:
    if sc.depths is not None:
        depth = rng.choice(np.asarray(sc.depths, dtype=np.int64), size=n)
    else:
        depth = np.round(rng.lognormal(np.log(sc.depth_median), sc.depth_sigma, n))
    return np.maximum(1, depth).astype(np.int64)


def _effort(sc: Scenario, depth: np.ndarray, rng) -> np.ndarray:
    """Records each identifier works per arm, shape (n_identifiers, n_arms)."""
    n, k = depth.size, sc.n_arms
    if sc.design == "sets":
        out = np.zeros((n, k), dtype=np.int64)
        out[np.arange(n), rng.integers(k, size=n)] = depth
        return out
    base, rem = np.divmod(depth, k)
    extra = rng.random((n, k)).argsort(axis=1) < rem[:, None]
    return base[:, None] + extra.astype(np.int64)


def simulate(sc: Scenario, reps: int, seed: int) -> dict[str, np.ndarray]:
    """Treatment minus control resolved records per replicate, for both denominators."""
    rng = np.random.default_rng(seed)
    counts = np.asarray(sc.group_counts, dtype=np.float64)
    queue_n = np.maximum(1, np.round(counts / sc.n_arms)).astype(np.int64)
    shares = counts / counts.sum()
    arm_total = int(queue_n.sum())
    win_total = int(np.minimum(queue_n, sc.window).sum())
    lifts = (0.0, sc.lift)
    stats = {"pool": np.empty(reps), "window": np.empty(reps)}
    for r in range(reps):
        n = sc.n_identifiers
        group = rng.choice(len(counts), size=n, p=shares)
        depth = _depths(sc, n, rng)
        skill = rng.beta(sc.skill_a, sc.skill_b, n)
        effort = _effort(sc, depth, rng)
        res = []
        for arm, lift in enumerate(lifts):
            p = np.minimum(1.0, skill * (1.0 + lift))
            whole = win = 0
            for g, qn in enumerate(queue_n):
                m = (group == g) & (effort[:, arm] > 0)
                if sc.dealing == "stacked":
                    w, i = _queue(effort[m, arm], p[m], qn, sc.window, rng)
                else:
                    i = _queue_random_start(effort[m, arm], p[m], min(qn, sc.window), rng)
                    w = i
                whole, win = whole + w, win + i
            bg_in = rng.binomial(win_total - win, sc.background)
            bg_out = rng.binomial(arm_total - win_total - (whole - win), sc.background)
            res.append((whole + bg_in + bg_out, win + bg_in))
        stats["pool"][r] = res[1][0] - res[0][0]
        stats["window"][r] = res[1][1] - res[0][1]
    return stats


def power(sc: Scenario, *, reps: int = 2000, seed: int = 0, alpha: float = 0.05) -> dict:
    """Two-sided power per denominator, with the null simulated under the same design."""
    null = simulate(replace(sc, lift=0.0), reps, seed)
    alt = simulate(sc, reps, seed + 1)
    out: dict = {"scenario": {k: v for k, v in asdict(sc).items() if k != "depths"}}
    for key in ("pool", "window"):
        thr = float(np.quantile(np.abs(null[key]), 1 - alpha))
        out[key] = {
            "power": float((np.abs(alt[key]) > thr).mean()),
            "null_sd": float(null[key].std()),
            "mean_diff": float(alt[key].mean()),
        }
    return out


def identifier_power(
    sc: Scenario, *, reps: int = 1000, seed: int = 0, alpha: float = 0.05, flips: int = 1000
) -> float:
    """Power of the pre-registered per-identifier test (analysis.sign_flip_p), rotation only.

    One treatment arm is compared with control at Holm's first-step level, alpha / (n_arms - 1),
    the bar the smallest p value must clear when only one arm differs, so the result is slightly
    conservative for the Holm-corrected analysis.

    Each identifier's species-level identifications in an arm are Binomial(effort, skill *
    lift_arm); queue competition and the window cap are ignored, which is conservative for
    neither side and small while effort is far below the queue length.
    """
    if sc.design != "rotation":
        raise ValueError("the per-identifier test needs the rotation design")
    level = alpha / (sc.n_arms - 1)
    rng = np.random.default_rng(seed)
    hits = 0
    for _ in range(reps):
        depth = _depths(sc, sc.n_identifiers, rng)
        skill = rng.beta(sc.skill_a, sc.skill_b, sc.n_identifiers)
        effort = _effort(sc, depth, rng)
        control = rng.binomial(effort[:, 0], skill)
        treated = rng.binomial(effort[:, 1], np.minimum(1.0, skill * (1.0 + sc.lift)))
        p = sign_flip_p(treated - control, reps=flips, seed=int(rng.integers(2**32)))
        hits += p < level
    return hits / reps


def _floats(s: str) -> list[float]:
    return [float(x) for x in s.split(",") if x.strip()]


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Simulated power of the arm comparison.")
    ap.add_argument("--identifiers", default="10,25,50,100")
    ap.add_argument("--lifts", default="0.1,0.2,0.3")
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--window", type=int, default=3000)
    ap.add_argument("--dealing", choices=DEALINGS, default="stacked")
    ap.add_argument("--depths", type=Path, help="JSON list of per-identifier record counts")
    ap.add_argument("--out", type=Path, help="write all results as JSON")
    a = ap.parse_args(argv)
    depths = tuple(int(x) for x in json.loads(a.depths.read_text())) if a.depths else None
    rows = []
    print(
        "| design | dealing | identifiers | lift | power (pool) | power (window) | "
        "null sd (window) | power (per identifier) |"
    )
    print("|---|---|---|---|---|---|---|---|")
    for design in DESIGNS:
        for n in (int(x) for x in _floats(a.identifiers)):
            for lift in _floats(a.lifts):
                sc = Scenario(n, lift, design, dealing=a.dealing, window=a.window, depths=depths)
                r = power(sc, reps=a.reps, seed=a.seed)
                if design == "rotation":
                    r["identifier"] = {"power": identifier_power(sc, reps=a.reps, seed=a.seed)}
                rows.append(r)
                ident = f"{r['identifier']['power']:.2f}" if "identifier" in r else "n/a"
                print(
                    f"| {design} | {a.dealing} | {n} | {lift:.2f} | {r['pool']['power']:.2f} | "
                    f"{r['window']['power']:.2f} | {r['window']['null_sd']:.0f} | {ident} |"
                )
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(rows, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
