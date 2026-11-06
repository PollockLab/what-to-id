import gzip
import json

import pytest

from what_to_id import sdm_manifest
from what_to_id.page_map import main, write_map
from what_to_id.sdm_manifest import BASE, COG, load, match, sdm_meta
from what_to_id.site_files import read_meta

from .conftest import make_pool

# as the ECCC manifest: one-item lists, synonyms joined by ~ or None
FAKE = {
    "bombus-a": {"Species": ["Bombus a"], "IUCN.Synonoms": ["Apis old~Bombus older"], "files": []},
    "apis-b": {"Species": ["Apis b"], "IUCN.Synonoms": [None], "files": []},
    "apis-c": {"Species": ["Apis c"], "IUCN.Synonoms": ["Apis b~Apis shared"], "files": []},
    "apis-d": {"Species": ["Apis d"], "IUCN.Synonoms": ["Apis shared"], "files": []},
}


def test_match_by_species_and_synonym_case_and_space_blind():
    names = ["bombus A ", "Bombus older", "Apis old", "Vulpes vulpes", None, ""]
    assert match(FAKE, names) == {0: "bombus-a", 1: "bombus-a", 2: "bombus-a"}


def test_a_name_two_slugs_claim_goes_to_its_species_or_to_none():
    # "Apis b" is apis-b's species and apis-c's synonym; "Apis shared" only synonyms of two
    assert match(FAKE, ["Apis b", "Apis shared", "Apis c"]) == {0: "apis-b", 2: "apis-c"}


def test_match_of_nothing():
    assert match({}, ["Bombus a"]) == {} and match(FAKE, []) == {}


def test_the_cogs_sit_beside_a_manifest_url_and_at_base_for_a_local_copy(tmp_path, monkeypatch):
    f = tmp_path / "manifest.json"
    f.write_text(json.dumps(FAKE))
    assert load(f) == FAKE
    assert sdm_meta(f, ["Taxon", "Apis c"]) == {"cog": f"{BASE}/{COG}", "taxa": {"1": "apis-c"}}

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return FAKE

    monkeypatch.setattr(sdm_manifest.requests, "get", lambda url, timeout: R())
    m = sdm_meta("https://example.org/a/manifest.json", ["Bombus a"])
    assert m == {
        "cog": f"https://example.org/a/{COG}",
        "taxa": {"0": "bombus-a"},
    }


def _pool():
    pool = make_pool(60)
    pool["taxon_name"] = [["Bombus a", "Apis c", "Vulpes x"][t % 3] for t in pool["taxon_id"]]
    return pool


def test_write_map_lists_each_taxon_row_with_a_model(tmp_path):
    f = tmp_path / "manifest.json"
    f.write_text(json.dumps(FAKE))
    out = tmp_path / "site"
    write_map(out, _pool(), sdm_manifest=f)  # raises if an arm word reaches the page
    meta = read_meta((out / "map.html").read_text())
    taxa = json.loads(gzip.decompress((out / meta["taxa"]).read_bytes()))
    want = {
        str(i): {"Bombus a": "bombus-a", "Apis c": "apis-c"}[t[0]]
        for i, t in enumerate(taxa)
        if t[0] in ("Bombus a", "Apis c")
    }
    assert want and meta["sdm"] == {"cog": f"{BASE}/{COG}", "taxa": want}


def test_without_a_manifest_the_page_has_no_models(tmp_path):
    write_map(tmp_path, _pool())
    assert "sdm" not in read_meta((tmp_path / "map.html").read_text())


def test_the_cli_reads_the_manifest(tmp_path):
    pytest.importorskip("pyarrow")
    f = tmp_path / "manifest.json"
    f.write_text(json.dumps(FAKE))
    _pool().to_parquet(tmp_path / "pool.parquet")
    main(
        ["--pool", str(tmp_path / "pool.parquet"), "--out", str(tmp_path), "--sdm-manifest", str(f)]
    )
    assert read_meta((tmp_path / "map.html").read_text())["sdm"]["taxa"]


def test_write_map_goes_on_without_the_manifest(tmp_path):
    """A manifest that cannot be read drops the habitat line, not the build."""
    out = tmp_path / "site"
    write_map(out, _pool(), sdm_manifest=tmp_path / "missing.json")
    assert "sdm" not in read_meta((out / "map.html").read_text())
