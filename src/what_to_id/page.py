"""Static, dependency-free HTML pages for identifiers: a landing page and one page per set.

Arm names never reach the HTML; pages show only the blind label (A/B/C). The label to arm
mapping lives in manifest.json alone. Wording is for BC naturalists, not for us: "set" not
"arm", "batch" for a block of records that opens as one Identify page.
"""

from __future__ import annotations

from collections.abc import Mapping
from html import escape
from pathlib import Path

import pandas as pd

from what_to_id.manifest import Manifest
from what_to_id.page_style import CSS, FONTS, JS

ARM_WORDS = ("recency", "gap_first", "similarity", "novelty", "gap first")
THUMBS_PER_BATCH = 4

GROUP_NAMES = {
    "Actinopterygii": "Fish",
    "Amphibia": "Amphibians",
    "Animalia": "Other animals",
    "Arachnida": "Spiders and allies",
    "Aves": "Birds",
    "Chromista": "Kelp and allies",
    "Fungi": "Fungi and lichens",
    "Insecta": "Insects",
    "Mammalia": "Mammals",
    "Mollusca": "Molluscs",
    "Plantae": "Plants",
    "Protozoa": "Slime moulds",
    "Reptilia": "Reptiles",
}


def group_name(group: str) -> str:
    """Plain name for an iconic taxon, with the Latin group in brackets when they differ."""
    plain = GROUP_NAMES.get(group)
    return f"{plain} ({group})" if plain else group


def _doc(title: str, body: str, *, subtitle: str = "") -> str:
    t = escape(title)
    sub = f'<p class="sub">{subtitle}</p>\n' if subtitle else ""
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f"<title>{t}</title>\n{FONTS}<style>{CSS}</style>\n</head>\n<body>\n<main>\n<h1>{t}</h1>\n{sub}"
        f"{body}\n</main>\n<script>{JS}</script>\n</body>\n</html>\n"
    )


def _attach_pool(batches: pd.DataFrame, pool: pd.DataFrame | None) -> pd.DataFrame:
    """Join the record fields the pages show (photo, observed date, ID count) onto batches."""
    if pool is None:
        return batches.assign(photo_url=None, observed_on=None, ident_count=pd.NA)
    cols = [c for c in ("id", "photo_url", "observed_on", "ident_count") if c in pool.columns]
    joined = batches.merge(pool[cols], on="id", how="left")
    for c in ("photo_url", "observed_on", "ident_count"):
        if c not in joined.columns:
            joined[c] = None
    return joined


def _signal_facts(sig: Mapping[str, object] | None) -> list[str]:
    """Identifier-facing words for the per-batch signals; arm names never appear here."""
    if not sig:
        return []
    facts = []
    if sig.get("cohesion") is not None:
        facts.append(f"look-alike {float(sig['cohesion']):.2f}")
    if sig.get("novelty") is not None:
        facts.append(f"unfamiliar {float(sig['novelty']):.2f}")
    return facts


def _batch_card(
    label: str, seq: int, sub: pd.DataFrame, url: str, sig: Mapping[str, object] | None = None
) -> str:
    code = f"{escape(label)}-{seq:03d}"
    n = len(sub)
    fresh = sub["ident_count"]
    fresh_n = int((fresh.fillna(-1).astype(int) == 0).sum()) if fresh.notna().any() else None
    dates = sub["observed_on"].dropna().astype(str)
    when = f"{dates.min()} to {dates.max()}" if len(dates) else ""
    thumbs = "".join(
        f'<img src="{escape(str(u), quote=True)}" alt="" loading="lazy" width="72" height="72">'
        for u in sub.sort_values("position")["photo_url"].dropna().head(THUMBS_PER_BATCH)
    )
    facts = [f"{n} records"]
    if fresh_n is not None:
        facts.append(f"{fresh_n} with no ID yet")
    if when:
        facts.append(f"seen {when}")
    facts.extend(_signal_facts(sig))
    return (
        f'<li class="batch" id="{code}">'
        f'<label class="done"><input type="checkbox" data-batch="{code}"> done</label>'
        f'<span class="code">{code}</span>'
        f'<span class="facts">{escape(", ".join(facts))}</span>'
        f'<span class="thumbs">{thumbs}</span>'
        f'<a class="btn" href="{escape(url, quote=True)}" target="_blank" rel="noopener">'
        f"Open in Identify</a></li>"
    )


