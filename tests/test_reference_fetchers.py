import json

import at_risk_bc_taxa
import pytest
import reference_common as rc


def _doc(n):
    return {"source": "s", "taxa": list(range(n))}


def test_write_refuses_a_drop_over_ten_percent_unless_forced(tmp_path):
    out = tmp_path / "l.json"
    rc.write(out, _doc(100), force=False)  # nothing to compare with yet
    rc.write(out, _doc(90), force=False)  # exactly 10% is allowed
    with pytest.raises(SystemExit, match="drop over 10%"):
        rc.write(out, _doc(80), force=False)
    assert len(json.loads(out.read_text())["taxa"]) == 90  # the refusal left the file alone
    rc.write(out, _doc(80), force=True)
    assert json.loads(out.read_text())["fetched"] == str(rc.date.today())


def _cs(authority, status, iucn=None, place=None):
    return {"authority": authority, "status": status, "iucn": iucn, "place": place}


@pytest.mark.parametrize(
    ("statuses", "want"),
    [
        ([], None),
        ([_cs("COSEWIC", "special_concern")], 1),
        ([_cs("Canadian Species at Risk Act", "Extirpated"), _cs("NatureServe", "S1", 50)], 1),
        ([_cs("COSEWIC", "not at risk")], None),
        ([_cs("NatureServe", "S2", 40, {"id": 7085})], 2),
        ([_cs("NatureServe", "S3", 30, {"id": 7085})], 3),
        ([_cs("NatureServe", "S1", 50, {"id": 46})], None),  # another place's rank
    ],
)
def test_tier(statuses, want):
    assert at_risk_bc_taxa.tier(statuses) == want
