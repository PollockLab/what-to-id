"""How it works in Chromium: the contents list every h2, a click scrolls and marks the section,
the filter hides terms that do not match, and the old anchors still resolve."""

import re

from what_to_id import terms_page
from what_to_id.glossary import GLOSSARY

from . import test_embeddings_browser as eb

browser = eb.browser
OLD_IDS = [*GLOSSARY, "study", "methods", "methods-eval", "identify", "taxonomy-about"]


def _page(browser, tmp_path, width=1440):
    path = terms_page.build(tmp_path)
    page = browser.new_page(viewport={"width": width, "height": 800})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.goto(path.as_uri())
    return page


def test_toc_lists_every_h2_and_a_click_marks_and_scrolls(browser, tmp_path):
    page = _page(browser, tmp_path)
    h2s = page.eval_on_selector_all("main h2", "els => els.map(e => e.id)")
    links = page.eval_on_selector_all("#toc a", "els => els.map(e => e.getAttribute('href'))")
    assert h2s[:3] == ["about", "how-each-view-works", "glossary"]
    assert h2s and all(f"#{i}" in links for i in h2s)
    assert page.is_visible("#toc a") and not page.is_visible("#toc summary")
    assert page.locator("#toc [aria-current]").count() <= 1
    assert page.locator("#toc a[href='#methods-eval'][aria-current]").count() == 0  # at the top
    page.click("#toc a[href='#methods-eval']")
    page.wait_for_function("document.querySelector('#toc a[href=\"#methods-eval\"]').ariaCurrent")
    assert page.evaluate("scrollY") > 500
    assert page.locator("#toc [aria-current]").count() == 1
    assert page.errors == []


def test_filter_hides_non_matching_terms_and_empty_groups(browser, tmp_path):
    page = _page(browser, tmp_path)
    total = page.locator("#glossary-list dt").count()
    assert total == len(GLOSSARY)
    page.fill("#find-q", "cosine")
    assert page.locator("#glossary-list dt:visible").count() >= 1
    assert page.is_hidden("#glossary-list dt#needs-id")
    assert page.locator("#glossary-list h3:visible").count() == 1
    assert re.match(r"\d+ of \d+ terms", page.inner_text("#find-n"))
    page.fill("#find-q", "")
    assert page.locator("#glossary-list dt:visible").count() == total


def test_phone_collapses_the_contents_and_old_anchors_resolve(browser, tmp_path):
    page = _page(browser, tmp_path, width=390)
    assert page.eval_on_selector("#toc", "e => e.open") is False
    top = page.eval_on_selector("#toc", "e => e.getBoundingClientRect().top")
    assert page.text_content("h1") == "How it works"
    assert page.locator("h1 + #toc").count() == 1
    assert top < page.eval_on_selector("#glossary", "e => e.getBoundingClientRect().top")
    assert page.is_visible("#toc summary") and not page.is_visible("#toc a")
    ids = set(page.eval_on_selector_all("[id]", "els => els.map(e => e.id)"))
    assert set(OLD_IDS) <= ids
    page.goto(page.url + "#needs-id")
    assert page.evaluate("document.querySelector(':target').id") == "needs-id"
    assert page.is_visible("dt#needs-id")
