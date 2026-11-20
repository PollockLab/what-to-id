"""The Food web page's taxon picker in Chromium (opens on groups, typing ranks, keys select)."""

import pytest

from . import test_embeddings_browser as eb
from .foodweb_page import build_site, open_page

browser = eb.browser


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    yield from build_site(tmp_path_factory.mktemp("picker-site"))


def rows(page):
    return page.locator("#sent .cb li[role=treeitem], #sent .cb li[role=option]")


def test_picker_opens_on_the_groups_with_counts_and_expands_in_place(browser, base):
    page = open_page(browser, base + "#q=eats&x=Strix")
    page.locator("#sent input").click()
    assert page.locator("#sent input").get_attribute("aria-expanded") == "true"
    assert page.locator("#sent ul").get_attribute("role") == "tree"
    assert rows(page).first.inner_text().split() == ["Birds", "2", "13"]
    assert rows(page).count() == 3  # Birds, its open path down to the pick, and the sibling
    page.locator("#sent .tri.o").first.click()  # collapse
    assert rows(page).count() == 1
    assert page.errors == []


def test_picker_typing_ranks_matches_and_the_keyboard_selects(browser, base):
    page = open_page(browser, base + "#q=eats&x=Strix")
    page.locator("#sent input").fill("stri")
    assert page.locator("#sent ul").get_attribute("role") == "listbox"
    assert rows(page).first.inner_text().split("\n")[0] == "Strix"
    page.locator("#sent input").fill("zzzz")
    assert (
        rows(page).count() == 0 and "No taxon matches" in page.locator("#sent .none").inner_text()
    )
    page.locator("#sent input").fill("buteo")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    page.wait_for_function("location.hash.includes('x=Buteo')")
    assert page.errors == []
