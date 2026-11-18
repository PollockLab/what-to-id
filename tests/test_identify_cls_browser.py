"""Identify's rows hold the height they fill, so a phone that runs the page's script late does not
see the rows below them drop when the tabs and chips arrive. iNaturalist is stubbed."""

import pytest

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib

browser = eb.browser
site = ib.site

HEIGHTS = "['tabs','qchips'].map(i=>document.getElementById(i).getBoundingClientRect().height)"


@pytest.mark.parametrize("size", [(390, 844), (1280, 800)])
def test_the_empty_tabs_and_chips_are_as_tall_as_the_filled_ones(browser, site, size):
    page = ib.open_identify(browser, site[0], "#lvl=3&sort=conf", size=size, touch=size[0] < 600)
    page.wait_for_selector("#tabs .tab .cut", state="attached")
    page.wait_for_selector("#qchips .qchip", state="attached")
    filled = page.evaluate(HEIGHTS)
    assert min(filled) > 20  # a real tab row and a real chip row
    page.evaluate(
        "tabs.replaceChildren();qchips.replaceChildren()"
    )  # the page before its script ran
    empty = page.evaluate(HEIGHTS)
    assert empty == pytest.approx(filled, abs=1)
    page.close()
