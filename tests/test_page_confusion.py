"""The confused-pairs page: order, anchors, links, the taxa list, and a manifest without the key."""

import json

import pandas as pd

from what_to_id import page_confusion


def _frame():
    cols = "taxon_id taxon_name looks_like_taxon_id looks_like_name n_photos n_species_photos share"
    return pd.DataFrame(
        [
            (1, "Aus bus", 2, "Cus dus", 3, 10, 0.3),
            (7, "Eus fus", 2, "Cus dus", 9, 12, 0.75),
            (1, "Aus bus", 5, "Gus hus", 5, 10, 0.5),
        ],
        columns=cols.split(),
    )


def test_build_from_parquet(tmp_path):
    pq = tmp_path / "c.parquet"
    _frame().to_parquet(pq)
    out = tmp_path / "site"
    assert page_confusion.main(["--out", str(out), "--parquet", str(pq)]) == 0
    html = (out / "confusion.html").read_text()
    rows = html.split("<tbody>")[1].split("<tr")[1:]
    assert [
        r.count("Eus") + 2 * r.count("Gus") + 3 * r.count("Aus bus</i></td><td><i>Cus")
        for r in rows
    ] == [1, 2, 3]
    assert html.count('id="t1"') == 1 and html.count('id="t7"') == 1
    assert html.index('id="t1"') < html.index("Gus hus")  # first row in table order
    assert "75%" in html and "50%" in html and "30%" in html
    assert (
        'href="https://www.inaturalist.org/observations/identify?taxon_id=7&place_id=7085'
        '&quality_grade=needs_id" target="_blank" rel="noopener"'
    ) in html
    assert "<i>Aus bus</i>" in html and ">Confused pairs<" in html
    assert json.loads((out / "confusion-taxa.json").read_text()) == [1, 7]


def test_manifest_without_the_key_writes_nothing(tmp_path, monkeypatch):
    def fetch(url, path):
        path.write_text(json.dumps({"version": 1}))

    monkeypatch.setattr(page_confusion, "_fetch", fetch)
    assert page_confusion.main(["--out", str(tmp_path), "--data-url", "https://x.test/"]) == 0
    assert list(tmp_path.iterdir()) == []


def test_manifest_with_the_key_shows_built_date(tmp_path, monkeypatch):
    pq = tmp_path / "src.parquet"
    _frame().to_parquet(pq)
    entry = {"name": "confusion.parquet", "built_at": "2026-10-20T03:00:00Z", "count": 3}

    def fetch(url, path):
        if url.endswith("manifest.json"):
            path.write_text(json.dumps({"confusion": entry}))
        else:
            path.write_bytes(pq.read_bytes())

    monkeypatch.setattr(page_confusion, "_fetch", fetch)
    out = tmp_path / "site"
    assert page_confusion.main(["--out", str(out), "--data-url", "https://x.test/"]) == 0
    assert "Built 2026-10-20" in (out / "confusion.html").read_text()
