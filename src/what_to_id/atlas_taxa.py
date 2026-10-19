"""Precomputed text vectors for taxon-name queries, so the page answers them without the text model.

    python -m what_to_id.atlas_taxa build --pool pool.parquet --index DIR [--snapshot DIR]

Embeds ``a photo of <scientific name>`` for every distinct scientific name in the pool with the
torch fp32 text tower and writes two versioned files into the index directory:
``taxa-<sha12>.tsv.gz`` (one ``scientific<TAB>common`` line per row) and ``taxa-<sha12>.f16``
(rows x dims float16, same row order, so a browser can HTTP-Range one 2 KB vector). The manifest
gains an optional ``taxa`` entry; the layout version stays 1. Common names share the row of their
scientific name (a second row would double the file for a text the model knows less well); a
common name used by several scientific names is ambiguous and is left to the text model.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import logging
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np

from .atlas_index_io import read_manifest, write_array, write_manifest

log = logging.getLogger("what_to_id")

PROMPT = "a photo of {}"
DEFAULT_SNAPSHOT = Path.home() / ".cache" / "what-to-id" / "bioclip-2.5"
BATCH = 64
Embed = Callable[[list[str]], np.ndarray]


def taxa_table(pool: str | Path) -> list[tuple[str, str]]:
    """Distinct (scientific, common) pairs from the pool, sorted by lower-cased scientific name."""
    import pandas as pd

    df = pd.read_parquet(pool, columns=["taxon_name", "common_name"])
    df = df.dropna(subset=["taxon_name"])
    df["taxon_name"] = df["taxon_name"].str.split().str.join(" ")
    df = df[df["taxon_name"] != ""]
    df["common_name"] = df["common_name"].fillna("").str.split().str.join(" ")
    # one row per lower-cased scientific name, keeping its first non-empty common name
    df = df.assign(_key=df["taxon_name"].str.lower(), _empty=df["common_name"] == "")
    df = df.sort_values(["_key", "_empty", "common_name"]).drop_duplicates("_key")
    return list(zip(df["taxon_name"], df["common_name"], strict=True))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def _names_blob(table: list[tuple[str, str]]) -> bytes:
    text = "".join(f"{sci}\t{common}\n" for sci, common in table)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:  # mtime 0: same table, same bytes
        gz.write(text.encode())
    return buf.getvalue()


def torch_embed(snapshot: Path) -> Embed:
    """Unit-norm fp32 text embeddings from the pinned snapshot, on MPS when available else CPU."""
    import torch

    from .atlas_text_encoder import load_model, text_tower

    model, tokenizer = load_model(snapshot)
    tower = text_tower(model)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    tower.to(device)

    def embed(prompts: list[str]) -> np.ndarray:
        out = []
        with torch.inference_mode():
            for lo in range(0, len(prompts), BATCH):
                tokens = tokenizer(prompts[lo : lo + BATCH]).to(device)
                out.append(tower(tokens).float().cpu().numpy())
        return np.vstack(out)

    return embed


def build(pool: str | Path, index: str | Path, embed: Embed) -> dict:
    """Write the taxa files into ``index`` and register them in its manifest; return the entry."""
    manifest = read_manifest(index)
    table = taxa_table(pool)
    if not table:
        raise ValueError(f"{pool} has no taxon_name values")
    prompts = [PROMPT.format(sci) for sci, _ in table]
    t0 = time.time()
    vectors = np.asarray(embed(prompts), dtype=np.float32)
    dims = manifest["dims"]
    if vectors.shape != (len(table), dims):
        raise ValueError(f"embedder gave {vectors.shape}, expected {(len(table), dims)}")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if not np.all(norms > 0) or not np.all(np.isfinite(norms)):
        raise ValueError("embedder returned zero-length or non-finite rows")
    vectors /= norms
    base = Path(index)
    tmp = base / "taxa.f16.tmp"
    write_array(tmp, vectors, "<f2")
    vec_name = f"taxa-{_digest(tmp)}.f16"
    tmp.replace(base / vec_name)
    blob = _names_blob(table)
    names_name = f"taxa-{hashlib.sha256(blob).hexdigest()[:12]}.tsv.gz"
    (base / names_name).write_bytes(blob)
    entry = {
        "names": names_name,
        "vectors": vec_name,
        "count": len(table),
        "dims": dims,
        "prompt": PROMPT,
    }
    for old in (manifest.get("taxa") or {}).values():  # files the new manifest no longer names
        if isinstance(old, str) and old not in entry.values() and (base / old).is_file():
            (base / old).unlink()
    manifest["taxa"] = entry
    write_manifest(index, manifest)
    log.info("embedded %d taxa in %.0fs", len(table), time.time() - t0)
    return entry


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m what_to_id.atlas_taxa", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="embed every pool taxon into the index directory")
    b.add_argument("--pool", type=Path, required=True, help="pool parquet with taxon_name")
    b.add_argument("--index", type=Path, required=True, help="index directory with manifest.json")
    b.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT, help="BioCLIP 2.5 snapshot")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    entry = build(args.pool, args.index, torch_embed(args.snapshot))
    print(entry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
