"""Inline SVG figures for the Methods section, drawn from the figure data in levels_outcome.json.

No plotting library: the page is static and the numbers are already binned by the script.
"""

from __future__ import annotations

import math

W, H, L, B, T = 640, 230, 52, 36, 26  # canvas, left and bottom margins, top band (legend)
COLOURS = {
    "none": "#b8b8b8",
    "easy": "#3a9c6a",
    "taxonomist": "#e0a528",
    "weird": "#8d6ac4",
    "mislabel": "#d64545",
}


def _x(v: float, lo: float, hi: float) -> float:
    return L + (v - lo) / (hi - lo) * (W - L - 8)


def _text(x: float, y: float, s: str, anchor: str = "middle") -> str:
    return f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}">{s}</text>'


def _frame(label: str, xlabel: str, ylabel: str, body: str) -> str:
    return (
        f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{label}">{body}'
        f"{_text((W + L) / 2, H - 4, xlabel)}"
        f'<text transform="translate(12 {(H - B) / 2:.0f}) rotate(-90)" text-anchor="middle">'
        f"{ylabel}</text></svg>"
    )


def margin_hist(fig: dict, names: dict[str, str], cuts: list[float]) -> str:
    """Stacked counts per margin bin on a log axis, one colour per level, cut-offs as lines."""
    edges, counts = fig["edges"], fig["counts"]
    lo, hi = edges[0], edges[-1]
    top = math.log10(1 + max(sum(c) for c in zip(*counts.values(), strict=True)))

    def y(n: float) -> float:
        return H - B - math.log10(1 + n) / top * (H - B - T)

    parts = []
    for i in range(len(edges) - 1):
        base, x0, w = 0, _x(edges[i], lo, hi), _x(edges[i + 1], lo, hi) - _x(edges[i], lo, hi)
        for name, c in counts.items():
            if c[i]:
                y0, y1 = y(base), y(base + c[i])
                parts.append(
                    f'<rect x="{x0:.1f}" y="{y1:.1f}" width="{w:.1f}" height="{y0 - y1:.1f}"'
                    f' fill="{COLOURS[name]}"/>'
                )
                base += c[i]
    for c in cuts:
        parts.append(
            f'<line x1="{_x(c, lo, hi):.1f}" y1="{T}" x2="{_x(c, lo, hi):.1f}" y2="{H - B}"'
            ' stroke="currentColor" stroke-dasharray="4 3"/>'
        )
    parts += [_text(L - 6, y(10**k) + 4, f"{10**k:,}", "end") for k in range(int(top) + 1)]
    for i, k in enumerate(counts):
        parts.append(
            f'<rect x="{L + 108 * i}" y="4" width="10" height="10" fill="{COLOURS[k]}"/>'
            f"{_text(L + 14 + 108 * i, 13, names[k], 'start')}"
        )
    for t in (-0.15, -0.1, -0.05, 0, 0.05, 0.1, 0.15):
        parts.append(_text(_x(t, lo, hi), H - B + 16, f"{t:g}"))
    return _frame(
        "Margin histogram by level", "margin (own minus other)", "records", "".join(parts)
    )


def corrected_by_margin(fig: dict) -> str:
    """Corrected per 1,000 in each margin bin of equal record count, bars left to right."""
    edges, rate = fig["edges"], fig["corrected_per_1000"]
    n, top = len(rate), max(fig["corrected_per_1000"]) or 1
    bw = (W - L - 8) / n

    def y(v: float) -> float:
        return H - B - v / top * (H - B - T)

    parts = []
    for i, v in enumerate(rate):
        parts.append(
            f'<rect x="{L + i * bw:.1f}" y="{y(v):.1f}" width="{bw - 1:.1f}"'
            f' height="{H - B - y(v):.1f}" fill="{COLOURS["mislabel"]}"/>'
            f"{_text(L + i * bw + bw / 2, y(v) - 3, f'{v:g}')}"
        )
    for i in range(0, n + 1, max(1, n // 5)):
        if not math.isinf(edges[i]):
            parts.append(_text(L + i * bw, H - B + 16, f"{edges[i]:.2f}"))
    return _frame(
        "Corrected per thousand by margin bin",
        "margin bin, lowest to highest, equal record counts",
        "corrected per 1,000",
        "".join(parts),
    )
