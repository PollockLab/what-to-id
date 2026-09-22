"""Design, split, serving and analysis figures for the method section.

Each function returns one inline <svg>. Where the build's own data would be private (which list
is which, who identified what), the figure runs the real code on a small made-up input instead:
the deal calls assign.assign.
"""

from __future__ import annotations

import random
import zlib

import numpy as np
import pandas as pd

from what_to_id import assign as assign_mod
from what_to_id.page_svg import (
    arrow,
    fmt,
    line,
    lines,
    list_cls,
    rect,
    svg,
    text,
    wrap,
)


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
