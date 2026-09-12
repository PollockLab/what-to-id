import pandas as pd
import pytest

from what_to_id.manifest import Manifest
from what_to_id.page import group_name, render_arm_page, render_index, write_site

ARM_NAMES = ["recency", "gap_first", "similarity"]


def _batches():
    return pd.DataFrame(
        {
            "batch_id": ["recency-Aves-000"] * 2
            + ["recency-Insecta-000"]
            + ["gap_first-Aves-000"] * 2,
            "arm": ["recency"] * 3 + ["gap_first"] * 2,
            "group": ["Aves", "Aves", "Insecta", "Aves", "Aves"],
            "position": [0, 1, 0, 0, 1],
            "id": [1, 2, 3, 4, 5],
        }
    )


def _pool():
    return pd.DataFrame(
        {
            "id": [1, 2, 3, 4, 5],
            "photo_url": ["https://p/1.jpg", None, "https://p/3.jpg", "https://p/4.jpg", "x"],
            "observed_on": ["2026-05-01", "2026-06-02", "2026-01-01", None, "2026-02-02"],
            "ident_count": [0, 1, 0, 0, 0],
        }
    )


def _manifest():
    return Manifest(
        freeze="2026-09-01",
        d1="2026-09-15",
        seed=0,
        batch_size=2,
        arms=["recency", "gap_first"],
        arm_labels={"recency": "B", "gap_first": "A"},
        pool_sha256="0" * 64,
        pool_rows=5,
        batches={
            "recency-Aves-000": {
                "arm": "recency",
                "group": "Aves",
                "url": "https://x?id=1,2&a=<b>",
                "ids": [1, 2],
            },
            "recency-Insecta-000": {
                "arm": "recency",
                "group": "Insecta",
                "url": "https://x?id=3",
                "ids": [3],
            },
            "gap_first-Aves-000": {
                "arm": "gap_first",
                "group": "Aves",
                "url": "https://y",
                "ids": [4, 5],
            },
        },
    )


def _assert_blind(html: str) -> None:
    for name in ARM_NAMES:
        assert name not in html


def test_group_name():
    assert group_name("Aves") == "Birds (Aves)"
    assert group_name("Unknownia") == "Unknownia"


def test_render_arm_page_blind_and_escaped():
    b = _batches()
    urls = {k: v["url"] for k, v in _manifest().batches.items()}
    html = render_arm_page("B", b[b["arm"] == "recency"], urls, title="T <1>", pool=_pool())
    assert "Set B" in html and "B-001" in html and "B-002" in html
    _assert_blind(html)
    assert "&lt;1&gt;" in html
    assert "&amp;a=&lt;b&gt;" in html
    assert 'target="_blank"' in html
    assert "Birds (Aves)" in html and 'id="Insecta"' in html
    # batch B-001 holds ids 1 and 2: one photo, one record with no ID yet, two dates
    assert "2 records, 1 with no ID yet, seen 2026-05-01 to 2026-06-02" in html
    assert 'src="https://p/1.jpg"' in html
    assert 'data-batch="B-001"' in html


def test_render_arm_page_without_pool_has_no_thumbs():
    b = _batches()
    urls = {k: v["url"] for k, v in _manifest().batches.items()}
    html = render_arm_page("A", b[b["arm"] == "gap_first"], urls, title="t")
    assert "<img" not in html and "no ID yet" not in html
    assert "2 records" in html


def test_render_arm_page_missing_url():
    b = _batches()
    with pytest.raises(ValueError, match="no url"):
        render_arm_page("A", b, {}, title="t")


def test_render_index():
    html = render_index(_manifest(), _batches(), title="Idx")
    assert 'href="arm_A.html"' in html and "Set B" in html
    assert 'href="arm_B.html#Insecta"' in html
    assert "<td>none</td>" in html  # set A has no Insecta batch
    assert "5 records in 2 groups" in html
    _assert_blind(html)


def test_write_site(tmp_path):
    m = _manifest()
    written = write_site(tmp_path, m, _batches(), pool=_pool())
    names = sorted(p.name for p in written)
    assert names == ["arm_A.html", "arm_B.html", "index.html"]
    for p in written:
        _assert_blind(p.read_text())
    assert "Set B" in (tmp_path / "arm_B.html").read_text()
    assert "https://y" in (tmp_path / "arm_A.html").read_text()


def test_write_site_refuses_leaked_arm_name(tmp_path):
    m = _manifest()
    m.arm_labels = {"recency": "recency", "gap_first": "A"}
    with pytest.raises(ValueError, match="leaked"):
        write_site(tmp_path, m, _batches())
