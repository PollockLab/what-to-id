"""Design, split, serving and analysis figures for the method section.

Each function returns one inline <svg>. Where the build's own data would be private (which list
is which, who identified what), the figure runs the real code on a small made-up input instead:
the deal calls assign.assign, the test figure calls analysis.sign_flip_p.
"""

from __future__ import annotations

import random
import zlib
from itertools import product

import numpy as np
import pandas as pd

from what_to_id import assign as assign_mod
from what_to_id.analysis import record_shuffle_p, sign_flip_p
from what_to_id.page_svg import (
    W,
    arrow,
    circle,
    fmt,
    line,
    lines,
    list_cls,
    rect,
    svg,
    text,
    wrap,
)

# Power by simulation (power.py), lift 0.2, 2000 replicates, seed 0, from the two POWER_COMMAND
# runs. "every" lines: the "power (per identifier)" column of the rotation rows (the sign-flip
# test at Holm's first-step level; identifier_power ignores dealing, competition and the cap).
# "one" line: the "power (window)" column of the sets rows of the 4-list run (window-total test,
# simulated null, random-start dealing).
_IDS = (5, 10, 15, 25, 40, 60, 100)
_POWER_ROWS = {
    "every-2": (0.00, 0.63, 0.89, 0.99, 1.00, 1.00, 1.00),
    "every-4": (0.00, 0.22, 0.46, 0.80, 0.98, 1.00, 1.00),
    "one-4": (0.06, 0.06, 0.07, 0.07, 0.08, 0.08, 0.09),
}
POWER: list[dict] = [
    {"series": key, "identifiers": n, "lift": 0.2, "power": p}
    for key, row in _POWER_ROWS.items()
    for n, p in zip(_IDS, row, strict=True)
]
POWER_COMMAND = tuple(
    "uv run python -m what_to_id.power --identifiers 5,10,15,25,40,60,100 --lifts 0.2 "
    f"--reps 2000 --seed 0 --dealing random-start --n-arms {k}"
    for k in (4, 2)
)
SERIES_NAMES = {
    "every-2": "Every list, 2 lists",
    "every-4": "Every list, 4 lists",
    "one-4": "One list each, 4 lists",
}


def _box(x: float, y: float, w: float, title: str, body: str, cls: str = "bx"):
    rows = wrap(body, w - 16, 11)
    h = 24 + len(rows) * 14.3 + 2
    out = rect(x, y, w, h, cls, rx=6) + text(x + 8, y + 16, title, "tb", size=11.5)
    return out + lines(x + 8, y + 31, rows, "m", size=11), h


def flow_figure(f: dict) -> str:
    """CONSORT-style flow with this build's counts. `f` holds only arm-blind aggregates."""
    mx, mw, sx, sw = 6, 240, 262, 132
    not_served = f["pool_rows"] - f["served_rows"]
    if not_served:
        not_served_text = (
            f"{fmt(not_served)} records. Only the first {f['max_batches']} batches of each list "
            "in each taxon group are served."
        )
    elif f["max_batches"]:
        not_served_text = (
            f"None. No list has more than {f['max_batches']} batches in a taxon group, the cap."
        )
    else:
        not_served_text = "None. No cap on batches."
    steps = [
        ("Records pulled", f"{fmt(f['pool_rows'])} BC records that need an ID, with a photo", None),
        ("Random split", f"each record to one of {f['k']} lists", None),
        (
            "Sorted and cut",
            f"each list sorts its records, per taxon group, and cuts batches of up to "
            f"{fmt(f['batch_size'])}",
            ("Not served", not_served_text),
        ),
        (
            "Served",
            f"{fmt(f['served_rows'])} records in {fmt(f['n_batches'])} batches, "
            f"{fmt(f['list_min'])} to {fmt(f['list_max'])} records per list",
            None,
        ),
        (
            "Rotation",
            "each browser takes the lists in its own random turn order",
            (
                "Participants",
                "identifiers in the blitz's iNaturalist project or on its sign-up form",
            ),
        ),
        (
            "Read-back and comparison",
            "each participant's count on each list against the control",
            None,
        ),
    ]
    y, parts = 4.0, []
    for i, (title, body, side) in enumerate(steps):
        b, h = _box(mx, y, mw, title, body)
        parts.append(b)
        if side:
            sb, sh = _box(sx, y, sw, side[0], side[1], "bx side")
            parts.append(sb + arrow(mx + mw, y + 18, sx - 1, y + 18))
            h = max(h, sh)
        y += h
        if i < len(steps) - 1:
            parts.append(arrow(mx + mw / 2, y + 1, mx + mw / 2, y + 15))
            y += 17
    label = (
        f"Flow of records: {fmt(f['pool_rows'])} pulled, split into {f['k']} lists, cut into "
        f"{fmt(f['n_batches'])} batches, {fmt(f['served_rows'])} served, then rotation and "
        "read-back."
    )
    return svg(y + 4, label, "".join(parts), max_px=620)


