"""The glossary behind the toggletips: every tagged key has an entry, every entry is plain, and the
study and blind pages, frozen for the preregistered study, carry none of it."""

import re
from pathlib import Path

from what_to_id import page_blind, page_nav
from what_to_id.glossary import GLOSSARY
from what_to_id.page_rotation import render_rotation_index

from .test_page_nav import FORBIDDEN
from .test_page_rotation import _manifest

SRC = Path(page_nav.__file__).parent
# data-explain="k" in html, 'data-explain':'k' in an attrs object, .dataset.explain='k' in js
TAG = re.compile(r"""(?:data-explain|dataset\.explain)['"]?\s*[:=]\s*['"]([^'"<>]+)['"]""")
MARKS = ("explain-data", "explain-pop", "data-explain", "xpop")


def _tagged():
    keys = {}
    for path in SRC.rglob("*"):
        if path.suffix in {".js", ".html", ".py"} and path.name != "explain.js":
            for key in TAG.findall(path.read_text()):
                keys.setdefault(key, path.relative_to(SRC))
    return keys


def test_every_tagged_key_is_in_the_glossary():
    keys = _tagged()
    assert {"left-needs-id", "needs-id", "location-accuracy"} <= keys.keys()
    assert {k: str(p) for k, p in keys.items() if k not in GLOSSARY} == {}


def test_tag_pattern_reads_each_way_of_tagging():
    text = """<b data-explain="a">x</b> el('span',{'data-explain':'b'}) e.dataset.explain='c'"""
    assert TAG.findall(text) == ["a", "b", "c"]
    assert TAG.findall("x.dataset.explain]") == []


def test_entries_are_plain_sentences():
    assert GLOSSARY
    for key, entry in GLOSSARY.items():
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", key), key
        definition, use = entry
        assert definition.strip() and definition.rstrip().endswith("."), key
        assert use is None or (use.strip() and use.startswith("Use it when ")), key
        text = " ".join(x for x in entry if x)
        assert "—" not in text and "--" not in text, key
        assert not [w for w in FORBIDDEN if w in text.lower()], key


def test_nav_carries_the_glossary_and_script_once():
    html = page_nav.nav("map.html")
    assert html.count('id="explain-data"') == 1 and "explain-pop" in html
    data = re.search(r'id="explain-data">(.*?)</script>', html).group(1)
    assert "</" not in data


def test_study_and_blind_pages_carry_none_of_it():
    pages = {
        "nav": page_nav.nav("study.html"),
        "study": render_rotation_index(_manifest(), title="t", map_href="map.html"),
        "blind": page_blind.render([]),
    }
    assert {k: [m for m in MARKS if m in v] for k, v in pages.items()} == {
        "nav": [],
        "study": [],
        "blind": [],
    }


def test_keys_built_in_script_are_in_the_glossary():
    # the Identify tabs map level numbers to keys, the legend switch names its keys beside its modes
    app = (SRC / "identify_assets/identify_app.js").read_text()
    keys = re.findall(r"'([a-z-]+)'", re.search(r"var XK=\[0,([^\]]+)\]", app).group(1))
    assert len(keys) == 5
    legend = (SRC / "map_assets/level_colour.js").read_text()
    keys += re.findall(r"'(colour-by-[a-z]+)'", legend)
    assert len(keys) == 7 and [k for k in keys if k not in GLOSSARY] == []


def test_every_glossary_key_is_tagged_on_some_page():
    # quoted anywhere in a page asset: tags, and keys picked in script (Identify tabs, user modes)
    text = "".join(
        p.read_text()
        for p in SRC.rglob("*")
        if p.suffix in {".js", ".html"} and p.name != "explain.js"
    )
    assert [k for k in GLOSSARY if f"'{k}'" not in text and f'"{k}"' not in text] == []
