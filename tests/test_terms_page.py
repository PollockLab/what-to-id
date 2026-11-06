"""terms.html: every glossary key is an anchor, every More link lands on one, the copied
explanations equal their sources, and the frozen study page is untouched."""

import json
import re
from pathlib import Path

from what_to_id import page_identify, page_nav, terms_page
from what_to_id.glossary import GLOSSARY

SRC = Path(page_nav.__file__).parent


def _ids(html):
    return set(re.findall(r'\bid="([^"]+)"', html))


def test_every_glossary_key_is_one_anchor_in_one_group():
    grouped = [k for keys in terms_page.GROUPS.values() for k in keys]
    assert sorted(grouped) == sorted(GLOSSARY)
    html = terms_page.render()
    for key in GLOSSARY:
        assert f'<dt id="{key}">' in html
    assert html.count("<dt id=") == len(GLOSSARY)
    assert "Needs ID</dt>" in html and "Narrow it down</dt>" in html


def test_labels_read_id_as_ID_and_match_the_page():
    assert terms_page.label("agreeing-ids") == "Agreeing IDs"
    assert terms_page.label("share-needing-id") == "Share needing ID"
    assert terms_page.label("identified-to-rank") == "Identified to rank"
    # the user filter's tick labels on the map
    assert terms_page.label("not-identified-by-me") == "Hide records I identified"
    assert terms_page.label("my-taxa") == "Only my genera"
    assert terms_page.label("observer-filter") == "Only records I observed"


def test_every_more_link_targets_an_anchor():
    data = re.search(r'id="explain-data">(.*?)</script>', page_nav.nav("map.html")).group(1)
    ids = _ids(terms_page.render())
    hrefs = {k: v[2] for k, v in json.loads(data).items()}
    assert hrefs.keys() == GLOSSARY.keys()
    for key, href in hrefs.items():
        page, _, frag = href.partition("#")
        assert page == "terms.html" and frag in ids, key
    assert "target='_blank'" in (SRC / "site_assets/explain.js").read_text()


def test_the_copied_explanations_equal_their_sources():
    html = terms_page.render()
    text = lambda p: (SRC / p).read_text()  # noqa: E731
    sources = {
        "identify": text("identify_assets/identify.html"),
        "confusion": text("confusion_assets/confusion.html"),
        "tree": text("tree_assets/tree.html"),
        "space": text("embeddings_assets/embeddings.html"),
    }
    # the Identify About, once its placeholders are filled the way page_identify fills them
    about = re.search(r"</summary>(.*?)</details>", page_identify.render(), re.S).group(1)
    assert about.strip() in html and "__" not in about
    for src, pattern in (
        ("confusion", r"</summary>\n(<dl>.*?)<dt>Built</dt>"),
        ("tree", r'<p id="about" hidden>(.*?)</p>'),
        ("space", r'<p class="note" id="honest">(.*?)</p>'),
    ):
        copied = (
            re.search(pattern, sources[src], re.S).group(1).replace('<span id="fid"></span> ', "")
        )
        assert copied.strip() in html, src
    assert "__" not in html.split("</style>")[1]


def test_identify_dates_flow_through(tmp_path):
    (tmp_path / page_identify.DATES_NAME).write_text(
        json.dumps({"photos": "2026-01-02", "scored": "2026-02-03"})
    )
    html = terms_page.build(tmp_path).read_text()
    assert "Photos downloaded on 2 January 2026, scored on 3 February 2026." in html


def test_no_nav_tab_and_study_stays_frozen():
    assert "terms.html" not in [p for p, _ in page_nav.PAGES]
    study = page_nav.nav("study.html")
    assert "terms.html" not in study and "explain-data" not in study