CHANCE_SIMS = 4000


def chance_band(n: int, k: int) -> tuple[int, int, float]:
    """Smallest and largest list size that chance gives when n records go to k lists at random.

    Returns the 2.5th percentile of the smallest list, the 97.5th percentile of the largest list
    over CHANCE_SIMS seeded splits, and the share of splits that fall outside that band.
    """
    c = np.random.default_rng(0).multinomial(n, [1 / k] * k, size=CHANCE_SIMS)
    lo, hi = np.percentile(c.min(1), 2.5), np.percentile(c.max(1), 97.5)
    return int(lo), int(hi), float(((c.min(1) < lo) | (c.max(1) > hi)).mean())


def chance_outside(sizes: list[int], k: int) -> tuple[int, float]:
    """How many of these k list sizes fall outside the chance band, and how many chance puts there.

    The band is chance_band's, as the share figure draws it. The second value is the mean, over
    the same CHANCE_SIMS seeded splits, of the number of lists below or above it, so both counts
    use one band and one rule.
    """
    n = sum(sizes)
    c = np.random.default_rng(0).multinomial(n, [1 / k] * k, size=CHANCE_SIMS)
    lo, hi = chance_band(n, k)[:2]
    seen = sum(1 for s in sizes if s < lo or s > hi)
    return seen, float(((c < lo) | (c > hi)).sum(1).mean())


def list_share_figure(groups: list[dict], k: int, band: bool) -> str:
    """Per taxon group: the smallest to the largest list as a share of the group's records.

    `groups` holds arm-blind aggregates only (name, records, recs). With `band`, a shaded band
    shows the range chance gives (chance_band), so a reader can see whether a spread is unusual.
    """
    even = 100 / k
    rows = []  # (short name, smallest %, largest %, chance band in % or None)
    for g in groups:
        n = g["records"] or 1
        pct = tuple(100 * r / n for r in chance_band(n, k)[:2]) if band else None
        lo, hi = (100 * r / n for r in g["recs"])
        rows.append((g["name"].split(" (")[0], lo, hi, pct))
    far = [abs(v - even) for _, lo, hi, pct in rows for v in (lo, hi, *(pct or ()))]
    span = max(1, int(np.ceil(max(far, default=1))))
    x0, x1, top, step = 130, 388, 26 if band else 8, 22

    def xs(v: float) -> float:
        return x0 + (x1 - x0) * (v - even + span) / (2 * span)

    parts = []
    if band:
        parts += [
            rect(x0, 4, 18, 11, "band"),
            text(x0 + 23, 13, "chance, 2.5 to 97.5%", "m"),
            line(x0 + 150, 9.5, x0 + 168, 9.5, "rng"),
            text(x0 + 173, 13, "this build", "m"),
        ]
    for i, (name, lo, hi, pct) in enumerate(rows):
        y = top + i * step
        if pct:
            parts.append(rect(xs(pct[0]), y, xs(pct[1]) - xs(pct[0]), 16, "band"))
        parts.append(text(x0 - 6, y + 12, name, "t", anchor="end"))
        parts.append(line(xs(lo), y + 8, max(xs(hi), xs(lo) + 1), y + 8, "rng"))
    bottom = top + len(rows) * step
    parts.append(line(xs(even), top - 3, xs(even), bottom, "lvl"))
    parts.append(line(x0, bottom + 2, x1, bottom + 2, "ax"))
    for v in (even - span, even - span / 2, even, even + span / 2, even + span):
        parts.append(line(xs(v), bottom + 2, xs(v), bottom + 6, "tick"))
        parts.append(text(xs(v), bottom + 18, f"{v:g}%", "m", anchor="middle"))
    label = "Smallest and largest list, as a share of each taxon group's records: " + "; ".join(
        f"{name} {lo:.1f} to {hi:.1f} percent" for name, lo, hi, *_ in rows
    )
    return svg(bottom + 24, label, "".join(parts), max_px=620)


