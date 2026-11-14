"""scripts/foodweb_progress.py: one CSV row from stubbed iNaturalist responses."""

import csv
import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).parents[1] / "scripts" / "foodweb_progress.py"


def _load():
    spec = importlib.util.spec_from_file_location("foodweb_progress", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _o(id_, name, field_id, taxon=None):
    return {
        "id": id_,
        "taxon": {"name": name, "id": id_},
        "photos": [{"url": "https://x/photos/1/square.jpg"}],
        "ofvs": [{"field_id": field_id, "taxon": {"name": taxon, "id": 1}}] if taxon else [],
    }


class _Resp:
    def __init__(self, results):
        self._r = results

    def raise_for_status(self):
        pass

    def json(self):
        return {"results": self._r}


def test_one_row_counts_species_coarse_and_distinct_edges(tmp_path, monkeypatch):
    mod = _load()
    by_field = {
        "field:Eating": [
            _o(1, "Strix varia", 13, "Mus musculus"),
            _o(2, "Strix varia", 13, "Mus musculus"),  # the same edge again
            _o(3, "Strix varia", 13, "Myodes"),  # coarse
            _o(4, "Strix varia", 13),  # empty field
        ],
        "field:Eaten by": [_o(5, "Mus musculus", 879, "Buteo jamaicensis")],
    }

    def get(url, params, **kw):
        key = next(k for k in params if k.startswith("field:"))
        return _Resp(by_field[key])

    monkeypatch.setattr("requests.get", get)
    out = tmp_path / "p.csv"
    assert mod.main(["--out", str(out)]) == 0
    assert mod.main(["--out", str(out)]) == 0  # appends, one header
    rows = list(csv.DictReader(out.open()))
    assert len(rows) == 2 and out.read_text().count("date,") == 1
    r = rows[0]
    assert (r["n_obs"], r["n_named_species"], r["n_coarse"], r["n_green_edges"]) == (
        "5",
        "3",
        "1",
        "2",
    )


def test_no_observations_gives_a_zero_row():
    r = _load().row([], "2026-11-13")
    assert [r[c] for c in ("n_obs", "n_named_species", "n_coarse", "n_green_edges")] == [0] * 4
