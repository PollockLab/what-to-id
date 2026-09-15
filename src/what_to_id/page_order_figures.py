"""One schematic figure per list order, drawn from the real order code on made-up records.

Each figure shows made-up records in the space the order looks at (time, map cells, photo
likeness, distance to verified photos, or place against a species' verified records), numbers
them, runs the order from arms.py, and cuts the result into batches of up to 4 in a strip below. The
points take the colour of the batch they land in, so the reader can follow each record.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from what_to_id.arms import GapFirst, Novelty, Recency, Similarity, Surprise
from what_to_id.page_svg import circle, line, rect, svg, text
from what_to_id.surprise import tail_prob

BS = 4  # batch size in the figures
_T0 = pd.Timestamp("2026-09-01T00:00:00Z")


def _pool(n: int, hours: list[float], **cols) -> pd.DataFrame:
    """Made-up records 1..n, added `hours` after a fixed time, in one taxon group."""
    created = [_T0 + pd.Timedelta(hours=h) for h in hours]
    return pd.DataFrame(
        {"id": np.arange(1, n + 1), "iconic_taxon": "Aves", "created_at": created, **cols}
    )


def _batch_of(order: np.ndarray) -> np.ndarray:
    """Batch number (0-based) of each record position, from the served order."""
    out = np.empty(len(order), dtype=int)
    out[order] = np.arange(len(order)) // BS
    return out


def _dot(x: float, y: float, n: int, batch: int, r: float = 9) -> str:
    return circle(x, y, r, f"b{batch % 3 + 1}") + text(x, y + 3.9, str(n), "ink", anchor="middle")


def _strip(order: np.ndarray, y: float) -> tuple[str, float]:
    """The served order as numbered squares, cut into batches of up to BS."""
    parts = [text(6, y + 11, f"Served order, cut into batches of up to {BS}", "tb", size=11)]
    n_batches = math.ceil(len(order) / BS)
    gap = 12
    # Fit every batch in the 400-wide view: shrink squares when there are more than 3 batches.
    sq = min(24.0, (388 - gap * (n_batches - 1)) / (n_batches * BS) - 3)
    x, top = 6.0, y + 20
    for i, pos in enumerate(order):
        b = i // BS
        if i and i % BS == 0:
            x += gap
        parts.append(rect(x, top, sq, sq, f"b{b % 3 + 1}", rx=3))
        parts.append(text(x + sq / 2, top + 16, str(int(pos) + 1), "ink", anchor="middle"))
        if i % BS == 0:
            n_in = min(BS, len(order) - i)
            w = n_in * (sq + 3) - 3
            parts.append(line(x, top + sq + 5, x + w, top + sq + 5, "br"))
            parts.append(text(x + w / 2, top + sq + 17, f"batch {b + 1}", "m", anchor="middle"))
        x += sq + 3
    return "".join(parts), top + sq + 22


def _finish(panel: str, order: np.ndarray, y: float, label: str) -> str:
    strip, h = _strip(order, y)
    seq = ", ".join(str(int(p) + 1) for p in order)
    return svg(h, f"{label} Served order: {seq}.", panel + strip, max_px=620)


def newest_figure() -> str:
    hours = [3, 40, 12, 71, 55, 20, 64, 8, 33, 47, 26, 60]
    pool = _pool(len(hours), hours)
    order = Recency().order(pool, seed=0)
    batch = _batch_of(order)
    x0, x1, ya = 20, 380, 96
    parts = [line(x0, ya, x1, ya, "ax")]
    parts.append(text(x0, ya + 16, "older", "m") + text(x1, ya + 16, "newer", "m", anchor="end"))
    parts.append(text((x0 + x1) / 2, ya + 16, "time the record was added", "m", anchor="middle"))
    span = max(hours)
    for i, h in enumerate(hours):
        x = x0 + 10 + (x1 - x0 - 20) * h / span
        y = ya - 22 - (i % 3) * 22
        parts.append(line(x, y + 8, x, ya, "tick") + _dot(x, y, i + 1, batch[i]))
    return _finish("".join(parts), order, ya + 26, "Twelve made-up records on a time line.")


def gap_figure() -> str:
    cols, rows, cw, ch, gx, gy = 6, 4, 44, 30, 10, 8
    rng = np.random.default_rng(3)
    score = np.round(rng.uniform(0, 1, (rows, cols)), 2)
    cells = [(1, 0), (4, 1), (2, 2), (0, 3), (5, 3), (3, 1), (1, 2), (4, 3), (2, 0), (5, 0)]
    pool_score = [float(score[r, c]) for c, r in cells] + [np.nan, np.nan]
    hours = [5, 50, 22, 61, 14, 38, 70, 29, 44, 9, 66, 18]
    pool = _pool(len(hours), hours, cell_score=pool_score)
    order = GapFirst().order(pool, seed=0)
    batch = _batch_of(order)
    parts = []
    for r in range(rows):
        for c in range(cols):
            level = min(4, int(score[r, c] * 5))
            parts.append(rect(gx + c * cw, gy + r * ch, cw - 2, ch - 2, f"s{level}"))
    for i, (c, r) in enumerate(cells):
        parts.append(_dot(gx + c * cw + cw / 2 - 1, gy + r * ch + ch / 2 - 1, i + 1, batch[i]))
    ox = gx + cols * cw + 14
    parts.append(rect(ox, gy, 400 - ox - 6, rows * ch - 2, "far", rx=4))
    parts.append(text(ox + 6, gy + 15, "over 20 km from", "m"))
    parts.append(text(ox + 6, gy + 28, "a cell centre:", "m"))
    parts.append(text(ox + 6, gy + 41, "no score", "m"))
    for j in range(2):
        parts.append(_dot(ox + 26 + j * 34, gy + 78, 11 + j, batch[10 + j]))
    ly = gy + rows * ch + 12
    parts.append(text(gx, ly + 2, "map score:", "m"))
    for level in range(5):
        parts.append(rect(gx + 70 + level * 26, ly - 8, 24, 12, f"s{level}"))
    parts.append(
        text(gx + 70, ly + 16, "0", "m") + text(gx + 70 + 128, ly + 16, "1", "m", anchor="end")
    )
    label = (
        "Twelve made-up records in a grid of map cells shaded by score. Two records lie too far "
        "from any cell."
    )
    return _finish("".join(parts), order, ly + 22, label)


def _unit(P: np.ndarray, c: float = 1.6) -> np.ndarray:
    X = np.column_stack([P, np.full(len(P), c)])
    return X / np.linalg.norm(X, axis=1, keepdims=True)


def _farthest_first(X: np.ndarray, k: int, seed: int) -> np.ndarray:
    """Farthest-first start points in cosine distance, first one at random (as CoreSet does)."""
    picks = [int(np.random.default_rng(seed).integers(len(X)))]
    d = 1 - X @ X[picks[0]]
    for _ in range(k - 1):
        q = int(d.argmax())
        picks.append(q)
        d = np.minimum(d, 1 - X @ X[q])
    return np.array(picks)


LOOKALIKE_SEED = 279  # the most compact groups, over seeds 0-399, with no two dots overlapping


def lookalike_example() -> dict:
    """Made-up photo points in 4 look-alike clusters, grown and ranked as Similarity.order does."""
    rng = np.random.default_rng(LOOKALIKE_SEED)
    centres = np.array([[-0.6, -0.4], [0.55, -0.45], [-0.5, 0.5], [0.5, 0.5]])
    sizes = [4, 4, 3, 3]
    P = np.vstack([c + rng.normal(0, 0.17, (s, 2)) for c, s in zip(centres, sizes, strict=True)])
    blob = np.repeat(np.arange(4), sizes)
    score = np.clip(np.array([0.2, 0.8, 0.5, 0.35])[blob] + rng.normal(0, 0.08, len(P)), 0, 1)
    X = _unit(P)
    k = math.ceil(len(P) / BS)
    picks = _farthest_first(X, k, int(rng.integers(len(P))))
    member_of, member_sim = Similarity(".", BS)._grow(X, picks)
    # The ranking step of Similarity.order: clusters by mean map score, highest first.
    key = np.array([-np.nanmean(score[member_of == c]) for c in range(k)])
    rank = np.empty(k, dtype=int)
    rank[np.argsort(key, kind="stable")] = np.arange(k)
    order = np.lexsort((-member_sim, rank[member_of]))
    return {"P": P, "picks": picks, "member_of": member_of, "rank": rank, "order": order}


def _hull(pts: np.ndarray) -> np.ndarray:
    pts = sorted(map(tuple, pts))
    if len(pts) < 3:
        return np.array(pts)

    def turn(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def half(seq):
        out: list = []
        for p in seq:
            while len(out) >= 2 and turn(out[-2], out[-1], p) <= 0:
                out.pop()
            out.append(p)
        return out[:-1]

    return np.array(half(pts) + half(pts[::-1]))


def lookalike_figure() -> str:
    ex = lookalike_example()
    P, member_of, rank, order = ex["P"], ex["member_of"], ex["rank"], ex["order"]
    batch = _batch_of(order)
    lo, hi = P.min(0) - 0.12, P.max(0) + 0.12

    def xy(p):
        return 26 + (p[0] - lo[0]) / (hi[0] - lo[0]) * 348, 30 + (hi[1] - p[1]) / (
            hi[1] - lo[1]
        ) * 170

    parts = []
    for c in range(len(ex["picks"])):
        pts = np.array([xy(p) for p in P[member_of == c]])
        ctr = pts.mean(0)
        grown = ctr + (_hull(pts) - ctr) * 1.0 + np.sign(_hull(pts) - ctr) * 13
        poly = " ".join(f"{a:.1f},{b:.1f}" for a, b in grown)
        parts.append(f'<polygon points="{poly}" class="hull"/>')
        top = grown[:, 1].min()
        parts.append(text(ctr[0], top - 4, f"group {rank[c] + 1}", "m", anchor="middle"))
    for i, p in enumerate(P):
        x, y = xy(p)
        if i in ex["picks"]:
            parts.append(circle(x, y, 12, "seed"))
        parts.append(_dot(x, y, i + 1, batch[i]))
    label = (
        "Fourteen made-up photos placed by likeness; four start photos each grow a group of up to "
        "four; groups are ranked by mean map score."
    )
    return _finish("".join(parts), order, 224, label)


def unfamiliar_example() -> dict:
    rng = np.random.default_rng(5)
    R2 = np.vstack([rng.normal((-0.4, -0.2), 0.16, (8, 2)), rng.normal((0.35, 0.3), 0.14, (7, 2))])
    Q2 = np.array(
        [
            [-0.3, -0.1],
            [0.9, -0.5],
            [0.3, 0.2],
            [-0.9, 0.6],
            [0.0, 0.05],
            [0.55, -0.1],
            [-0.55, -0.45],
            [0.2, 0.75],
        ]
    )
    X, R = _unit(Q2).astype(np.float32), _unit(R2).astype(np.float32)
    pool = _pool(len(Q2), [10, 30, 50, 20, 60, 40, 5, 25])
    nov = Novelty({"Aves": Path("pool")}, {"Aves": Path("ref")})
    nov._pool._cache["pool"] = (pool["id"].to_numpy(dtype=np.int64), X)
    nov._ref._cache["ref"] = (np.arange(100, 100 + len(R2), dtype=np.int64), R)
    order = nov.order(pool, seed=0)
    near = (X @ R.T).argmax(1)
    return {"Q": Q2, "R": R2, "near": near, "dist": nov.distances(X, R), "order": order}


def unfamiliar_figure() -> str:
    ex = unfamiliar_example()
    Q, R, order = ex["Q"], ex["R"], ex["order"]
    batch = _batch_of(order)
    allp = np.vstack([Q, R])
    lo, hi = allp.min(0) - 0.1, allp.max(0) + 0.1

    def xy(p):
        return 20 + (p[0] - lo[0]) / (hi[0] - lo[0]) * 360, 8 + (hi[1] - p[1]) / (
            hi[1] - lo[1]
        ) * 160

    parts = []
    for i, q in enumerate(Q):
        parts.append(line(*xy(q), *xy(R[ex["near"][i]]), "near"))
    parts.extend(circle(*xy(r), 4, "ref") for r in R)
    for i, q in enumerate(Q):
        parts.append(_dot(*xy(q), i + 1, batch[i]))
    label = (
        "Eight made-up photos and fifteen Research Grade photos placed by likeness, each linked "
        "to its closest verified photo."
    )
    return _finish("".join(parts), order, 180, label)


def unexpected_example() -> dict:
    rng = np.random.default_rng(11)
    ref = np.vstack([rng.normal((70, 90), 18, (30, 2)), rng.normal((150, 50), 14, (14, 2))])
    q = np.array(
        [[72, 88], [150, 55], [110, 70], [30, 30], [180, 140], [95, 110], [130, 40], [20, 150]]
    )
    surprise = tail_prob(ref, q.astype(float), h=25.0)
    pool = _pool(len(q), [10, 30, 50, 20, 60, 40, 5, 25], surprise=surprise)
    return {"ref": ref, "q": q, "surprise": surprise, "order": Surprise().order(pool, seed=0)}


def unexpected_figure() -> str:
    ex = unexpected_example()
    ref, q, order = ex["ref"], ex["q"], ex["order"]
    batch = _batch_of(order)

    sx = 1.85  # view units per map km across; the view is wider than tall

    def xy(p):
        return 16 + p[0] * sx, 10 + (170 - p[1]) * 0.95

    parts = [rect(8, 4, 384, 168, "far", rx=4)]
    parts.extend(circle(*xy(r), 3.5, "ref") for r in ref)
    for i, p in enumerate(q):
        x, y = xy(p)
        parts.append(_dot(x, y, i + 1, batch[i]))
        parts.append(text(x + 11, y - 7, f"{ex['surprise'][i]:.2f}", "m"))
    parts.append(line(20, 166, 20 + 25 * sx, 166, "ax") + text(26 + 25 * sx, 169, "25 km", "m"))
    label = (
        "Eight made-up records of one species on a map, among its verified records, each with "
        "its tail probability."
    )
    return _finish("".join(parts), order, 180, label)


ORDER_FIGURES = {
    "recency": newest_figure,
    "gap_first": gap_figure,
    "similarity": lookalike_figure,
    "novelty": unfamiliar_figure,
    "surprise": unexpected_figure,
}