DEAL_SEED = 7


def deal_example(k: int) -> tuple[pd.DataFrame, list[str], int]:
    """Twenty made-up bird records in two observer buckets (0 and 1), and k made-up lists."""
    users = [next(u for u in range(1, 100) if zlib.crc32(str(u).encode()) % 3 == b) for b in (0, 1)]
    pool = pd.DataFrame(
        {
            "id": np.arange(1, 21),
            "iconic_taxon": "Aves",
            "user_id": [users[0]] * 10 + [users[1]] * 10,
        }
    )
    return pool, [f"list{i + 1}" for i in range(k)], DEAL_SEED


def deal_figure(k: int) -> str:
    """The seeded stratified deal, from assign.assign on the made-up pool."""
    pool, arms, seed = deal_example(k)
    arm_of = assign_mod.assign(pool, arms, seed=seed).set_index("id")["arm"]
    st = assign_mod.strata(pool).to_numpy()
    ids = pool["id"].to_numpy(dtype=np.int64)
    x0, step, sq = 22, 33, 28
    parts, y = [], 4.0
    for i, stratum in enumerate(sorted(set(st))):
        # The same per-stratum shuffle assign() deals from; the colours below come from assign().
        seq = assign_mod._stratum_rng(seed, stratum).permutation(ids[st == stratum])
        bucket = stratum.split("|")[1]
        parts.append(
            text(x0, y + 12, f"Birds, observer bucket {bucket}: 10 records, shuffled", "tb")
        )
        top = y + 20
        for j, rid in enumerate(seq):
            n = arms.index(arm_of[int(rid)])
            x = x0 + j * step
            attr = f' data-rec="{int(rid)}" data-list="{n + 1}"'
            parts.append(rect(x, top, sq, sq, list_cls(n), rx=4, extra=attr))
            parts.append(text(x + sq / 2, top + 18, str(int(rid)), "ink", anchor="middle", size=11))
            parts.append(text(x + sq / 2, top + sq + 12, f"L{n + 1}", "m", anchor="middle"))
        sizes = [int(sum(arm_of[int(r)] == a for r in seq)) for a in arms]
        note = f"Deal starts at list {i % k + 1}. List sizes here: {', '.join(map(str, sizes))}."
        parts.append(text(x0, top + sq + 28, note, "m"))
        y = top + sq + 40
    for n in range(k):
        x = x0 + n * 72
        parts.append(
            rect(x, y + 2, 12, 12, list_cls(n), rx=2) + text(x + 17, y + 12, f"List {n + 1}", "m")
        )
    label = (
        f"Two made-up sets of 10 bird records, one per observer bucket, each shuffled and dealt to "
        f"{k} lists in turn. The second set starts one list later."
    )
    return svg(y + 20, label, "".join(parts), max_px=620)


def _visit_row(y: float, who: str, cells: list[tuple[str, str]], w: float, gap: float) -> str:
    parts = [text(6, y + 17, who, "t")]
    x = 84
    for i, (label, cls) in enumerate(cells):
        parts.append(
            rect(x, y, w, 24, cls, rx=4) + text(x + w / 2, y + 16, label, "ink", anchor="middle")
        )
        if i < len(cells) - 1:
            parts.append(arrow(x + w + 1, y + 12, x + w + gap - 2, y + 12))
        x += w + gap
    return "".join(parts)