def render_arm_page(
    label: str,
    batches_for_arm: pd.DataFrame,
    urls: Mapping[str, str],
    *,
    title: str,
    pool: pd.DataFrame | None = None,
    freeze: str = "",
    signals: Mapping[str, Mapping[str, object]] | None = None,
) -> str:
    """One page per blind label: batches grouped by taxon, each with a link into Identify."""
    required = {"batch_id", "group", "id", "position"}
    if not required <= set(batches_for_arm.columns):
        raise ValueError(f"batches frame needs columns {sorted(required)}")
    signals = signals or {}
    df = _attach_pool(batches_for_arm, pool)
    order = list(dict.fromkeys(df["batch_id"]))
    missing = [b for b in order if b not in urls]
    if missing:
        raise ValueError(f"no url for batch {missing[0]!r}")
    seq = {bid: i + 1 for i, bid in enumerate(order)}
    sections = []
    for group, gdf in df.groupby("group", sort=True):
        cards = "\n".join(
            _batch_card(label, seq[bid], sub, urls[bid], signals.get(bid))
            for bid, sub in gdf.groupby("batch_id", sort=False)
            if bid in seq
        )
        nb = gdf["batch_id"].nunique()
        sections.append(
            f'<section id="{escape(str(group), quote=True)}">'
            f"<h2>{escape(group_name(str(group)))} "
            f'<small>{nb} batches, {len(gdf)} records</small></h2>\n<ul class="batches">\n'
            f"{cards}\n</ul></section>"
        )
    nav = " ".join(
        f'<a href="#{escape(str(g), quote=True)}">{escape(GROUP_NAMES.get(str(g), str(g)))}</a>'
        for g in sorted(df["group"].unique())
    )
    body = (
        f'<p class="crumbs"><a href="index.html">All sets</a> / Set {escape(label)}</p>\n'
        f'<p class="lede">{len(order)} batches, {len(df)} records. Pick a group you know, open '
        "a batch, ID what you can, tick it done. Ticks live in this browser only, so note the "
        "batch code too.</p>\n"
        + _signal_legend(signals, order)
        + f'<p class="groupnav">Jump to: {nav}</p>\n'
        + "\n".join(sections)
    )
    return _doc(title, body, subtitle=_freeze_note(freeze))


def _signal_legend(signals: Mapping[str, Mapping[str, object]], order: list[str]) -> str:
    """One sentence explaining the per-batch numbers, only when a shown batch has one."""
    shown = [signals[b] for b in order if b in signals]
    has_c = any(s.get("cohesion") is not None for s in shown)
    has_n = any(s.get("novelty") is not None for s in shown)
    if not (has_c or has_n):
        return ""
    parts = []
    if has_c:
        parts.append(
            "<b>Look-alike</b> is how much the photos in a batch resemble each other to an image "
            "model, 0 to 1"
        )
    if has_n:
        parts.append(
            "<b>unfamiliar</b> is how far they sit from verified BC photos of the same group, "
            "0 to 1"
        )
    return f'<p class="legend">{"; ".join(parts)}. Neither number says how hard a batch is.</p>\n'


def _freeze_note(freeze: str) -> str:
    return f"Records that needed an ID in British Columbia on {escape(freeze)}." if freeze else ""


