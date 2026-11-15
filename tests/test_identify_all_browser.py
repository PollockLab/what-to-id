"""Identify's All needing ID tab (#lvl=all) in Chromium: every record of the pool, level 0 too,
newest first under the bar's filters; never the default tab and never in the Batches."""

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib

browser = eb.browser
site = ib.site


def test_all_needing_id_lists_the_whole_pool_newest_first_under_the_filters(browser, site):
    base, pts = site
    page = ib.open_identify(browser, base)
    page.wait_for_function("__identify.total()[6] > 0")
    assert page.evaluate("__identify.level()") == 1  # not the default
    assert page.evaluate("__identify.total()[6]") == len(pts)
    assert ib.tab(page, 6).locator("b").inner_text() == f"{len(pts):,}"
    ib.tab(page, 6).click()
    page.wait_for_selector("#grid .card")
    assert "lvl=all" in page.evaluate("location.hash")
    got = page.evaluate("__identify.view()[6]")
    assert got == sorted(pts["id"].tolist(), reverse=True)  # the base order: newest first
    zero = set(pts.loc[pts["level"] == 0, "id"])
    assert zero and zero <= set(got)
    assert page.is_hidden("#sortb") and page.is_hidden("#showall")
    page.click("#bwhat")
    page.locator("#groups .gb", has_text="Birds").first.click()
    birds = int((pts["iconic_taxon"] == "Aves").sum())
    page.wait_for_function(f"__identify.total()[6] === {birds}")
    assert len(page.evaluate("__identify.view()[6]")) == birds < len(pts)
    page.reload()  # the hash keeps the tab
    page.wait_for_function("window.__identify && __identify.total()[6] > 0")
    assert page.evaluate("__identify.level()") == 6
    assert page.get_attribute("#tab6", "aria-selected") == "true"
    assert page.errors == []
