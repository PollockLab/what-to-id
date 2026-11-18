"""The secondary outcome of scripts/levels_outcome.py: any change of the community taxon."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

from what_to_id import terms_methods, terms_page

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lo", ROOT / "scripts" / "levels_outcome.py")
lo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lo)


def test_any_change_counts_a_record_that_left_with_a_new_taxon(tmp_path):
    ids = np.arange(1, 7)
    pd.DataFrame(
        {"id": ids, "taxon_name": "Sp a", "own": 0.5, "other": 0.49, "other_name": "Sp b"}
    ).to_parquet(tmp_path / "scores.parquet")
    pd.DataFrame(
        {"id": ids, "taxon_id": 1, "rank": "species", "iconic_taxon": "Aves", "user_id": ids}
    ).to_parquet(tmp_path / "before.parquet")
    # 1 stays, 2 is relabelled and stays; 3 to 6 left
    pd.DataFrame({"id": [1, 2], "taxon_id": [1, 9], "taxon_name": "x"}).to_parquet(
        tmp_path / "after.parquet"
    )
    # 3 left under a new taxon, 4 left unchanged, 5 is gone from the API, 6 has no taxon
    pd.DataFrame({"id": [3, 4, 6], "taxon_id": pd.array([7, 1, None], dtype="Int64")}).to_parquet(
        tmp_path / "now.parquet"
    )
    args = (tmp_path / "scores.parquet", tmp_path / "before.parquet", tmp_path / "after.parquet")
    s = lo.cohort(*args, leaver_taxa=tmp_path / "now.parquet").set_index("id")
    assert s["changed_any"].to_dict() == {1: False, 2: True, 3: True, 4: False, 5: False, 6: False}
    assert s["corrected"].to_dict() == {1: False, 2: True, 3: False, 4: False, 5: False, 6: False}


def test_methods_table_comes_from_the_committed_json():
    ev = json.loads(terms_methods.OUTCOME.read_text())
    mis = ev["levels"]["mislabel"]["any_change"]
    html = terms_page.render()
    lo_, hi = mis["per_1000_ci"]
    assert f"<td>{mis['per_1000']:.2f} [{lo_:.2f}, {hi:.2f}]</td>" in html
    assert ev["leaver_taxa_fetched_on"] in html
    assert "leaver_taxa" in ev["inputs"] and len(ev["inputs"]["leaver_taxa"]["sha256"]) == 64
