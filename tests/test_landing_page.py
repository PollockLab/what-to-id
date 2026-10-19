"""The landing page lists only the pages that were built and never names a list."""

from what_to_id.landing_page import build
from what_to_id.page import ARM_WORDS


def test_cards_follow_the_built_pages(tmp_path):
    (tmp_path / "split.html").write_text("x")
    (tmp_path / "study.html").write_text("x")
    page = build(tmp_path, live=("split.html",), day="2026-10-19").read_text()
    html = page.split("<main", 1)[1]  # the cards, not the header tabs
    assert 'href="split.html"' in html and 'href="study.html"' in html
    assert "search.html" not in page
    assert html.index("Experimental") < html.index('href="study.html"')
    assert html.index('href="split.html"') < html.index("Experimental")
    # only the live card is dated; the frozen study card carries no date
    assert html.count("refreshed 2026-10-19") == 1
    assert html.index("refreshed") < html.index("Experimental")
    assert not [w for w in ARM_WORDS if w in page.lower()]


def test_empty_folder_has_no_cards(tmp_path):
    html = build(tmp_path).read_text()
    assert "Choose a task" in html and 'class="card"' not in html and "Experimental" not in html
