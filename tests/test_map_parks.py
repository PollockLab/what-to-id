import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from what_to_id.map_parks import encode_rings, parks_blob, parks_version, read_parks
from what_to_id.page_map import _ASSETS

_SCRIPT = Path(__file__).parents[1] / "scripts" / "bc_park_places.py"


def _script():
    spec = importlib.util.spec_from_file_location("bc_park_places", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_encode_rings_codes_as_the_page_does():
    rings = [[-123.12345, 49.2, -123, 49.30005, -122.9, 49.2], [0, 0, 0.0001, 0, 0, -0.0001]]
    js = (
        "var document={};" + (_ASSETS / "map_area.js").read_text()
        + f"console.log(JSON.stringify([MapArea.encode({json.dumps(rings)}),"
        + f"MapArea.decode({json.dumps(encode_rings(rings))})]));"
    )  # fmt: skip
    code, back = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True,
                                           check=True).stdout)  # fmt: skip
    assert encode_rings(rings) == code
    assert back[0] == [-123.1234, 49.2, -123, 49.3001, -122.9, 49.2]


def test_park_list_holds_every_bc_area_once():
    doc = read_parks()
    assert doc["kinds"] == ["Park", "Ecological reserve", "Protected area", "Recreation area",
                            "Conservancy"]  # fmt: skip
    rows = doc["parks"]
    kind = {r[1]: doc["kinds"][r[2]] for r in rows}
    assert kind["Strathcona Park"] == "Park"
    assert kind["Tacheeda Lakes Ecological Reserve"] == "Ecological reserve"
    keys = [r[0] for r in rows]
    assert len(keys) == len(set(keys))
    assert all(re.fullmatch(r"\d{4}(-\d+)?", k) for k in keys)
    # a park in several sites has a row for each site and one for the whole park
    sites = {k.split("-")[0] for k in keys if "-" in k}
    assert sites and sites <= set(keys)
    for key, name, kind, place, bbox, rings, alt in rows:
        assert name and name == name.strip() and 0 <= kind < len(doc["kinds"])
        assert isinstance(place, int) and place >= 0 and isinstance(alt, str)
        w, s, e, n = bbox
        assert -140 < w < e < -114 and 48 < s < n < 60.1, key
        # a matched park takes its boundary from iNaturalist; the rest carry their own
        assert (rings == "") == bool(place), key
        assert place or re.fullmatch(r"[A-Za-z0-9_\-]+(\.[A-Za-z0-9_\-]+)*", rings), key
    # a matched place stands for one area only
    places = [r[3] for r in rows if r[3]]
    assert len(places) == len(set(places))
    assert len(parks_version(parks_blob())) == 12


def test_names_come_out_readable():
    m = _script()
    assert m.display("STRATHCONA PARK") == "Strathcona Park"
    assert m.display("BABINE MOUNTAINS PARK") == "Babine Mountains Park"
    assert (m.display("TAHSISH-KWOIS PARK [A.K.A. TAHSISH RIVER]")
            == "Tahsish-Kwois Park (a.k.a. Tahsish River)")  # fmt: skip
    # the catalogue cuts names at 50 characters
    assert m.display("SOMETHING VERY LONG AND WINDING CREEK PROVINCIAL PA") == (
        "Something Very Long and Winding Creek Provincial Park"
    )
    assert m.display("A NAME LONG ENOUGH THAT THE CATALOGUE CUTS IT [A.K.A") == (
        "A Name Long Enough That the Catalogue Cuts It"
    )


def test_names_match_across_forms_and_designations():
    m = _script()
    assert m.core("Strathcona Provincial Park") == m.core("STRATHCONA PARK") == "strathcona"
    assert "TAHSISH RIVER" in m.forms("TAHSISH-KWOIS PARK [A.K.A. TAHSISH RIVER]")
    assert m.forms("A / B PARK") == ["A / B PARK", "A", "B PARK"]
    assert m.name_score("CAPE SCOTT PARK", "Cape Scott Provincial Park") == 1.0
    assert m.name_score("CAPE SCOTT PARK", "Cape Sutil") < m.MIN_NAME
    # a park and a protected area often share a name, and are different areas
    assert m.kind_ok("PROVINCIAL PARK", "Cape Scott Provincial Park")
    assert not m.kind_ok("PROVINCIAL PARK", "Cape Scott Protected Area")
    assert m.kind_ok("RECREATION AREA", "Strathcona-Westmin Provincial Park")
    assert m.kind_ok("ECOLOGICAL RESERVE", "Ten Mile Point")
