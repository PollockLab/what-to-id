import json

import pytest

from what_to_id.manifest import (
    LABELFIRST_COMMIT,
    Manifest,
    blind_labels,
    blind_labels_keyed,
    key_fingerprint,
    key_from_env,
    read_manifest,
    sha256_file,
    validate_manifest,
    write_manifest,
)

KEY = bytes.fromhex("00112233445566778899aabbccddeeff00112233445566778899aabbccddee")
KEY2 = bytes.fromhex("ff112233445566778899aabbccddeeff00112233445566778899aabbccddee")


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


def test_design_defaults_to_sets_and_old_manifests_still_validate():
    m = _manifest()
    assert m.design == "sets"
    d = m.to_dict()
    validate_manifest(d)
    d.pop("design")  # an old manifest written before "design" existed
    validate_manifest(d)


def test_design_must_be_sets_or_rotation():
    d = _manifest().to_dict()
    d["design"] = "bogus"
    with pytest.raises(ValueError, match="design"):
        validate_manifest(d)


def test_write_rejects_invalid(tmp_path):
    m = _manifest()
    m.batches["recency-Aves-001"] = {"arm": "recency", "group": "Aves", "url": "u", "ids": [1]}
    with pytest.raises(ValueError):
        write_manifest(m, tmp_path / "m.json")


def test_assignment_and_key_fingerprint_defaults():
    m = _manifest()
    assert m.assignment == "stratified"
    assert m.key_fingerprint is None
    d = m.to_dict()
    validate_manifest(d)
    d.pop("assignment")
    d.pop("key_fingerprint")
    validate_manifest(d)  # old manifests written before these keys existed still validate


def test_assignment_must_be_stratified_or_keyed():
    d = _manifest().to_dict()
    d["assignment"] = "bogus"
    with pytest.raises(ValueError, match="assignment"):
        validate_manifest(d)


def test_blind_labels_keyed_deterministic_and_pool_independent():
    lab = blind_labels_keyed(["recency", "gap_first", "similarity"], KEY)
    assert set(lab.values()) == {"A", "B", "C"}
    assert lab == blind_labels_keyed(["recency", "gap_first", "similarity"], KEY)


def test_blind_labels_keyed_depends_on_key():
    lab = blind_labels_keyed(["recency", "gap_first", "similarity"], KEY)
    lab2 = blind_labels_keyed(["recency", "gap_first", "similarity"], KEY2)
    assert lab != lab2


def test_key_from_env_missing(monkeypatch):
    monkeypatch.delenv("WHAT_TO_ID_KEY", raising=False)
    with pytest.raises(ValueError, match="not set"):
        key_from_env()


def test_key_from_env_too_short(monkeypatch):
    monkeypatch.setenv("WHAT_TO_ID_KEY", "abcd")
    with pytest.raises(ValueError, match="32 hex"):
        key_from_env()


def test_key_from_env_non_hex(monkeypatch):
    short_secret = "zz" * 16
    monkeypatch.setenv("WHAT_TO_ID_KEY", short_secret)
    with pytest.raises(ValueError) as exc_info:
        key_from_env()
    assert short_secret not in str(exc_info.value)


def test_key_from_env_error_never_leaks_value(monkeypatch):
    secret = "ab" * 16
    monkeypatch.setenv("WHAT_TO_ID_KEY", "nothex" + secret)
    with pytest.raises(ValueError) as exc_info:
        key_from_env()
    assert secret not in str(exc_info.value)


def test_key_from_env_reads_hex(monkeypatch):
    monkeypatch.setenv("WHAT_TO_ID_KEY", "  " + KEY.hex() + "  ")
    assert key_from_env() == KEY


def test_key_fingerprint_does_not_contain_key_hex():
    fp = key_fingerprint(KEY)
    assert len(fp) == 12
    assert KEY.hex() not in fp
    assert fp not in KEY.hex()
    assert fp == key_fingerprint(KEY)
    assert fp != key_fingerprint(KEY2)
