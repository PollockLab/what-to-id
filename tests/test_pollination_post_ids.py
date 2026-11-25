"""Posting an iNaturalist ID from the Pollination page's insect cards, with Identify's sign in"""

import json

import pytest

from what_to_id import page_eating, page_identify

from . import test_embeddings_browser as eb
from .foodweb_page import META, OBS, open_page, serve
from .test_pollination_page import POLLEN, POLLEN_OBS

browser = eb.browser
SESSION = {"jwt": "jwt", "user": {"id": 9, "login": "tester"}}
SIGNED_IN = f"sessionStorage.setItem('wtid-inat', '{json.dumps(SESSION)}')"


def config(html):
    return json.loads(html.split("var EATING_CONFIG=", 1)[1].split(";</script>", 1)[0])


def test_the_oauth_config_and_script_are_on_the_pollination_page_only():
    pollen = page_eating.render(kind="pollination")
    assert config(pollen)["oauth"] == {
        "client": page_identify.INAT_CLIENT_ID,
        "redirect": page_identify.INAT_REDIRECT,
    }
    assert "var IdentifyInat=" in pollen
    food = page_eating.render()
    assert "oauth" not in config(food) and "IdentifyInat=" not in food.split("var FoodLoop=")[0]


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("pollination-post")
    for name, data in (
        (page_eating.OBS_FILE, OBS),
        (page_eating.METAWEB_FILE, META),
        (page_eating.POLLINATION_OBS, POLLEN_OBS),
        (page_eating.POLLINATION_METAWEB, POLLEN),
    ):
        (root / name).write_text(json.dumps(data))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(page_identify, "INAT_CLIENT_ID", "test-client")
        assert page_eating.build(root)
    yield next(serve(root, "pollination.html"))


def mock_inat(page, posts):
    def ids(route):
        posts.append(json.loads(route.request.post_data))
        route.fulfill(json={"id": 1})

    page.route("https://api.inaturalist.org/v1/identifications", ids)
    page.route(
        "https://api.inaturalist.org/v1/taxa?*",
        lambda r: r.fulfill(json={"results": [{"id": 52775, "name": "Bombus vosnesenskii"}]}),
    )


def test_signed_out_cards_offer_sign_in_and_keep_the_links(browser, site):
    page = open_page(browser, site + "#q=does&x=Bombus%20mixtus&y=Rosa")
    page.wait_for_function("document.querySelectorAll('#cards > li').length > 0")
    card = page.locator("#cards > li").first
    assert card.locator("a.open").inner_text() == "Agree on iNaturalist"
    assert card.locator("button.lnk").inner_text() == "Sign in with iNaturalist"
    assert card.locator(".post").count() == 0 and page.errors == []


def test_a_narrow_card_posts_the_species_once(browser, site):
    page = open_page(browser, site, init=SIGNED_IN)
    posts = []
    mock_inat(page, posts)
    page.wait_for_function("document.querySelectorAll('#cards > li').length > 0")
    card = page.locator("#cards > li", has_text="Likely visitors of White Clover")
    assert card.locator("button.lnk").count() == 0
    b = card.locator(".lk li").first.locator(".post")
    assert b.inner_text() == "Post ID"
    b.click()
    page.wait_for_function(
        "[...document.querySelectorAll('.post')].some(b => b.textContent === 'Posted')"
    )
    assert b.is_disabled()
    b.click(force=True)
    page.wait_for_timeout(200)
    assert posts == [{"identification": {"observation_id": 1, "taxon_id": 52775}}]
    assert page.errors == []


def test_a_confirm_card_agrees_with_its_taxon(browser, site):
    page = open_page(browser, site + "#q=does&x=Bombus%20mixtus&y=Rosa", init=SIGNED_IN)
    posts = []
    mock_inat(page, posts)
    page.wait_for_function("document.querySelectorAll('#cards > li').length > 0")
    card = page.locator("#cards > li").first
    assert card.locator("a.open").inner_text() == "Open on iNaturalist"
    card.locator(".post", has_text="Agree").click()
    page.wait_for_function("document.querySelector('.post').textContent === 'Posted'")
    assert posts == [{"identification": {"observation_id": 4, "taxon_id": 4}}]


def test_the_food_web_page_has_no_post_or_sign_in(browser, site):
    page = open_page(browser, site.replace("pollination.html", "food-web.html"), init=SIGNED_IN)
    assert page.evaluate("typeof IdentifyInat") == "undefined"
    assert page.locator(".post").count() == 0
    assert "Sign in with iNaturalist" not in page.inner_text("body")
