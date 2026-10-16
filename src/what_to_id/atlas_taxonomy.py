"""Validate an offline taxon cache and expose explicit partial observation lineages."""

from __future__ import annotations

import hashlib
import json
from numbers import Integral
from pathlib import Path
from urllib.parse import urlsplit

from what_to_id.taxonomy import PRESETS

_MAX_SAFE_INTEGER = 2**53 - 1


def _taxon_id(value: object, *, context: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, Integral)
        or not 0 < value <= _MAX_SAFE_INTEGER
    ):
        raise ValueError(f"{context} must be a positive integer taxon ID")
    return int(value)


def _unique_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate taxonomy key: {key}")
        result[key] = value
    return result


def membership(record: dict, taxon_ids: list[int], *, exclude: bool = False) -> bool | None:
    """Known ancestry is positive; an absent root is negative only for a complete path."""
    if not isinstance(exclude, bool):
        raise ValueError("taxon scope exclude must be a boolean")
    if set(record["ancestor_taxon_ids"]).intersection(taxon_ids):
        return not exclude
    return exclude if record["taxonomy_complete"] else None


class AtlasTaxonomy:
    """One validated cache snapshot, without modifying or fetching the map's taxonomy."""

    def __init__(self, path: Path, *, source_url: str | None = None):
        if source_url is not None:
            url = urlsplit(source_url)
            if (
                url.scheme != "https"
                or not url.hostname
                or url.username is not None
                or url.password is not None
                or url.fragment
                or any(character.isspace() for character in source_url)
            ):
                raise ValueError(
                    "taxonomy source must be an absolute HTTPS URL without credentials"
                )
        contents = Path(path).read_bytes()
        raw = json.loads(contents, object_pairs_hook=_unique_object)
        if not isinstance(raw, dict) or not isinstance(raw.get("taxa"), dict):
            raise ValueError("taxonomy cache requires a taxa object")
        tree = {}
        for key, row in raw["taxa"].items():
            if not key.isascii() or not key.isdecimal() or str(int(key)) != key:
                raise ValueError(f"invalid taxonomy ID: {key!r}")
            taxon_id = _taxon_id(int(key), context="taxonomy ID")
            if not isinstance(row, list) or len(row) != 4:
                raise ValueError(f"taxon {taxon_id}: expected [parent, latin, common, rank]")
            parent = row[0]
            if parent is not None:
                parent = _taxon_id(parent, context=f"taxon {taxon_id} parent")
            tree[taxon_id] = parent
        # Iterative traversal also catches cycles outside the candidate cohort and
        # handles arbitrarily deep valid paths without Python recursion limits.
        finished = set()
        for start in tree:
            path_ids = set()
            cursor = start
            while cursor in tree and cursor not in finished:
                if cursor in path_ids:
                    raise ValueError(f"taxonomy cycle includes taxon {cursor}")
                path_ids.add(cursor)
                cursor = tree[cursor]
            finished.update(path_ids)
        self._parents = tree
        self._lineages: dict[int, tuple[tuple[int, ...], bool]] = {}
        self.source_url = source_url
        self.cache_sha256 = hashlib.sha256(contents).hexdigest()

    def lineage(self, taxon_id: int | None) -> dict:
        """Include self and known parent links, retaining missing ancestry explicitly."""
        if taxon_id is None:
            return {"taxon_id": None, "ancestor_taxon_ids": [], "taxonomy_complete": False}
        taxon_id = _taxon_id(taxon_id, context="observation taxon_id")
        if taxon_id not in self._lineages:
            ancestors = [taxon_id]
            cursor = taxon_id
            complete = False
            while cursor in self._parents:
                parent = self._parents[cursor]
                if parent is None:
                    complete = True
                    break
                ancestors.append(parent)
                cursor = parent
            self._lineages[taxon_id] = tuple(ancestors), complete
        ancestors, complete = self._lineages[taxon_id]
        return {
            "taxon_id": taxon_id,
            "ancestor_taxon_ids": list(ancestors),
            "taxonomy_complete": complete,
        }

    def metadata(self, records: list[dict], *, group: str | None = None) -> dict:
        """Describe the exact cache and observed completeness, never ecological coverage."""
        complete = sum(record["taxonomy_complete"] for record in records)
        presets = []
        definitions = [(label, roots, description, False) for label, roots, description in PRESETS]
        if group == "Fungi":
            roots = next(roots for label, roots, _ in PRESETS if label == "Lichens")
            definitions.append(
                (
                    "Outside listed lichen-forming groups",
                    roots,
                    "An approximate exclusion of the listed lichen-forming groups, "
                    "using complete cached ancestry only",
                    True,
                )
            )
        for label, roots, description, exclude in definitions:
            states = [membership(record, roots, exclude=exclude) for record in records]
            presets.append(
                {
                    "label": label,
                    "taxon_ids": list(roots),
                    "description": description,
                    "approximate": exclude or label == "Lichens",
                    "exclude": exclude,
                    "match_count": sum(state is True for state in states),
                    "nonmatch_count": sum(state is False for state in states),
                    "unknown_count": sum(state is None for state in states),
                }
            )
        return {
            "source_url": self.source_url,
            "cache_sha256": self.cache_sha256,
            "complete_count": complete,
            "incomplete_count": len(records) - complete,
            "lineage_includes_self": True,
            "completeness": "every parent link reaches an explicit root in this cache",
            "membership": "known root matches; absent root is negative only with complete ancestry",
            "presets": presets,
        }
