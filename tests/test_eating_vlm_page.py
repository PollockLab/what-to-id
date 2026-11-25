"""The Food web page's model hints (foodweb-vlm.json) in Chromium."""

import json

import pytest

from . import foodweb_page
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
    assert first.locator(".vlm").inner_text() == "Very likely feeding · prey guess: House Mouse"
    assert first.locator(".vlm").get_attribute("title") == "Model P(feeding) 0.95"
    assert first.locator(".vbar i").get_attribute("style") == "width: 95%;"
    assert (
        first.locator("> div > :first-child").get_attribute("class") == "evl vlm"
    )  # the first line
    style = first.locator(".pbox").get_attribute("style")
    assert style == "left: 10%; top: 20%; width: 50%; height: 60%;"
    assert page.locator(".vlm").count() == 1  # only the observation in the file


def test_the_page_works_without_the_model_file(browser, tmp_path):
    url = next(build_site(tmp_path, vlm=False))
    page = open_page(browser, url + HASH)
    assert page.locator("#cards li").count() == 10 and page.locator(".vlm").count() == 0
    assert page.errors == []


def test_cards_rank_by_the_models_signal_and_model_only_cards_follow_the_field(
    browser, tmp_path, monkeypatch
):
    obs = json.loads(json.dumps(foodweb_page.OBS))
    model = {**obs["obs"][0], "id": 200, "k": "model"}
    del model["f"]
    obs["obs"] = [obs["obs"][0], obs["obs"][1], model]
    hints = {
        "0": {"p": 0.2, "prey": []},
        "1": {"p": 0.99, "prey": []},
        "200": {"p": 0.99, "prey": []},
    }
    monkeypatch.setattr(foodweb_page, "OBS", obs)
    monkeypatch.setattr(foodweb_page, "TEXT", {"fetched": "2026-11-13", "n": 0, "obs": []})
    monkeypatch.setattr(foodweb_page, "VLM", {"model": "t", "obs": hints})
    page = open_page(browser, next(build_site(tmp_path)) + HASH)
    ids = page.locator("#cards li > figure > a").evaluate_all(
        "a => a.map(x => x.href.split('/').pop())"
    )
    assert ids == [
        "1",
        "0",
        "200",
    ]  # 1 rises on the model, 0 sinks but stays above the model-only card
    assert page.errors == []


def test_the_prey_picker_starts_on_the_models_guess_with_a_copyable_eating_value(
    browser, tmp_path, monkeypatch
):
    stub = (
        "Object.defineProperty(navigator,'clipboard',{configurable:true,"
        "value:{writeText:t=>(window.__c=t,Promise.resolve())}})"
    )
    hints = {
        "1": {"p": 0.99, "prey": [["Mus musculus", 0.6]]}
    }  # card 1's field names only the genus Mus
    monkeypatch.setattr(foodweb_page, "VLM", {"model": "t", "obs": hints})
    page = open_page(browser, next(build_site(tmp_path)) + HASH, stub)
    card = page.locator("#cards li").first
    assert card.locator("a").first.get_attribute("href").endswith("/observations/1")
    page.keyboard.press("4")
    assert card.locator(".which input").input_value() == "House Mouse"
    assert card.locator(".which .ev").inner_text() == "Eating = House Mouse"
    card.locator(".which .cp").click()
    assert page.evaluate("window.__c") == "House Mouse"
    assert card.locator(".which .cs").inner_text() == "Copied" and page.errors == []


def test_a_model_card_names_the_models_guess_a_group_or_something(browser, tmp_path, monkeypatch):
    obs = json.loads(json.dumps(foodweb_page.OBS))
    model = {**obs["obs"][0], "id": 200, "k": "model"}
    del model["f"]
    obs["obs"] = [{**model, "id": i} for i in (200, 201, 202)]
    hints = {
        "200": {"p": 0.9, "name": "Mus musculus", "prey": []},  # a taxon
        "201": {"p": 0.9, "name": "mouse", "prey": []},  # a word with no group
        "202": {"p": 0.9, "name": "rodent", "prey": [["Mus", 0.4]]},  # a genus in the metaweb
    }
    monkeypatch.setattr(foodweb_page, "OBS", obs)
    monkeypatch.setattr(foodweb_page, "TEXT", {"fetched": "2026-11-13", "n": 0, "obs": []})
    monkeypatch.setattr(foodweb_page, "VLM", {"model": "t", "obs": hints})
    page = open_page(browser, next(build_site(tmp_path)) + HASH)
    cards = {
        i: page.locator("#cards li", has=page.locator(f"a[href$='/observations/{i}']")).inner_text()
        for i in (200, 201, 202)
    }
    assert "Barred Owl may be eating House Mouse" in cards[200]
    assert "Barred Owl may be eating something" in cards[201]
    assert "Barred Owl may be eating Mus" in cards[202] and page.errors == []
