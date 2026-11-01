import json

import pandas as pd

from what_to_id import blind_answers as ba
from what_to_id.blind_skill import fit

RECORDS = [{"id": 1, "group": "Fungi", "photos": []}, {"id": 2, "group": "Fungi", "photos": []}]


def _export(path, login, rows):
    with path.open("w") as f:
        for rid, taxon, conf in rows:
            f.write(
                json.dumps(
                    {
                        "record_id": rid,
                        "login": login,
                        "taxon": taxon,
                        "confidence": conf,
                        "seconds": 3.2,
                        "saved_at": "2026-11-01T20:00:00Z",
                    }
                )
                + "\n"
            )
    return path


def test_exports_to_fit(tmp_path):
    a = _export(tmp_path / "a.jsonl", "ann", [(1, "Amanita muscaria", "sure"), (2, "", "abstain")])
    b = _export(
        tmp_path / "b.jsonl", "bob", [(1, "Amanita muscaria", "likely"), (2, "Fly agaric", "guess")]
    )
    c = _export(
        tmp_path / "c.jsonl",
        "cy",
        [(1, " amanita pantherina ", "guess"), (1, "Amanita muscaria", "sure")],
    )
    exports = ba.read_exports([a, b, c])
    assert len(exports) == 5  # cy's second answer to record 1 replaced the first
    assert (
        exports.loc[(exports.login == "cy") & (exports.record_id == 1), "taxon"].item()
        == "Amanita muscaria"
    )

    seen = []
    lookup = lambda n: seen.append(n) or {"Amanita muscaria": 48715, "Fly agaric": 48715}.get(n)  # noqa: E731
    names, missing = ba.resolve(exports["taxon"].tolist(), {"Amanita muscaria": 48715}, lookup)
    assert seen == ["Fly agaric"]  # known names and the empty abstention are not looked up
    assert names == {"Amanita muscaria": 48715, "Fly agaric": 48715} and missing == []

    df = ba.answers_frame(exports, RECORDS, names)
    assert list(df.columns) == ba.COLUMNS
    assert set(df["group"]) == {"Fungi"}
    assert df.loc[(df.login == "ann") & (df.record_id == 2), "taxon_id"].item() == ba.ABSTAIN
    skill, cons = fit(df)
    assert cons.set_index("record_id")["taxon_id"].to_dict() == {1: 48715, 2: 48715}
    assert cons.set_index("record_id")["n_abstain"].to_dict() == {1: 0, 2: 1}
    assert set(skill["login"]) == {"ann", "bob", "cy"}


def test_unresolved_and_unknown_record(tmp_path):
    e = _export(tmp_path / "a.jsonl", "ann", [(1, "Amanta muscaria", "sure"), (9, "x", "sure")])
    exports = ba.read_exports([e])
    names, missing = ba.resolve(exports["taxon"].tolist(), {}, lambda n: None)
    assert missing == ["Amanta muscaria", "x"] and names == {}
    try:
        ba.answers_frame(exports, RECORDS, {"x": 1})
    except ValueError as err:
        assert "9" in str(err)
    else:
        raise AssertionError("record 9 is not in records.json")


def test_empty_export(tmp_path):
    (tmp_path / "e.jsonl").write_text("")
    exports = ba.read_exports([tmp_path / "e.jsonl"])
    assert exports.empty
    assert ba.answers_frame(exports, RECORDS, {}).empty


def test_main_writes_parquet_and_names(tmp_path, monkeypatch):
    monkeypatch.setattr(ba, "inat_lookup", lambda n, session=None: 48715)
    e = _export(tmp_path / "a.jsonl", "ann", [(1, "Amanita muscaria", "sure")])
    rec, names, out = tmp_path / "r.json", tmp_path / "n.json", tmp_path / "a.parquet"
    rec.write_text(json.dumps(RECORDS))
    assert ba.main([str(e), "--records", str(rec), "--names", str(names), "--out", str(out)]) == 0
    assert json.loads(names.read_text()) == {"Amanita muscaria": 48715}
    assert pd.read_parquet(out)["taxon_id"].tolist() == [48715]
