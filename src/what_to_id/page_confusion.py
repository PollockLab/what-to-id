"""The confused-pairs page: species pairs as the index, each pair's Needs ID records worst first.

    python -m what_to_id.page_confusion --out SITE_DIR --data-url URL [--parquet FILE]
        [--records-parquet FILE]

The atlas manifest at ``--data-url`` may carry ``"confusion"`` and ``"confusion_records"``, each
``{"name", "built_at", "count"}``, naming parquets beside it. ``confusion`` is the pairs table
(taxon_id, taxon_name, looks_like_taxon_id, looks_like_name, n_photos, n_species_photos, share);
``confusion_records`` holds one row per record with a negative text margin, at most 50 per pair
(RECORD_COLUMNS). Without ``confusion`` nothing is written; without ``confusion_records`` the page
lists the pairs only. ``--parquet`` and ``--records-parquet`` build from local files instead.

It writes confusion.html (every script inlined), confusion-taxa.json (the taxon ids with a pair,
which the tree page reads for its "Often confused with" link) and confusion-data.bin, gzipped:

    u32 LE header length H, H bytes of header JSON, zero padding to a multiple of 4, then n records
    as columns: id u32[n], photo u32[n], taxon u16[n], looks u16[n], score u8[n], meta u8[n]

The header holds ``taxa`` (index -> [taxon_id or null, name, group index or null]), ``groups``
([name, records] by records desc), ``pairs`` ([taxon, looks, n_photos, n_species_photos] by
n_photos desc), ``n``, ``score`` ([lo, hi]: score s is margin lo + s / 255 * (hi - lo)),
``hosts`` and ``exts``. Records run by taxon, worst margin first. A photo URL is
``hosts[meta // len(exts)] + photo + "/medium." + exts[meta % len(exts)]``; meta 255 has none.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import tempfile
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd

from what_to_id import page_nav
from what_to_id.confusion import RECORD_COLUMNS
from what_to_id.page_lookalike import _fetch

HERE = Path(__file__).parent
ASSETS = HERE / "confusion_assets"
PAGE_NAME = "confusion.html"
TAXA_NAME = "confusion-taxa.json"
DATA_NAME = "confusion-data.bin"
NO_PHOTO = 255
PHOTO = r"^(https?://.+/)(\d+)/medium\.([A-Za-z0-9]+)(?:\?.*)?$"
SCRIPTS = {
    "__EMBEDDINGS_LAYOUT__": HERE / "embeddings_assets" / "embeddings_layout.js",
    "__IDENTIFY_LINKS__": HERE / "map_assets" / "identify_links.js",
    "__CONFUSION_APP__": ASSETS / "confusion_app.js",
}
NO_RECORDS = "Per-record rows arrive with the next build; until then each pair links to Identify."


def _keys(ids: pd.Series, names: pd.Series) -> np.ndarray:
    """A taxon's key: its id, or its name when the look-alike is not a species in the pool."""
    ids = ids.astype("Int64")
    return np.where(ids.notna(), ids.astype(object), "n:" + names.astype(str))


def encode(pairs: pd.DataFrame, records: pd.DataFrame | None, built_at: str = "") -> bytes:
    """The gzipped confusion-data.bin for these pairs and records (see the module docstring)."""
    recs = records if records is not None else pd.DataFrame(columns=list(RECORD_COLUMNS))
    missing = [c for c in RECORD_COLUMNS if c not in recs.columns]
    if missing:
        raise ValueError(f"the records table lacks {', '.join(missing)}")
    recs = recs.sort_values(["taxon_id", "margin", "id"], kind="stable").reset_index(drop=True)
    sides = [
        (pairs["taxon_id"], pairs["taxon_name"]),
        (recs["taxon_id"], recs["taxon_name"]),
        (pairs["looks_like_taxon_id"], pairs["looks_like_name"]),
        (recs["looks_like_taxon_id"], recs["looks_like_name"]),
    ]
    named = pd.concat(
        [pd.DataFrame({"key": _keys(i, n), "id": i.astype("Int64"), "name": n}) for i, n in sides]
    ).drop_duplicates("key")
    if len(named) > 0xFFFF:
        raise ValueError(f"{len(named)} taxa do not fit the page's 16-bit taxon index")
    index = pd.Series(np.arange(len(named)), index=named["key"].to_numpy())

    def ix(ids: pd.Series, names: pd.Series) -> np.ndarray:
        return index[_keys(ids, names)].to_numpy()

    group = recs.groupby("taxon_id")["iconic_taxon"].first().dropna()
    counts = group.reindex(recs["taxon_id"]).value_counts()
    groups = [[str(g), int(c)] for g, c in counts.items()]
    gix = {g: k for k, (g, _) in enumerate(groups)}
    taxa = [
        [None, str(n), None] if pd.isna(i) else [int(i), str(n), gix.get(group.get(int(i)))]
        for i, n in zip(named["id"], named["name"], strict=True)
    ]
    pp = pairs.sort_values("n_photos", ascending=False, kind="stable")
    pair_rows = np.column_stack(
        [
            ix(pp["taxon_id"], pp["taxon_name"]),
            ix(pp["looks_like_taxon_id"], pp["looks_like_name"]),
            pp["n_photos"].to_numpy(),
            pp["n_species_photos"].to_numpy(),
        ]
    ).astype(int)
    ids = recs["id"].to_numpy(np.int64)
    if len(ids) and (ids.min() <= 0 or ids.max() > 0xFFFFFFFF):
        raise ValueError("record ids must be positive and fit 32 bits")
    margin = recs["margin"].to_numpy(float)
    lo, hi = (float(margin.min()), float(margin.max())) if len(margin) else (0.0, 0.0)
    score = np.rint((margin - lo) / (hi - lo) * 255) if hi > lo else np.zeros(len(margin))
    parts = recs["photo_url"].astype(str).str.extract(PHOTO)
    ok = parts[1].notna().to_numpy()
    hosts, exts = sorted(set(parts[0].dropna())), sorted(set(parts[2].dropna().str.lower()))
    if len(hosts) * max(len(exts), 1) > NO_PHOTO:
        raise ValueError(f"{len(hosts)} photo hosts by {len(exts)} extensions do not fit a byte")
    host_ix = parts[0].map({h: k for k, h in enumerate(hosts)}).fillna(0).to_numpy(int)
    ext_ix = parts[2].str.lower().map({e: k for k, e in enumerate(exts)}).fillna(0).to_numpy(int)
    meta = np.where(ok, host_ix * len(exts) + ext_ix, NO_PHOTO)
    photo = np.where(ok, pd.to_numeric(parts[1], errors="coerce").fillna(0), 0).astype(np.int64)
    if photo.max(initial=0) > 0xFFFFFFFF:
        raise ValueError("photo ids must fit 32 bits")
    if (~ok).any():
        print(f"page_confusion: {int((~ok).sum())} records have no medium photo URL")
    head = {
        "built_at": built_at,
        "taxa": taxa,
        "groups": groups,
        "pairs": pair_rows.tolist(),
        "n": len(recs),
        "score": [lo, hi],
        "hosts": hosts,
        "exts": exts,
    }
    header = json.dumps(head, separators=(",", ":")).encode()
    body = b"".join(
        [
            np.array([len(header)], "<u4").tobytes(),
            header,
            b"\0" * (-(4 + len(header)) % 4),
            ids.astype("<u4").tobytes(),
            photo.astype("<u4").tobytes(),
            ix(recs["taxon_id"], recs["taxon_name"]).astype("<u2").tobytes(),
            ix(recs["looks_like_taxon_id"], recs["looks_like_name"]).astype("<u2").tobytes(),
            score.astype("u1").tobytes(),
            meta.astype("u1").tobytes(),
        ]
    )
    return gzip.compress(body, 9, mtime=0)