def render_index(
    manifest: Manifest,
    batches_df: pd.DataFrame,
    *,
    title: str,
) -> str:
    """Landing page: what the blitz is, how to work a batch, one card per set, group table."""
    labels = {manifest.arm_labels[a]: f"arm_{manifest.arm_labels[a]}.html" for a in manifest.arms}
    per_label = batches_df.assign(label=batches_df["arm"].map(manifest.arm_labels))
    cards = []
    for lab in sorted(labels):
        sub = per_label[per_label["label"] == lab]
        cards.append(
            f'<a class="card" href="{escape(labels[lab], quote=True)}"><b>Set {escape(lab)}</b>'
            f"<span>{sub['batch_id'].nunique()} batches</span><span>{len(sub)} records</span>"
            f"<span>{sub['group'].nunique()} groups</span></a>"
        )
    groups = sorted(per_label["group"].astype(str).unique())
    head = "".join(f"<th>Set {escape(lab)}</th>" for lab in sorted(labels))
    rows = []
    for g in groups:
        cells = []
        for lab in sorted(labels):
            sub = per_label[(per_label["label"] == lab) & (per_label["group"].astype(str) == g)]
            nb = sub["batch_id"].nunique()
            link = f'<a href="{escape(labels[lab], quote=True)}#{escape(g, quote=True)}">'
            cells.append(f"<td>{link}{nb} batches</a></td>" if nb else "<td>none</td>")
        rows.append(f"<tr><th>{escape(group_name(g))}</th>{''.join(cells)}</tr>")
    n_groups = len(groups)
    set_list = ", ".join(sorted(labels)[:-1]) + f" or {sorted(labels)[-1]}"
    n_sets = {2: "two", 3: "three", 4: "four"}.get(len(labels), str(len(labels)))
    body = (
        '<section class="how"><h2>How it works</h2><ol>'
        f"<li><b>Take your set</b>, {escape(set_list)}. This page picks one for you at random "
        "and remembers it in this browser. Stay with it.</li>"
        "<li><b>Pick a group you know.</b> Every set has every group.</li>"
        f"<li><b>Open a batch.</b> Up to {int(manifest.batch_size)} records in one Identify "
        "page. Identify hides records that reached Research Grade since the list was built, so "
        "a batch can run short.</li>"
        "<li><b>ID what you can, skip the rest.</b> Add an ID, agree, or mark reviewed, as "
        "always.</li>"
        "<li><b>Tick it done</b> and note the code, e.g. A-016.</li>"
        "</ol></section>\n"
        '<p class="yourset" hidden>Your set is <a class="btn" data-yourset href="#"></a> '
        '<a class="swap" href="#" data-swap>pick another</a></p>\n'
        f'<div class="cards">{"".join(cards)}</div>\n'
        f'<section class="why"><h2>Why {n_sets} sets</h2>'
        f"<p>All sets draw from the same {int(manifest.pool_rows)} records in {n_groups} groups "
        "and differ only in which records share a batch. After the blitz we count which set "
        "reached Research Grade more. The rule behind each set stays hidden until then. Your IDs "
        "land on iNaturalist as usual, in your name.</p></section>\n"
        '<section class="groups"><h2>Batches per group</h2><table>'
        f"<thead><tr><th>Group</th>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"
        "</section>\n"
        f'<p class="prov">List frozen {escape(manifest.freeze)}, observations from '
        f"{escape(manifest.d1)} on, built {escape(manifest.created_at[:10])}, "
        f"pool {escape(manifest.pool_sha256[:8])}, seed {int(manifest.seed)}.</p>"
    )
    return _doc(title, body, subtitle=_freeze_note(manifest.freeze))


def write_site(
    out_dir: Path | str,
    manifest: Manifest,
    batches_df: pd.DataFrame,
    pool: pd.DataFrame | None = None,
) -> list[Path]:
    """Write index.html and arm_<label>.html; the arm name never appears in the HTML."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    urls = {bid: b["url"] for bid, b in manifest.batches.items()}
    signals = {
        bid: {k: b.get(k) for k in ("cohesion", "novelty")} for bid, b in manifest.batches.items()
    }
    title = "What to ID next in BC"
    written: list[Path] = []
    for arm, label in manifest.arm_labels.items():
        sub = batches_df[batches_df["arm"] == arm]
        path = out / f"arm_{label}.html"
        html = render_arm_page(
            label,
            sub,
            urls,
            title=f"{title}, set {label}",
            pool=pool,
            freeze=manifest.freeze,
            signals=signals,
        )
        _assert_blind(html, path)
        path.write_text(html)
        written.append(path)
    index = out / "index.html"
    html = render_index(manifest, batches_df, title=title)
    _assert_blind(html, index)
    index.write_text(html)
    written.append(index)
    return written


def _assert_blind(html: str, path: Path) -> None:
    low = html.lower()
    for w in ARM_WORDS:
        if w in low:
            raise ValueError(f"{path.name}: arm name {w!r} leaked into the page")
