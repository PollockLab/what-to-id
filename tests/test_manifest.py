import json

import pytest

from what_to_id.manifest import (
    LABELFIRST_COMMIT,
    Manifest,
    blind_labels,
    read_manifest,
    sha256_file,
    validate_manifest,
    write_manifest,
)


def _manifest():
    return Manifest(
        freeze="2026-09-01",
        d1="2026-09-15",
        seed=0,
        batch_size=2,
        arms=["recency", "gap_first"],
        arm_labels=blind_labels(["recency", "gap_first"], 0),
        pool_sha256="0" * 64,
        pool_rows=4,
        batches={
            "recency-Aves-000": {
                "arm": "recency",
                "group": "Aves",
                "url": "https://x",
                "ids": [1, 2],
            },
            "gap_first-Aves-000": {
                "arm": "gap_first",
                "group": "Aves",
                "url": "https://y",
                "ids": [3, 4],
            },
        },
    )


def test_blind_labels():
    lab = blind_labels(["recency", "gap_first", "similarity"], 0)
    assert set(lab.values()) == {"A", "B", "C"}
    assert lab == blind_labels(["recency", "gap_first", "similarity"], 0)
    assert any(blind_labels(["recency", "gap_first", "similarity"], s) != lab for s in range(1, 20))


def test_round_trip(tmp_path):
    m = _manifest()
    p = tmp_path / "manifest.json"
    write_manifest(m, p)
    back = read_manifest(p)
    assert back == m
    assert back.labelfirst_commit == LABELFIRST_COMMIT
    assert back.where_to_blitz_ref == "grid-outputs-v1@3bdcc68"
    assert json.loads(p.read_text())["created_at"].endswith("+00:00")


def test_sha256_file(tmp_path):
    p = tmp_path / "f"
    p.write_bytes(b"abc")
    assert sha256_file(p) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


@pytest.mark.parametrize(
    "mutate, key",
    [
        (lambda d: d.pop("seed"), "seed"),
        (lambda d: d.update(seed="0"), "seed"),
        (lambda d: d.update(arms=[]), "arms"),
        (lambda d: d["arm_labels"].pop("recency"), "arm_labels"),
        (lambda d: d["arm_labels"].update(recency="B", gap_first="B"), "arm_labels"),
        (lambda d: d["batches"]["recency-Aves-000"].pop("url"), "url"),
        (lambda d: d["batches"]["recency-Aves-000"].update(ids=[1, "2"]), "ints"),
        (lambda d: d["batches"]["recency-Aves-000"].update(ids=[1, 3]), "more than one batch"),
        (lambda d: d["batches"]["recency-Aves-000"].update(arm="bogus"), "bogus"),
    ],
)
def test_validation_errors(mutate, key):
    d = _manifest().to_dict()
    mutate(d)
    with pytest.raises(ValueError, match=key):
        validate_manifest(d)


def test_write_rejects_invalid(tmp_path):
    m = _manifest()
    m.batches["recency-Aves-001"] = {"arm": "recency", "group": "Aves", "url": "u", "ids": [1]}
    with pytest.raises(ValueError):
        write_manifest(m, tmp_path / "m.json")
