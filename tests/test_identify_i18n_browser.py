"""Identify's language and names settings in Chromium: the gear's popover switches the page to
French (text, <html lang>, species' French names from the build) and sets how names show, both
kept over a reload, and none of it moves a card. iNaturalist is stubbed."""

import numpy as np
import pytest

from what_to_id import page_identify, pool_levels, taxonomy

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib
from .embeddings_fixture import pool_frame

browser = eb.browser
HELP = "#helpb"  # its aria-label is "About, notes and keys"
FR = {1000 + k: f"Commun {k}" for k in range(7)}


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    """A site whose species have English and French common names."""
    pytest.importorskip("pyarrow")
    root = tmp_path_factory.mktemp("identify-i18n")
    ids = np.random.default_rng(1).choice(2**32 - 2, 600, replace=False) + 1
    score = np.random.default_rng(2).normal(size=600).astype("float32")
    frame = pool_frame(ids)
    frame["common_name"] = frame["taxon_id"].map(lambda t: f"Common {t - 1000}")
    server, _ = ib.serve(root, frame, score)
    taxonomy.save_fr(FR, root / "fr.json")
    pool_levels.build(root, parquet=root / "identify.parquet", fr=root / "fr.json")
    page_identify.build(root)
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def set_to(page, name, value):
    """Pick a radio in the Settings popover; the page reloads."""
    page.click("#setb")
    with page.expect_event("load"):
        page.locator(f'#setpop input[name="{name}"][value="{value}"]').check(force=True)
    page.wait_for_function("window.__identify && __identify.ids().length > 0")


def common(page):
    """The common names of the cards drawn (the hidden .com line the panel shows)."""
    return page.evaluate(
        "[...document.querySelectorAll('#grid .card .title .com')].map(e=>e.textContent)"
    )


def test_french_changes_the_text_and_lang_and_survives_a_reload(browser, site):
    page = ib.open_identify(browser, site)
    assert page.evaluate("document.documentElement.lang") == "en"
    en = page.get_attribute(HELP, "aria-label")
    assert set(common(page)) <= {f"Common {k}" for k in range(7)} and common(page)
    set_to(page, "lang", "fr")
    assert page.evaluate("document.documentElement.lang") == "fr"
    fr = page.get_attribute(HELP, "aria-label")
    assert fr and fr != en
    assert page.locator("#setb").get_attribute("aria-label") != "Settings"
    assert set(common(page)) <= set(FR.values()) and common(page)  # the build's French names
    page.reload()
    page.wait_for_function("window.__identify && __identify.ids().length > 0")
    assert page.evaluate("document.documentElement.lang") == "fr"
    assert page.get_attribute(HELP, "aria-label") == fr
    assert page.locator('#setpop input[value="fr"]').is_checked()
    assert not page.errors
    set_to(page, "lang", "en")  # and back
    assert (
        page.get_attribute(HELP, "aria-label") == en
        and page.evaluate("document.documentElement.lang") == "en"
    )


def test_a_french_browser_opens_in_french_and_a_missing_name_falls_back(browser, site):
    page = browser.new_context(locale="fr-CA").new_page()
    page.goto(f"{site}/identify.html")
    page.wait_for_function("window.__identify && __identify.ids().length > 0")
    assert page.evaluate("document.documentElement.lang") == "fr"
    # a species with no French name keeps its English one, and with neither its Latin name shows
    fr = page.evaluate(
        "[...document.querySelectorAll('#grid .card .title .com')].map(e=>e.textContent)"
    )
    assert fr and all(n.startswith("Commun ") for n in fr)


def test_latin_hides_common_names_and_common_shows_them_first(browser, site):
    page = ib.open_identify(browser, site)
    both = page.evaluate(
        "[...document.querySelectorAll('#grid .card .face .hl')].map(e=>e.textContent)"
    )
    assert both and all(t.startswith("Taxon ") or t.startswith("Genus") for t in both)
    assert common(page)
    set_to(page, "names", "latin")
    assert common(page) == []
    assert "Common" not in page.inner_text("#grid")
    set_to(page, "names", "common")
    heads = page.evaluate(
        "[...document.querySelectorAll('#grid .card .face .hl')].map(e=>e.textContent)"
    )
    assert heads and sum(t.startswith("Common ") for t in heads) > len(heads) // 2
    assert page.locator('#setpop input[value="common"]').is_checked()
    set_to(page, "names", "both")
    assert common(page)


def view(page):
    """Every level's served ids, once the background loads have settled."""
    page.wait_for_load_state("networkidle")
    return page.evaluate("__identify.view()")


def test_the_cards_come_in_the_same_order_in_english_french_and_latin(browser, site):
    page = ib.open_identify(browser, site)
    en = view(page)
    assert any(en)
    set_to(page, "lang", "fr")
    assert view(page) == en
    set_to(page, "names", "latin")
    assert view(page) == en


def test_the_gear_opens_by_key_escape_closes_and_focus_returns(browser, site):
    page = ib.open_identify(browser, site)
    page.focus("#setb")
    page.keyboard.press("Enter")
    page.wait_for_selector("#setpop:popover-open")
    assert page.locator('#setpop input[name="names"][value="both"]').is_checked()  # the default
    page.keyboard.press("Escape")
    page.wait_for_selector("#setpop:not(:popover-open)", state="attached")
    assert page.evaluate("document.activeElement.id") == "setb"