def render(data_url: str, built_at: str = "", has_records: bool = True) -> str:
    html = (ASSETS / PAGE_NAME).read_text()
    built = f"Built {escape(built_at[:10])}." if built_at else ""
    note = "" if has_records else f'<p class="note" id="norecords">{escape(NO_RECORDS)}</p>'
    for key, value in {
        "__SITE_CSS__": page_nav.CSS,
        "__SITE_NAV__": page_nav.nav(PAGE_NAME),
        "__CONFIG__": json.dumps({"data": data_url}).replace("<", "\\u003c"),
        "__BUILT__": built,
        "__RECORDS_NOTE__": note,
    }.items():
        html = html.replace(key, value)
    for key, path in SCRIPTS.items():
        html = html.replace(key, path.read_text())
    return html


def build(
    out: Path,
    data_url: str | None,
    parquet: Path | None = None,
    records_parquet: Path | None = None,
) -> Path | None:
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        built_at = ""
        if parquet is None:
            if records_parquet is not None:
                raise ValueError("--records-parquet needs --parquet")
            if not data_url:
                raise ValueError("give --data-url or --parquet")
            base = data_url.rstrip("/") + "/"
            _fetch(base + "manifest.json", Path(tmp) / "manifest.json")
            manifest = json.loads((Path(tmp) / "manifest.json").read_text())
            entry = manifest.get("confusion")
            if not entry:
                print("page_confusion: the manifest has no confusion table; nothing written")
                return None
            parquet = Path(tmp) / "confusion.parquet"
            _fetch(base + entry["name"], parquet)
            built_at = entry.get("built_at", "")
            if rec_entry := manifest.get("confusion_records"):
                records_parquet = Path(tmp) / "confusion-records.parquet"
                _fetch(base + rec_entry["name"], records_parquet)
        df = pd.read_parquet(parquet)
        records = pd.read_parquet(records_parquet) if records_parquet else None
    blob = encode(df, records, built_at)
    (out / DATA_NAME).write_bytes(blob)
    print(f"page_confusion: {DATA_NAME} {len(blob) / 1e6:.2f} MB gzipped")
    version = hashlib.sha256(blob).hexdigest()[:12]
    target = out / PAGE_NAME
    target.write_text(render(f"{DATA_NAME}?v={version}", built_at, records is not None))
    (out / TAXA_NAME).write_text(json.dumps(sorted({int(t) for t in df["taxon_id"]})))
    return target


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m what_to_id.page_confusion", description=__doc__)
    p.add_argument("--out", type=Path, required=True, help="site directory")
    p.add_argument("--data-url", help="atlas base URL holding manifest.json")
    p.add_argument("--parquet", type=Path, help="build from this local file, skipping the manifest")
    p.add_argument("--records-parquet", type=Path, help="local per-record table, with --parquet")
    a = p.parse_args(argv)
    try:
        target = build(a.out, a.data_url, a.parquet, a.records_parquet)
    except (ValueError, OSError) as exc:
        print(f"page_confusion: {exc}", file=sys.stderr)
        return 1
    if target:
        print(f"page_confusion: wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
