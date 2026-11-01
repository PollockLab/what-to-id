"""Blind page exports to the answers frame that ``blind_skill.fit`` reads.

    python -m what_to_id.blind_answers --records records.json --names names.json \\
        --out answers.parquet blind-answers-*.jsonl

Each export row is ``{record_id, login, taxon, confidence, seconds, saved_at}``; ``taxon`` is the
typed name, empty for an abstention. The frame keeps those fields and adds ``group`` from
``records.json`` and ``taxon_id`` (-1 for an abstention). Names resolve through ``names.json``
(a JSON object, name to iNaturalist taxon id); names missing from it are looked up on the taxa
autocomplete endpoint by exact scientific or common name and written back. A name with no exact
match fails the command and is listed, so a typo is fixed by hand in ``names.json``, never guessed.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from what_to_id.inat import make_session

TAXA = "https://api.inaturalist.org/v1/taxa/autocomplete"
ABSTAIN = -1
COLUMNS = ["login", "group", "record_id", "taxon_id", "taxon", "confidence", "seconds", "saved_at"]


def read_exports(paths: list[Path]) -> pd.DataFrame:
    """Concatenate JSONL exports; a login's later answer to the same record replaces the earlier."""
    frames = [pd.read_json(p, lines=True) for p in paths if p.stat().st_size]
    if not frames:
        return pd.DataFrame(columns=COLUMNS[2:3] + COLUMNS[:1] + COLUMNS[4:])
    df = pd.concat(frames, ignore_index=True)
    df["taxon"] = df["taxon"].fillna("").astype(str).str.strip()
    return df.drop_duplicates(["login", "record_id"], keep="last").reset_index(drop=True)


def inat_lookup(name: str, session=None) -> int | None:
    """The taxon id whose scientific or preferred common name equals ``name``, else None."""
    session = session or make_session()
    r = session.get(TAXA, params={"q": name, "per_page": 10}, timeout=60)
    r.raise_for_status()
    low = name.lower()
    for t in r.json().get("results", []):
        if low in (str(t.get("name", "")).lower(), str(t.get("preferred_common_name", "")).lower()):
            return int(t["id"])
    return None


def resolve(
    names: list[str], known: dict[str, int], lookup: Callable[[str], int | None] = inat_lookup
) -> tuple[dict[str, int], list[str]]:
    """``known`` extended with ``lookup`` for new names, and the names that stayed unresolved."""
    out, missing = dict(known), []
    for n in sorted({n for n in names if n}):
        if n not in out:
            tid = lookup(n)
            if tid is None:
                missing.append(n)
            else:
                out[n] = tid
    return out, missing


def answers_frame(
    exports: pd.DataFrame, records: list[dict], names: dict[str, int]
) -> pd.DataFrame:
    """The frame ``blind_skill.fit`` reads: group joined from the records, names mapped to ids."""
    group = {int(r["id"]): r["group"] for r in records}
    df = exports.copy()
    df["group"] = df["record_id"].map(group)
    if df["group"].isna().any():
        bad = sorted(df.loc[df["group"].isna(), "record_id"].unique().tolist())
        raise ValueError(f"answers for records not in records.json: {bad}")
    df["taxon_id"] = df["taxon"].map(names).fillna(ABSTAIN).astype(int)
    return df[COLUMNS].reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m what_to_id.blind_answers", description=__doc__)
    p.add_argument("exports", nargs="+", type=Path, help="blind-answers-<login>.jsonl files")
    p.add_argument("--records", type=Path, required=True, help="the page's records.json")
    p.add_argument("--names", type=Path, required=True, help="name to taxon id JSON, updated")
    p.add_argument("--out", type=Path, required=True, help="answers parquet for blind_skill.fit")
    a = p.parse_args(argv)
    exports = read_exports(a.exports)
    known = json.loads(a.names.read_text()) if a.names.exists() else {}
    names, missing = resolve(exports["taxon"].tolist(), known)
    a.names.write_text(json.dumps(names, indent=1, sort_keys=True) + "\n")
    if missing:
        print(
            "blind_answers: no exact match, add to names.json:",
            *missing,
            sep="\n  ",
            file=sys.stderr,
        )
        return 1
    df = answers_frame(exports, json.loads(a.records.read_text()), names)
    df.to_parquet(a.out, index=False)
    print(f"blind_answers: {len(df)} answers from {df['login'].nunique()} logins -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
