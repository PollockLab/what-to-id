"""The Food web page's model hints (foodweb-vlm.json) in Chromium."""

import pytest

from . import test_embeddings_browser as eb
from .foodweb_page import build_site, open_page

browser = eb.browser
HASH = "#q=eats&x=Strix varia"


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    yield from build_site(tmp_path_factory.mktemp("eating-vlm-site"))


def test_a_card_with_a_model_hint_shows_the_model_line_and_the_prey_box(browser, base):
    page = open_page(browser, base + HASH)
    first = page.locator("#cards li").first
    assert (
        first.locator(".vlm").inner_text()
        == "Model: likely feeding (0.95) · prey guess: House Mouse"
    )
    style = first.locator(".pbox").get_attribute("style")
    assert style == "left: 10%; top: 20%; width: 50%; height: 60%;"
    assert page.locator(".vlm").count() == 1  # only the observation in the file


def test_the_page_works_without_the_model_file(browser, tmp_path):
    url = next(build_site(tmp_path, vlm=False))
    page = open_page(browser, url + HASH)
    assert page.locator("#cards li").count() == 10 and page.locator(".vlm").count() == 0
    assert page.errors == []