def serving_figure(k: int, n_batches: int) -> str:
    """Top: turn orders of two made-up identifiers. Bottom: random start inside one list.

    Panel titles carry no letter, since a letter would read as a list name.
    """
    parts = [text(6, 14, "Turn order: each press takes the next list", "tb")]
    y = 24.0
    for who, seed, presses in (("Identifier 1", 1, min(2 * k, 7)), ("Identifier 2", 2, k)):
        cycle = random.Random(seed).sample(range(k), k)
        cells = [(str(cycle[i % k] + 1), list_cls(cycle[i % k])) for i in range(presses)]
        parts.append(_visit_row(y, who, cells, 24, 21))
        y += 34
    n = max(2, min(n_batches, 4))
    parts.append(text(6, y + 16, f"Start batch: one list and taxon group, {n} batches", "tb"))
    y += 26
    for who, offset in (("Identifier 1", 1), ("Identifier 2", 0)):
        cells = [(f"batch {(offset + i) % n + 1}", "c1") for i in range(n)]
        parts.append(_visit_row(y, who, cells, 58, 20))
        y += 34
    parts.append(text(84, y + 6, "Each starts at a random batch, then wraps around.", "m"))
    label = (
        "Turn order: two made-up identifiers press Next batch. The lists come in each one's own "
        f"random turn order. Start batch: inside one list of {n} batches, each identifier starts "
        "at a random batch and wraps around."
    )
    return svg(y + 14, label, "".join(parts), max_px=620)


SHUFFLE_TOTALS = (0, 1, 1, 2, 2, 3, 4, 5)
SHUFFLE_ARMS = ("c", "c", "c", "c", "t", "t", "t", "t")
SHUFFLE_REPS = 2000


def shuffle_example() -> dict:
    """The record-level worked example: 8 made-up records, their totals, and the real p."""
    served = pd.DataFrame({"id": range(len(SHUFFLE_ARMS)), "arm": list(SHUFFLE_ARMS)})
    totals = pd.Series(np.asarray(SHUFFLE_TOTALS, dtype=np.float64), index=served["id"])
    on = served["arm"].to_numpy()
    obs = float(totals.to_numpy()[on == "t"].sum() - totals.to_numpy()[on == "c"].sum())
    return {
        "totals": SHUFFLE_TOTALS,
        "totals_text": ", ".join(str(t) for t in SHUFFLE_TOTALS),
        "control": int(
            sum(t for t, a in zip(SHUFFLE_TOTALS, SHUFFLE_ARMS, strict=True) if a == "c")
        ),
        "treated": int(
            sum(t for t, a in zip(SHUFFLE_TOTALS, SHUFFLE_ARMS, strict=True) if a == "t")
        ),
        "obs": obs,
        "reps": SHUFFLE_REPS,
        "p": record_shuffle_p(totals, served, arm="t", control="c", reps=SHUFFLE_REPS, seed=0),
    }


SIGNFLIP_DIFFS = (4, 7, -2, 3, 9, 1, -3, 5)


def signflip_example() -> dict:
    """The worked example: 8 made-up differences, every sign pattern, and the real p."""
    d = np.asarray(SIGNFLIP_DIFFS, dtype=np.float64)
    sums = np.array(list(product((-1.0, 1.0), repeat=d.size))) @ d
    obs = abs(float(d.sum()))
    return {
        "diffs": d,
        "sums": sums,
        "obs": obs,
        "extreme": int((np.abs(sums) >= obs - 1e-9).sum()),
        "p": sign_flip_p(d),
    }


