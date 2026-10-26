"""The confused-pairs page: the data file round-trips the pairs and records, the pairs-only build,
the taxa list, and a manifest without the key."""

import gzip
import json

import numpy as np
import pandas as pd

from what_to_id import page_confusion

OPEN = "https://inaturalist-open-data.s3.amazonaws.com/photos/"
STATIC = "https://static.inaturalist.org/photos/"


def pairs_frame():
    cols = "taxon_id taxon_name looks_like_taxon_id looks_like_name n_photos n_species_photos share"
    return pd.DataFrame(
        [
            (1, "Aus bus", 2, "Cus dus", 3, 10, 0.3),
            (7, "Eus fus", 2, "Cus dus", 9, 12, 0.75),
            (1, "Aus bus", None, "Gus hus", 5, 10, 0.5),
        ],
        columns=cols.split(),
    ).astype({"looks_like_taxon_id": "Int64"})


def records_frame():
    rows = [
        (101, 1, "Aus bus", "Plantae", 2, "Cus dus", -0.02, f"{OPEN}11/medium.jpg"),
        (102, 1, "Aus bus", "Plantae", None, "Gus hus", -0.30, f"{STATIC}12/medium.jpeg?1545"),
        (103, 1, "Aus bus", "Plantae", 2, "Cus dus", -0.10, f"{OPEN}13/medium.png"),
        (104, 1, "Aus bus", "Plantae", None, "Gus hus", -0.05, "https://example.org/x.jpg"),
        (201, 7, "Eus fus", "Fungi", 2, "Cus dus", -0.20, f"{OPEN}21/medium.jpg"),
        (202, 7, "Eus fus", "Fungi", 2, "Cus dus", -0.01, f"{STATIC}22/medium.jpg"),
    ]
    return pd.DataFrame(rows, columns=list(page_confusion.RECORD_COLUMNS)).astype(
        {"looks_like_taxon_id": "Int64"}
    )


def decode(blob):
    """The header and record columns of confusion-data.bin, as the page reads them."""
    raw = gzip.decompress(blob)
    h = int.from_bytes(raw[:4], "little")
    head = json.loads(raw[4 : 4 + h])
    n, o, cols = head["n"], (4 + h + 3) // 4 * 4, {}
    for name, dt in [("id", "<u4"), ("photo", "<u4"), ("taxon", "<u2"), ("looks", "<u2")] + [
        ("score", "u1"),
        ("meta", "u1"),
    ]:
        cols[name] = np.frombuffer(raw, dt, n, o)
        o += n * np.dtype(dt).itemsize
    assert o == len(raw)
    return head, cols


def photo_url(head, cols, i):
    m, e = int(cols["meta"][i]), len(head["exts"])
    if m == page_confusion.NO_PHOTO:
        return None
    return f"{head['hosts'][m // e]}{cols['photo'][i]}/medium.{head['exts'][m % e]}"


def write(tmp_path, records=True):
    pq, rq = tmp_path / "c.parquet", tmp_path / "r.parquet"
    pairs_frame().to_parquet(pq)
    args = ["--out", str(tmp_path / "site"), "--parquet", str(pq)]
    if records:
        records_frame().to_parquet(rq)
        args += ["--records-parquet", str(rq)]
    assert page_confusion.main(args) == 0
    return tmp_path / "site"


