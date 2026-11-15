"""Clear filters on Identify in Chromium: shown only while a filter is set, one tap back to the
defaults on the same tab, a clean address and the focus on What. Batches never show it
(test_identify_batches_browser.py)."""

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib
from .test_identify_unconfirmed_browser import RING

browser = eb.browser
site = ib.site
open_identify = ib.open_identify


def ready(browser, base, hash_):
    page = open_identify(browser, base, hash_, size=(1280, 900))
    page.wait_for_function("window.__identify")
    page.wait_for_load_state("networkidle")
    return page


def test_clear_filters_restores_the_defaults_on_the_same_tab(browser, site):
    base, _ = site
    clean = ready(browser, base, "#lvl=3")
    assert clean.locator("#fclear").is_hidden()
    want = clean.evaluate("__identify.total()")
    area = clean.evaluate("r => MapArea.encode([r])", RING)
    page = ready(browser, base, f"#groups=Aves&months=6&risk=1&inv=1&conf=all&lvl=3&area={area}")
    assert page.evaluate("__identify.total()") != want
    button = page.locator("#fclear")
    assert button.is_visible() and button.get_attribute("aria-label").startswith("Clear filters")
    button.focus()
    page.keyboard.press("Enter")
    page.wait_for_function("location.hash === '#lvl=3'")
    page.wait_for_function(
        "w => JSON.stringify(__identify.total()) === JSON.stringify(w)",
        arg=want,
    )
    button.wait_for(state="hidden")
    assert page.evaluate("__identify.level()") == 3
    assert page.evaluate("document.activeElement.id") == "bwhat"
    seg = "[...document.querySelectorAll('.seg1 b, #qchips input')]"
    seg += ".map(e => e.checked ?? e.textContent)"
    assert page.evaluate(seg) == clean.evaluate(seg)  # the bar and the At risk, Invasive chips too
    assert page.errors == [] and clean.errors == []


def test_clear_filters_is_french(browser, site):
    base, _ = site
    page = ready(browser, base, "#groups=Aves&lvl=1")
    page.evaluate("I18N.set('lang', 'fr')")  # reloads in French
    page.wait_for_function(
        "document.getElementById('fclear').textContent === 'Effacer les filtres'"
    )
    assert page.get_attribute("#fclear", "aria-label").startswith("Effacer les filtres :")
    assert page.locator("#fclear").is_visible() and page.errors == []