def signflip_figure() -> str:
    ex = signflip_example()
    d, sums, obs = ex["diffs"], ex["sums"], ex["obs"]
    parts = [text(6, 12, "Difference per person", "tb", size=11)]
    zx, unit, top = 78, 60 / float(np.abs(d).max()), 24
    for i, v in enumerate(d):
        y = top + i * 17
        x, w = (zx, v * unit) if v > 0 else (zx + v * unit, -v * unit)
        parts.append(text(8, y + 10, f"P{i + 1}", "m"))
        parts.append(rect(x, y, w, 12, "pos" if v > 0 else "neg"))
        lx, anchor = (x + w + 3, "start") if v > 0 else (x - 3, "end")
        parts.append(text(lx, y + 10, f"{int(v):+d}", "m", anchor=anchor))
    base = top + len(d) * 17
    parts.append(line(zx, top - 4, zx, base, "ax"))
    parts.append(text(zx, base + 14, f"sum {int(d.sum()):+d}", "t", anchor="middle"))
    values, counts = np.unique(sums, return_counts=True)
    x0, x1, hb, hy = 182, 392, 150, 36
    span = float(np.abs(values).max())
    bw = (x1 - x0) / (len(values) + 1)
    parts.append(text(x0, 12, f"All {len(sums)} sign patterns", "tb", size=11))

    def sx(v: float) -> float:
        return x0 + (v + span) / (2 * span) * (x1 - x0 - bw) + bw / 2

    peak = counts.max()
    for v, c in zip(values, counts, strict=True):
        h = (hb - 20) * c / peak
        cls = "tail" if abs(v) >= obs - 1e-9 else "hist"
        parts.append(rect(sx(v) - bw / 2 + 0.5, hy + hb - 20 - h, bw - 1, h, cls))
    axis = hy + hb - 20
    parts.append(line(x0, axis, x1, axis, "ax"))
    for v in (-obs, obs):
        parts.append(line(sx(v), hy + 4, sx(v), axis, "obs"))
    parts.append(text(sx(obs), hy - 3, f"observed sum {int(obs)}", "t", anchor="end"))
    for v in (-obs, 0, obs):
        parts.append(text(sx(v), axis + 13, f"{int(v):+d}" if v else "0", "m", anchor="middle"))
    parts.append(text((x0 + x1) / 2, axis + 27, "sum after flipping signs", "m", anchor="middle"))
    label = (
        f"Left: made-up differences for 8 people, summing to {int(d.sum())}. Right: histogram of "
        f"all {len(sums)} sign-flipped sums; {ex['extreme']} are at least {int(obs)} from zero."
    )
    return svg(max(base + 22, axis + 34), label, "".join(parts), max_px=640)


def power_figure(results: list[dict]) -> str:
    """Power against identifiers, one line per series, a legend and a dashed 0.8 line."""
    if not results:
        raise ValueError("power_figure needs at least one result")
    x0, x1, y0, y1 = 44, 388, 26, 206
    top_n = max(r["identifiers"] for r in results)

    def px(n: float) -> float:
        return x0 + (x1 - x0) * n / top_n

    def py(p: float) -> float:
        return y1 - (y1 - y0) * p

    parts = []
    for p in (0, 0.2, 0.4, 0.6, 0.8, 1.0):
        parts.append(line(x0, py(p), x1, py(p), "grid"))
        parts.append(text(x0 - 5, py(p) + 4, f"{p:.1f}", "m", anchor="end"))
    for n in sorted({r["identifiers"] for r in results}):
        parts.append(text(px(n), y1 + 15, str(n), "m", anchor="middle"))
    parts.append(line(x0, py(0.8), x1, py(0.8), "lvl"))
    parts.append(line(x0, y1, x1, y1, "ax") + line(x0, y0, x0, y1, "ax"))
    parts.append(text((x0 + x1) / 2, y1 + 31, "identifiers taking part", "m", anchor="middle"))
    parts.append(
        f'<text x="12" y="{(y0 + y1) / 2:g}" class="m" font-size="11" text-anchor="middle" '
        f'transform="rotate(-90 12 {(y0 + y1) / 2:g})">power</text>'
    )
    # The legend sits in the empty lower right: past 25 identifiers the rising lines are near 1.
    lx, ly = 196, py(0.62)
    for i, key in enumerate(dict.fromkeys(r["series"] for r in results)):
        pts = sorted((r["identifiers"], r["power"]) for r in results if r["series"] == key)
        cls = f"pw{i + 1}"
        path = " ".join(f"{px(n):.1f},{py(p):.1f}" for n, p in pts)
        parts.append(f'<polyline points="{path}" class="{cls}"/>')
        parts.extend(circle(px(n), py(p), 3, f"{cls}d") for n, p in pts)
        y = ly + i * 18
        parts.append(line(lx, y - 4, lx + 22, y - 4, cls) + circle(lx + 11, y - 4, 3, f"{cls}d"))
        parts.append(text(lx + 28, y, SERIES_NAMES.get(key, key), cls + "t"))
    label = "Simulated power against number of identifiers: " + "; ".join(
        f"{SERIES_NAMES.get(r['series'], r['series'])}, {r['identifiers']} identifiers, "
        f"{r['power']:.2f}"
        for r in results
    )
    return svg(y1 + 36, label, "".join(parts), w=W, max_px=640)
