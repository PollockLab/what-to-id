"""The map's data files under content-hashed names, listed in map.html's META.

Each file is named ``<stem>.<sha256[:12]>.bin`` by its own bytes, so a rebuild changes the URL of
only the files whose bytes changed and a returning visitor downloads only those. page_map names the
shards, taxa and observer files in META; the steps after it (levels, look-alikes, left needs-ID) add
theirs under META.files with `publish`, and every page reads the names from META.

Every Pages deploy uploads a whole new site, so ``keep`` copies the live site's data files (the ones
its map.html META names) into the new build before upload: a page cached from the last deploy still
finds its files, and anything older drops out.

    python -m what_to_id.site_files keep --site _site --url https://example.github.io/what-to-id/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path

import requests

MAP_NAME = "map.html"
START, END = "var META=", ";var BASEMAPS="
SAFE = re.compile(r"[\w-]+(\.[\w-]+)*")  # a plain file name, no path


def hashed(name: str, blob: bytes) -> str:
    stem, ext = name.rsplit(".", 1)
    return f"{stem}.{hashlib.sha256(blob).hexdigest()[:12]}.{ext}"


def dump(meta: dict) -> str:
    """META as render_map writes it inline."""
    return json.dumps(meta, sort_keys=True, separators=(",", ":")).replace("</", "<\\/")


def read_meta(html: str) -> dict:
    start, end = html.find(START), html.find(END)
    if start < 0 or end < start:
        raise ValueError("the map page holds no META: was it written by what_to_id.page_map?")
    return json.loads(html[start + len(START) : end])


def publish(site: Path, key: str, name: str, blob: bytes | None) -> Path | None:
    """Write ``blob`` as ``name`` hashed and list it as META.files[key]; None drops the entry."""
    page = Path(site) / MAP_NAME
    html = page.read_text()
    meta = read_meta(html)
    files = meta.setdefault("files", {})
    files.pop(key, None)
    if blob is not None:
        files[key] = hashed(name, blob)
        (page.parent / files[key]).write_bytes(blob)
    start, end = html.find(START) + len(START), html.find(END)
    page.write_text(html[:start] + dump(meta) + html[end:])
    return page.parent / files[key] if key in files else None


def path(site: Path, key: str) -> Path | None:
    """The file META.files[key] names in ``site``, or None."""
    name = read_meta((Path(site) / MAP_NAME).read_text()).get("files", {}).get(key)
    return Path(site) / name if name else None


def data_files(meta: dict) -> list[str]:
    """Every data file a META names, without a ``?v=`` (a page built before the hashed names)."""
    names = [s["file"] for s in meta["shards"]] + [meta["taxa"], meta.get("observer")]
    names += list(meta.get("files", {}).values())
    return [n.split("?")[0] for n in names if n]


def _get(url: str) -> bytes:
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.content


def keep(site: Path, url: str, get: Callable[[str], bytes] = _get) -> list[str]:
    """Copy the data files of the map page live at ``url`` into ``site``; the names it copied."""
    base = url.rstrip("/") + "/"
    kept = []
    for name in data_files(read_meta(get(base + MAP_NAME).decode())):
        if not SAFE.fullmatch(name):
            raise ValueError(f"the live map names {name!r}, not a plain file name")
        if not (Path(site) / name).exists():
            (Path(site) / name).write_bytes(get(base + name))
            kept.append(name)
    return kept


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m what_to_id.site_files", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    k = sub.add_parser("keep", help="copy the live site's data files into a new build")
    k.add_argument("--site", type=Path, required=True, help="the new site directory")
    k.add_argument("--url", required=True, help="base URL of the live site")
    a = p.parse_args(argv)
    try:
        kept = keep(a.site, a.url)
    except (ValueError, KeyError, requests.RequestException) as exc:
        print(f"site_files: {exc}", file=sys.stderr)
        return 1
    print(f"site_files: kept {len(kept)} files of the live site: {' '.join(kept)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
