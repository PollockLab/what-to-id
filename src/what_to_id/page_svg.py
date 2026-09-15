"""Small inline-SVG helpers for the method figures. No JavaScript, no libraries.

Every figure is drawn in a viewBox about 400 units wide, so 11-unit text stays near 10 px on a
400 px phone. Colours come from CSS classes in page_method.METHOD_CSS, never inline fills, so the
figures follow the page tokens.
"""

from __future__ import annotations

from html import escape

# Four (five with the opt-in order) list colours from the Okabe-Ito palette. They carry no
# order: none is lighter, darker or "first".
N_LIST_COLOURS = 5
W = 400
CHAR = 0.56  # rough glyph width, in font-size units, for wrapping


def svg(h: float, label: str, body: str, *, w: int = W, max_px: int | None = None) -> str:
    """One accessible inline SVG: viewBox, width 100%, a max-width, role img and a label."""
    cap = max_px or int(w * 1.6)
    return (
        f'<svg viewBox="0 0 {w} {h:g}" width="100%" style="max-width:{cap}px" role="img" '
        f'aria-label="{escape(label, quote=True)}" xmlns="http://www.w3.org/2000/svg">'
        f"{body}</svg>"
    )


MIN_FONT = 11  # 10.1 px on a 400 px phone, where the 400-unit view is 368 px wide


def text(x: float, y: float, s: str, cls: str = "t", *, anchor: str = "start", size=11) -> str:
    if size < MIN_FONT:
        raise ValueError(f"font size {size} is below {MIN_FONT}, too small on a phone")
    a = "" if anchor == "start" else f' text-anchor="{anchor}"'
    return f'<text x="{x:g}" y="{y:g}" class="{cls}" font-size="{size}"{a}>{escape(s)}</text>'


def wrap(s: str, width: float, size: float = 11) -> list[str]:
    """Greedy word wrap to lines that fit `width` units at `size`."""
    per = max(8, int(width / (CHAR * size)))
    lines: list[str] = []
    cur = ""
    for word in s.split():
        if cur and len(cur) + 1 + len(word) > per:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    if cur:
        lines.append(cur)
    return lines


def lines(x: float, y: float, rows: list[str], cls: str = "t", *, anchor="start", size=11) -> str:
    step = size * 1.3
    return "".join(
        text(x, y + i * step, r, cls, anchor=anchor, size=size) for i, r in enumerate(rows)
    )


def rect(x, y, w, h, cls: str, *, rx: float = 0, extra: str = "") -> str:
    r = f' rx="{rx:g}"' if rx else ""
    return f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" class="{cls}"{r}{extra}/>'


def line(x1, y1, x2, y2, cls: str = "ln") -> str:
    return f'<line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" class="{cls}"/>'


def circle(x, y, r, cls: str, extra: str = "") -> str:
    return f'<circle cx="{x:g}" cy="{y:g}" r="{r:g}" class="{cls}"{extra}/>'


def arrow(x1, y1, x2, y2) -> str:
    """A line with a small filled head at (x2, y2), pointing down, right or left."""
    if x1 == x2:
        d = 1 if y2 > y1 else -1
        head = f"{x2 - 4:g},{y2 - 6 * d:g} {x2 + 4:g},{y2 - 6 * d:g} {x2:g},{y2:g}"
    else:
        d = 1 if x2 > x1 else -1
        head = f"{x2 - 6 * d:g},{y2 - 4:g} {x2 - 6 * d:g},{y2 + 4:g} {x2:g},{y2:g}"
    return line(x1, y1, x2, y2, "ar") + f'<polygon points="{head}" class="arh"/>'


def list_cls(k: int) -> str:
    """CSS class for list number k (0-based). Numbers only: never a letter, never an order."""
    return f"c{k % N_LIST_COLOURS + 1}"


def fmt(n: float) -> str:
    return f"{int(n):,}"


def range_words(lo: int, hi: int) -> str:
    """A small range in words: "3", "2 or 3", "2 to 5"."""
    return str(lo) if lo == hi else f"{lo} {'or' if hi == lo + 1 else 'to'} {hi}"
