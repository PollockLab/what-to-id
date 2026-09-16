"""Section 8 numbers and figures: simulated power of the confirmatory family.

The values are copied from the grid ``python -m what_to_id.power_weighted`` writes, 1,000 runs
per point, with seed 0 (the figures) and a check run with seed 1 (the ranges in the text).
``WEIGHTED``: the "power" field of the rows with outcome "weighted" and exposure "blitz", per
id_factor. ``PLAIN``: the "power" field of the rows with outcome "plain", per lift.
``SCORE_MET``: the mean over one exposure's seed 0 rows of score_met_control and
score_met_data_poor. ``PREVIEW_NULL``: power plus behind of the preview rows at id_factor 1.0,
over both seeds. ``PREVIEW_AHEAD``: the largest "power" of any preview row, over both seeds.
``BLITZ_BEHIND``: the largest "behind" of any weighted blitz row, over both seeds.
``PREVIEW_SPAN_DAYS``: newest minus oldest created_at per group in the scored preview pool.
``NOCAP``: the one row of ``NOCAP_RUN``, the blitz model with no cap on batches.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import ROUND_HALF_UP, Decimal

from what_to_id.page_svg import W, circle, line, svg, text

IDS = (10, 15, 20, 25, 30, 40, 50)
WEIGHTED = {
    0: {
        0.6: (0.113, 0.235, 0.383, 0.458, 0.53, 0.687, 0.79),
        0.8: (0.513, 0.807, 0.931, 0.959, 0.979, 0.992, 0.998),
        1.0: (0.809, 0.973, 0.997, 0.999, 1.0, 1.0, 1.0),
    },
    1: {
        0.6: (0.112, 0.257, 0.305, 0.448, 0.574, 0.688, 0.793),
        0.8: (0.507, 0.804, 0.91, 0.963, 0.987, 0.996, 0.998),
        1.0: (0.801, 0.976, 0.997, 1.0, 1.0, 1.0, 1.0),
    },
}
PLAIN = {
    0: {
        0.1: (0.061, 0.143, 0.224, 0.312, 0.403, 0.604, 0.688),
        0.2: (0.207, 0.45, 0.657, 0.811, 0.915, 0.987, 0.995),
        0.3: (0.398, 0.716, 0.907, 0.978, 0.993, 1.0, 1.0),
    },
    1: {
        0.1: (0.053, 0.139, 0.224, 0.322, 0.386, 0.58, 0.708),
        0.2: (0.207, 0.449, 0.669, 0.782, 0.915, 0.985, 0.99),
        0.3: (0.407, 0.708, 0.909, 0.971, 0.99, 1.0, 1.0),
    },
}
# control, data-poor; five decimals so the page's three-decimal rounding is not a double rounding
SCORE_MET = {"blitz": (0.15846, 0.36064), "preview": (0.16009, 0.16036)}
PREVIEW_NULL = (0.011, 0.038, 0.0248)  # smallest, largest, mean
PREVIEW_AHEAD = 0.019
PREVIEW_PER_GROUP = 1000
PREVIEW_SPAN_DAYS = {"Plantae": 0.71, "Actinopterygii": 81.8}
NULL_RUNS = 14_000  # preview rows at id_factor 1.0: 7 participant counts, 2 seeds, 1,000 runs
BLITZ_BEHIND = 0.001
_RUN = (
    "uv run python -m what_to_id.power_weighted --pool data/pool_sample_2026-09-11.parquet "
    "--webapp-dir ../where-to-blitz/cluster_results/ca"
)
# The output names are those of the files the values above were copied from.
RERUN_ARGS = tuple(
    f"--reps 1000 --seed {s} --out {out}"
    for s, out in ((0, "weighted_grid.json"), (1, "weighted_grid_seed1.json"))
)
RERUN = tuple(f"{_RUN} {args}" for args in RERUN_ARGS)
# runs, participants, score met on the control and on the data-poor list, share ahead
NOCAP = (300, 20, 0.15909, 0.15779, 0.0)
NOCAP_ARGS = (
    '--identifiers 20 --factors 1.0 --exposures blitz --lifts "" --max-batches 0 '
    "--reps 300 --seed 0 --out weighted_nocap.json"
)
NOCAP_RUN = f"{_RUN} {NOCAP_ARGS}"


def p2(x: float) -> str:
    """Two decimals, halves rounded up: every value is an exact count out of 1,000 runs."""
    return str(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def power_at(grid: Mapping[int, Mapping[float, Sequence[float]]], key: float, n: int) -> str:
    """Seed 0 and seed 1 power at n participants: one value, or a range when they round apart."""
    i = IDS.index(n)
    a, b = sorted((grid[0][key][i], grid[1][key][i]))
    return p2(a) if p2(a) == p2(b) else f"{p2(a)} to {p2(b)}"


def power_panel(series: Mapping[str, Sequence[float]], what: str) -> str:
    """Power against participants, one line per series, a legend and a dashed 0.8 line."""
    if not series:
        raise ValueError("power_panel needs at least one series")
    x0, x1, y0, y1 = 44, 388, 26, 206
    top_n = max(IDS)

    def px(n: float) -> float:
        return x0 + (x1 - x0) * n / top_n

    def py(p: float) -> float:
        return y1 - (y1 - y0) * p

    parts = []
    for p in (0, 0.2, 0.4, 0.6, 0.8, 1.0):
        parts.append(line(x0, py(p), x1, py(p), "grid"))
        parts.append(text(x0 - 5, py(p) + 4, f"{p:.1f}", "m", anchor="end"))
    for n in IDS:
        parts.append(text(px(n), y1 + 15, str(n), "m", anchor="middle"))
    parts.append(line(x0, py(0.8), x1, py(0.8), "lvl"))
    parts.append(line(x0, y1, x1, y1, "ax") + line(x0, y0, x0, y1, "ax"))
    parts.append(text((x0 + x1) / 2, y1 + 31, "participants", "m", anchor="middle"))
    parts.append(
        f'<text x="12" y="{(y0 + y1) / 2:g}" class="m" font-size="11" text-anchor="middle" '
        f'transform="rotate(-90 12 {(y0 + y1) / 2:g})">power</text>'
    )
    # The legend sits in the lower right: past 30 participants every line is above 0.4.
    lx, ly = px(30), py(0.3)
    for i, (name, row) in enumerate(series.items()):
        if len(row) != len(IDS):
            raise ValueError(f"series {name!r} has {len(row)} values for {len(IDS)} points")
        cls = f"pw{i + 1}"
        pts = list(zip(IDS, row, strict=True))
        path = " ".join(f"{px(n):.1f},{py(p):.1f}" for n, p in pts)
        parts.append(f'<polyline points="{path}" class="{cls}"/>')
        parts.extend(circle(px(n), py(p), 3, f"{cls}d") for n, p in pts)
        y = ly + i * 18
        parts.append(line(lx, y - 4, lx + 22, y - 4, cls) + circle(lx + 11, y - 4, 3, f"{cls}d"))
        parts.append(text(lx + 28, y, name, cls + "t"))
    label = f"Simulated power against participants, {what}: " + "; ".join(
        f"{name}, {n} participants, {p2(p)}"
        for name, row in series.items()
        for n, p in zip(IDS, row, strict=True)
    )
    return svg(y1 + 36, label, "".join(parts), w=W, max_px=640)