def test_full_build_round_trips_pairs_and_records(tmp_path):
    out = write(tmp_path)
    head, cols = decode((out / "confusion-data.bin").read_bytes())
    taxa = head["taxa"]
    named = [(taxa[t][1], taxa[lk][1], n, s) for t, lk, n, s in head["pairs"]]
    assert named == [
        ("Eus fus", "Cus dus", 9, 12),
        ("Aus bus", "Gus hus", 5, 10),
        ("Aus bus", "Cus dus", 3, 10),
    ]
    by_name = {x[1]: x for x in taxa}
    assert by_name["Gus hus"][0] is None and by_name["Cus dus"][0] == 2
    groups = [g for g, _ in head["groups"]]
    assert sorted(head["groups"]) == [["Fungi", 2], ["Plantae", 4]]
    assert groups[by_name["Eus fus"][2]] == "Fungi" and by_name["Cus dus"][2] is None

    assert cols["id"].tolist() == [102, 103, 104, 101, 201, 202]  # by species, worst first
    assert [taxa[t][1] for t in cols["taxon"]] == ["Aus bus"] * 4 + ["Eus fus"] * 2
    assert [taxa[t][1] for t in cols["looks"]][:2] == ["Gus hus", "Cus dus"]
    assert cols["score"][0] == 0 and cols["score"][-1] == 255
    assert np.all(np.diff(cols["score"][:4].astype(int)) > 0)
    lo, hi = head["score"]
    assert (lo, hi) == (-0.30, -0.01)
    assert [photo_url(head, cols, i) for i in range(6)] == [
        f"{STATIC}12/medium.jpeg",
        f"{OPEN}13/medium.png",
        None,
        f"{OPEN}11/medium.jpg",
        f"{OPEN}21/medium.jpg",
        f"{STATIC}22/medium.jpg",
    ]
    html = (out / "confusion.html").read_text()
    assert ">Confused pairs<" in html and "norecords" not in html
    assert "confusion-data.bin?v=" in html and "var IdentifyLinks" in html
    assert not [k for k in ("__CONFIG__", "__SITE_NAV__", "__CONFUSION_APP__") if k in html]
    assert json.loads((out / "confusion-taxa.json").read_text()) == [1, 7]


def test_pairs_only_build_writes_the_pairs_and_the_note(tmp_path):
    out = write(tmp_path, records=False)
    head, cols = decode((out / "confusion-data.bin").read_bytes())
    assert head["n"] == 0 and head["groups"] == [] and len(head["pairs"]) == 3
    assert [head["taxa"][t][1] for t, *_ in head["pairs"]] == ["Eus fus", "Aus bus", "Aus bus"]
    assert "Per-record rows arrive with the next build" in (out / "confusion.html").read_text()
    assert json.loads((out / "confusion-taxa.json").read_text()) == [1, 7]


def test_manifest_without_the_key_writes_nothing(tmp_path, monkeypatch):
    def fetch(url, path):
        path.write_text(json.dumps({"version": 1}))

    monkeypatch.setattr(page_confusion, "_fetch", fetch)
    assert page_confusion.main(["--out", str(tmp_path), "--data-url", "https://x.test/"]) == 0
    assert list(tmp_path.iterdir()) == []


def test_manifest_with_both_keys_fetches_records_and_shows_built_date(tmp_path, monkeypatch):
    pq, rq = tmp_path / "src.parquet", tmp_path / "rec.parquet"
    pairs_frame().to_parquet(pq)
    records_frame().to_parquet(rq)
    entry = {"name": "confusion.parquet", "built_at": "2026-10-20T03:00:00Z", "count": 3}
    rec_entry = {"name": "confusion-records.parquet", "built_at": "x", "count": 6}

    def fetch(url, path):
        if url.endswith("manifest.json"):
            path.write_text(json.dumps({"confusion": entry, "confusion_records": rec_entry}))
        else:
            path.write_bytes((rq if url.endswith("records.parquet") else pq).read_bytes())

    monkeypatch.setattr(page_confusion, "_fetch", fetch)
    out = tmp_path / "site"
    assert page_confusion.main(["--out", str(out), "--data-url", "https://x.test/"]) == 0
    assert "Built 2026-10-20" in (out / "confusion.html").read_text()
    head, _ = decode((out / "confusion-data.bin").read_bytes())
    assert head["n"] == 6 and head["built_at"] == entry["built_at"]


def test_records_without_pairs_file_is_an_error(tmp_path, capsys):
    args = ["--out", str(tmp_path), "--records-parquet", str(tmp_path / "r.parquet")]
    assert page_confusion.main(args) == 1
    assert "--records-parquet needs --parquet" in capsys.readouterr().err
