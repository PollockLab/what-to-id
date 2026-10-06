"""The taxon tree behind the map's clade filters, and the taxa table the map page reads.

The tree is a JSON cache, {"taxa": {id: [parent id or null, latin, common, rank]}}, holding every
taxon the pool's records carry and all their ancestors. ``update_tree`` asks iNaturalist only for
taxa the cache lacks, PER_REQUEST at a time, and then for their ancestors it has not seen, so the
first fill of a 35,000-taxon pool takes a few hundred requests and a daily run a handful. A taxon
iNaturalist has since swapped keeps its place: ``is_active=any`` returns inactive taxa too.

The taxa table (pool-taxa.bin) is one row per taxon a record carries, most records first:
[latin, common, iNaturalist taxon id, rank]. With a tree, each row gains a fifth element, the
row of its parent (-1 for none), and rows for ancestors no record carries follow the record rows,
by id. A record then matches a taxon when that taxon is its own or any ancestor, so a search for
Bryophyta keeps every moss.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from collections.abc import Iterable
from pathlib import Path

import numpy as np
import pandas as pd

from what_to_id.inat import INAT, SLEEP, TIMEOUT, make_session

TAXA_API = INAT.rsplit("/", 1)[0] + "/taxa"
PER_REQUEST = 200
NO_TAXON = 0xFFFF
NO_RANK = 0xFF
# Shortcuts the map offers beside the taxon search, each a set of taxa picked at once:
# [label, iNaturalist taxon ids, tooltip]. They show only when the tree is complete.
# Lichens are no clade on iNaturalist, so that shortcut is approximate: the lichen-forming classes
# and order iNaturalist staff exclude to leave lichens out of Identify ("Excluding Taxa from
# Identify", https://www.inaturalist.org/posts/7210: Lecanoromycetes 54743, Verrucariales 117869,
# Lichinomycetes 152030, Arthoniomycetes 152028), plus the basidiolichen genera Lichenomphalia
# 118252 and Multiclavula 175541 named on the forum
# (https://forum.inaturalist.org/t/separate-lichen-and-fungi-into-two-categories/5212/10). It
# misses smaller lichen lineages and holds a few non-lichenized Lecanoromycetes.
PRESETS = [
    ["Bryophytes", [56327, 311249, 64615], "Hornworts, mosses and liverworts"],
    [
        "Lichens",
        [54743, 117869, 152030, 152028, 118252, 175541],
        "The main lichen-forming fungi; approximate, as lichens are no single clade",
    ],
]
# The iNaturalist taxon behind each iconic group the map shows as a chip, so Identify can add the
# chosen groups to the picked taxa in one taxon_id. Animalia (animals in no other group) and
# Unknown have no single taxon.
GROUP_TAXA = {
    "Actinopterygii": 47178,
    "Amphibia": 20978,
    "Arachnida": 47119,
    "Aves": 3,
    "Chromista": 48222,
    "Fungi": 47170,
    "Insecta": 47158,
    "Mammalia": 40151,
    "Mollusca": 47115,
    "Plantae": 47126,
    "Protozoa": 47686,
    "Reptilia": 26036,
}

log = logging.getLogger("what_to_id")


def load_tree(path: Path | str | None) -> dict[int, list]:
    """The cached tree, keyed by taxon id; empty when there is no cache yet."""
    if path is None or not Path(path).exists():
        return {}
    raw = json.loads(Path(path).read_text())
    return {int(k): v for k, v in raw["taxa"].items()}


def save_tree(tree: dict[int, list], path: Path | str) -> None:
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    body = {"taxa": {str(k): tree[k] for k in sorted(tree)}}
    tmp.write_text(json.dumps(body, ensure_ascii=False, separators=(",", ":")))
    tmp.replace(path)


def fetch_taxa(ids: Iterable[int], *, session=None) -> dict[int, list]:
    """[parent, latin, common, rank] for each of at most PER_REQUEST ids iNaturalist knows."""
    ids = sorted({int(i) for i in ids})
    if len(ids) > PER_REQUEST:
        raise ValueError(f"at most {PER_REQUEST} ids a request, got {len(ids)}")
    session = session or make_session()
    params = {"id": ",".join(map(str, ids)), "per_page": PER_REQUEST, "is_active": "any"}
    r = session.get(TAXA_API, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    out: dict[int, list] = {}
    for t in r.json()["results"]:
        chain = [int(a) for a in t.get("ancestor_ids") or [] if int(a) != int(t["id"])]
        out[int(t["id"])] = [
            chain[-1] if chain else None,
            t.get("name") or "",
            t.get("preferred_common_name") or "",
            t.get("rank") or "",
        ]
    return out


def missing_ancestors(tree: dict[int, list]) -> set[int]:
    """Parents named in the tree that it does not hold yet."""
    return {v[0] for v in tree.values() if v[0] is not None and v[0] not in tree}


def update_tree(tree: dict[int, list], ids: Iterable[int], *, session=None, sleep=SLEEP) -> int:
    """Add the taxa in ``ids`` the tree lacks, and their ancestors. Returns how many it added.

    The tree grows request by request, so what a failed run fetched stays in it, and the next
    run asks only for the rest.
    """
    session = session or make_session()
    before = len(tree)
    need = sorted({int(i) for i in ids} - set(tree))
    asked: set[int] = set()
    while need:
        for start in range(0, len(need), PER_REQUEST):
            if sleep and asked:
                time.sleep(sleep)
            batch = need[start : start + PER_REQUEST]
            asked.update(batch)
            tree.update(fetch_taxa(batch, session=session))
        need = sorted(missing_ancestors(tree) - asked)
    return len(tree) - before


def taxa_table(df: pd.DataFrame, tree: dict[int, list] | None = None):
    """The taxa table, each record's row in it, the ranks the rows index, and whether every
    record taxon has its whole line of ancestors in the tree (False without a tree)."""
    if "taxon_id" not in df or "taxon_name" not in df:
        return [], np.full(len(df), NO_TAXON), [], False
    common = df["common_name"] if "common_name" in df else pd.Series("", index=df.index)
    rank = df["rank"] if "rank" in df else pd.Series(None, index=df.index, dtype=object)
    t = pd.DataFrame(
        {"tid": df["taxon_id"], "latin": df["taxon_name"], "common": common, "rank": rank}
    ).dropna(subset=["tid"])
    table = t.drop_duplicates("tid").set_index("tid")
    table["n"] = t["tid"].value_counts()
    table = table.reset_index().sort_values(["n", "tid"], ascending=[False, True])
    if len(table) >= NO_TAXON:
        raise ValueError(f"{len(table)} taxa do not fit in uint16")
    pos = pd.Series(np.arange(len(table)), index=table["tid"].to_numpy())
    idx = df["taxon_id"].map(pos).fillna(NO_TAXON).to_numpy()

    def text(v) -> str:
        return str(v) if pd.notna(v) else ""

    rows = [
        [text(a), text(c), int(k), text(r)]
        for a, c, k, r in zip(
            table["latin"], table["common"], table["tid"], table["rank"], strict=True
        )
    ]
    complete = False
    if tree is not None:
        rows, complete = _with_ancestors(rows, tree)
    ranks = sorted({r[3] for r in rows if r[3]})
    at = {r: i for i, r in enumerate(ranks)}
    for r in rows:
        r[3] = at.get(r[3], NO_RANK)
    return rows, idx, ranks, complete


def _with_ancestors(rows: list[list], tree: dict[int, list]) -> tuple[list[list], bool]:
    """Append ancestor rows and give every row its parent's row (-1 for none)."""
    row = {r[2]: i for i, r in enumerate(rows)}
    extra: set[int] = set()
    complete = True
    for r in rows:
        p = r[2]
        # walk up until a taxon already placed, the root, or a gap in the tree
        while p is not None:
            if p not in tree:
                complete = False
                break
            p = tree[p][0]
            if p in row or p in extra:
                break
            if p is not None and p in tree:
                extra.add(p)
    for k in sorted(extra):
        row[k] = len(rows)
        _, latin, common, rank = tree[k]
        rows.append([latin, common, k, rank])
    for r in rows:
        p = tree[r[2]][0] if r[2] in tree else None
        r.append(row.get(p, -1) if p is not None else -1)
    return rows, complete


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fill the taxon tree cache for a pool's taxa.")
    ap.add_argument("--pool", required=True, type=Path)
    ap.add_argument("--tree", required=True, type=Path, help="JSON cache, created if missing")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ids = pd.read_parquet(a.pool, columns=["taxon_id"])["taxon_id"].dropna().astype(int)
    tree = load_tree(a.tree)
    try:
        added = update_tree(tree, ids.unique())
    finally:
        save_tree(tree, a.tree)
    lacking = len(set(ids) - set(tree)) + len(missing_ancestors(tree))
    log.info("tree holds %d taxa, %d new; %d still missing", len(tree), added, lacking)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
