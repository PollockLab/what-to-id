"""Rotation design: the blind study.json that Identify serves batches from, and terms.html explains.

Each click on "Next batch" in Identify advances a per-browser, per-group cycle through the blind
list labels in a random permutation drawn once and stored in localStorage
(identify_assets/identify_study.js). Every label gets the same share of every identifier's
effort. Each browser also starts every list and group at its own random batch and wraps around,
so identifiers working the same group spread over the served window instead of all opening the
same first batches (disjoint dealing).

study.json maps opaque list labels (the same letters as manifest.arm_labels) to per-group
ordered lists of observation ids, a list's position being the served log's ``batch_index``, so
the read-back joins public identifications to served batches with no help from the browser. It
also carries the "How the test works" fold for terms.html. No arm name or batch_id reaches it.
"""

from __future__ import annotations

import json
from pathlib import Path

from what_to_id.manifest import Manifest
from what_to_id.page import ARM_WORDS, group_name
from what_to_id.page_method import method_section

STUDY_NAME = "study.json"


def _rotation_data(manifest: Manifest) -> dict[str, dict[str, list[list[int]]]]:
    """label -> group -> batches of ids, each at its batch_index (the batch_id's number)."""
    data: dict[str, dict[str, list[list[int]]]] = {}
    for bid, b in sorted(manifest.batches.items(), key=lambda kv: int(kv[0].rsplit("-", 1)[1])):
        label = manifest.arm_labels[b["arm"]]
        batches = data.setdefault(label, {}).setdefault(str(b["group"]), [])
        if len(batches) != int(bid.rsplit("-", 1)[1]):
            raise ValueError(f"batch {bid!r} is out of sequence for its list and group")
        batches.append([int(i) for i in b["ids"]])
    return data


def study_data(manifest: Manifest) -> dict:
    """The blind study: build, day, group names, the lists, and the method fold."""
    data = _rotation_data(manifest)
    groups = sorted({g for by_group in data.values() for g in by_group})
    return {
        "build": manifest.created_at,
        "day": manifest.freeze,
        "names": {g: group_name(g) for g in groups},
        "lists": data,
        "methods": method_section(manifest, len(data)),
    }


def _blind(text: str) -> str:
    low = text.lower()
    for w in ARM_WORDS:
        if w in low:
            raise ValueError(f"{STUDY_NAME}: arm name {w!r} leaked into the study data")
    return text


def write_study(out_dir: Path | str, manifest: Manifest) -> Path:
    """Write study.json, refusing it if an arm name leaked in."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / STUDY_NAME
    path.write_text(_blind(json.dumps(study_data(manifest), sort_keys=True)))
    return path


def read_study(path: Path | str) -> dict:
    """A study.json for the pages, refused if an arm name is in it."""
    return json.loads(_blind(Path(path).read_text()))
