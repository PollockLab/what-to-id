"""GloBI interactions lifted to unordered host family pairs, and the committed pair files."""

from __future__ import annotations

import gzip
import hashlib

import pytest

from what_to_id import host_pairs

from .test_page_lookalike import _write_site

COLS = ["sourceTaxonId", "sourceTaxonFamilyName", "interactionTypeName", "targetTaxonFamilyName"]
COLS += ["referenceDoi", "sourceCitation"]


def _dump(path, rows):
    text = "\t".join(COLS) + "\n" + "".join("\t".join(["x", *r]) + "\n" for r in rows)
    path.write_bytes(gzip.compress(text.encode()))


ROWS = [
    ["Ustilaginaceae", "hasHost", "Poaceae", "10.1/a", ""],
    ["Poaceae", "hostOf", "Ustilaginaceae", "", "Some survey"],  # same pair, other way round
    ["Ustilaginaceae", "eats", "Cyperaceae", "10.1/b", ""],  # not a kept type
    ["Ustilaginaceae", "visitsFlowersOf", "Cyperaceae", "10.1/b", ""],
    ["Ustilaginaceae", "pathogenOf", "Cyperaceae", "10.1/c", ""],  # one row only
    ["Poaceae", "parasiteOf", "Poaceae", "10.1/d", ""],  # same family
    ["Poaceae", "parasiteOf", "Poaceae", "10.1/d", ""],
    ["Rosaceae", "hasHost", "Pucciniaceae", "10.1/e", ""],  # neither family is on the site
    ["Rosaceae", "hasHost", "Pucciniaceae", "10.1/e", ""],
    ["Poaceae", "hasHost", "Cyperaceae", "10.1/f", ""],  # same phylum
    ["Poaceae", "hasHost", "Cyperaceae", "10.1/f", ""],
]


@pytest.fixture
def site(tmp_path):
    _write_site(tmp_path)
    return tmp_path


def test_lift_keeps_cross_phylum_host_pairs_both_ways_above_the_threshold(site, tmp_path):
    dump = tmp_path / "interactions.tsv.gz"
    _dump(dump, ROWS)
    out = tmp_path / "pairs.tsv"
    assert host_pairs.main(["--site", str(site), "--dump", str(dump), "--out", str(out)]) == 0
    pairs = host_pairs.load([out])
    assert pairs == {
        ("Poaceae", "Ustilaginaceae"): {"types": "hasHost,hostOf", "rows": 2, "source": "10.1/a"}
    }
    assert out.read_text().startswith("# Generated from the GloBI interactions dump of ")


def test_a_lower_threshold_keeps_single_rows_but_never_excluded_types(site, tmp_path):
    dump = tmp_path / "interactions.tsv.gz"
    _dump(dump, ROWS)
    out = tmp_path / "pairs.tsv"
    host_pairs.main(
        ["--site", str(site), "--dump", str(dump), "--out", str(out), "--min-rows", "1"]
    )
    pairs = host_pairs.load([out])
    assert set(pairs) == {("Poaceae", "Ustilaginaceae"), ("Cyperaceae", "Ustilaginaceae")}
    assert pairs[("Cyperaceae", "Ustilaginaceae")]["types"] == "pathogenOf"


def test_the_header_pins_the_dump_and_a_wrong_sha256_writes_nothing(site, tmp_path):
    dump = tmp_path / "interactions.tsv.gz"
    _dump(dump, ROWS)
    sha = hashlib.sha256(dump.read_bytes()).hexdigest()
    out = tmp_path / "pairs.tsv"
    args = ["--site", str(site), "--dump", str(dump), "--out", str(out)]
    assert host_pairs.main([*args, "--sha256", sha.upper()]) == 0
    assert f"# Dump sha256: {sha}\n" in out.read_text()
    out.unlink()
    with pytest.raises(ValueError, match=f"has sha256 {sha}, expected 00"):
        host_pairs.main([*args, "--sha256", "00"])
    assert not out.exists()


def test_a_dump_without_the_family_columns_is_refused(site, tmp_path):
    dump = tmp_path / "interactions.tsv.gz"
    dump.write_bytes(gzip.compress(b"a\tb\nx\ty\n"))
    with pytest.raises(ValueError, match="lacks a column"):
        host_pairs.main(["--site", str(site), "--dump", str(dump), "--out", str(tmp_path / "o")])


def test_the_committed_pair_files_load_with_a_source_on_every_row():
    pairs = host_pairs.load()
    assert pairs and all(p["source"] for p in pairs.values())
    assert all(a < b for a, b in pairs)
