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


def test_the_page_works_without_the_model_file(browser, tmp_path):
    url = next(build_site(tmp_path, vlm=False))
    page = open_page(browser, url + HASH)
    assert page.locator("#cards li").count() == 10 and page.locator(".vlm").count() == 0
    assert page.errors == []


def test_pairs_the_field_already_names_come_after_the_model_studys_open_cards(
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
    assert ids == ["1", "200", "0"]  # 0's field names the pair, so iNaturalist has it: last
    assert page.errors == []


def test_a_part_link_draws_only_that_annotators_share(browser, base):
    page = open_page(browser, base + HASH.replace("#", "#part=2/2&"))
    ids = page.locator("#cards li > figure > a").evaluate_all(
        "a => a.map(x => +x.href.split('/').pop())"
    )
    assert ids and all(i % 2 == 1 for i in ids)
    assert page.locator("#cand").inner_text().startswith("Your share: part 2 of 2.")
    assert page.errors == []


def test_the_source_filter_keeps_one_source(browser, tmp_path, monkeypatch):
    obs = json.loads(json.dumps(foodweb_page.OBS))
    model = {**obs["obs"][0], "id": 200, "k": "model"}
    del model["f"]
    obs["obs"] = [obs["obs"][0], obs["obs"][1], model]
    monkeypatch.setattr(foodweb_page, "OBS", obs)
    monkeypatch.setattr(foodweb_page, "TEXT", {"fetched": "2026-11-13", "n": 0, "obs": []})
    monkeypatch.setattr(foodweb_page, "VLM", {"model": "t", "obs": {"200": {"p": 0.9, "prey": []}}})
    page = open_page(browser, next(build_site(tmp_path)) + HASH)
    page.locator("#sources button", has_text="Model study").click()
    ids = page.locator("#cards li > figure > a").evaluate_all(
        "a => a.map(x => x.href.split('/').pop())"
    )
    assert ids == ["200"] and page.errors == []


def _study_page(browser, tmp_path, monkeypatch):
    monkeypatch.setattr(foodweb_page, "VLM", {"model": "t", "obs": {"1": {"p": 0.99, "prey": []}}})
    return open_page(browser, next(build_site(tmp_path)) + HASH, study=True)


def test_a_study_card_is_blind_and_shows_the_six_options(browser, tmp_path, monkeypatch):
    page = _study_page(browser, tmp_path, monkeypatch)
    card = page.locator("#cards li").first
    assert card.locator("a").first.get_attribute("href").endswith("/observations/1")
    assert card.locator(".ask").inner_text() == "Is Barred Owl (Strix varia) eating something?"
    assert card.locator(".mk button b").all_inner_texts() == [
        "Predator not here",
        "Not eating",
        "Cannot tell",
        "Eating",
        "Eggs",
        "Carrion",
    ]
    assert card.locator(".mk button").nth(0).inner_text() == "1 Predator not here"
    third = card.locator(".mk button").nth(2)
    assert "cannot show whether it is eating prey" in third.get_attribute("title")
    assert third.get_attribute("aria-description") == third.get_attribute("title")
    assert "cannot show whether" not in third.inner_text()
    text = card.inner_text()
    assert "may be eating" not in text and "Why:" not in text
    assert card.locator(".vlm, .pbox, .pair").count() == 0 and page.errors == []


def test_key_6_saves_carrion_with_its_label_in_the_csv(browser, tmp_path, monkeypatch):
    page = _study_page(browser, tmp_path, monkeypatch)
    page.keyboard.press("6")
    rows = page.evaluate("FoodLoop.csv()").strip().split("\n")
    assert rows[0].endswith(",is_eating,label,model_p")
    assert rows[1].endswith('"yes","unsure","no","carrion","0.99"') and rows[1].startswith('"1",')
    assert page.errors == []


def test_key_4_on_a_study_card_opens_the_picker_with_no_guess(browser, tmp_path, monkeypatch):
    page = _study_page(browser, tmp_path, monkeypatch)
    page.keyboard.press("4")
    assert page.locator("#cards li").first.locator(".which input").input_value() == ""
    assert page.evaluate("FoodLoop.csv()").strip().count("\n") == 0  # not saved until Confirm
    assert page.errors == []


def test_study_mode_tucks_the_question_and_sections_2_and_4_away(browser, tmp_path, monkeypatch):
    page = _study_page(browser, tmp_path, monkeypatch)
    page.set_viewport_size({"width": 1400, "height": 900})
    assert "study" in page.evaluate("document.body.className")
    qf = page.locator("#qf")
    assert qf.evaluate("e => e.open") is False and page.locator("#modes").is_hidden()
    assert page.locator("#sources").is_visible() and page.locator("#export").is_visible()
    for sel in (".st2 details", ".st4 details"):
        assert page.locator(sel).evaluate("e => e.open") is False
    page.locator(".st2 summary").click()
    qf.locator("summary").click()
    assert page.locator("#mx").is_visible() and page.locator("#modes").is_visible()
    page.locator(".st2 summary").click()  # a study fold closes again, even on a wide screen
    assert page.locator(".st2 details").evaluate("e => e.open") is False
    assert page.errors == []


def test_leaving_study_mode_restores_the_layout(browser, tmp_path, monkeypatch):
    page = _study_page(browser, tmp_path, monkeypatch)
    page.set_viewport_size({"width": 1400, "height": 900})
    page.locator("#sources button", has_text="All sources").click()
    assert "study" not in page.evaluate("document.body.className")
    assert (
        page.locator("#qf").evaluate("e => e.open") is True and page.locator("#modes").is_visible()
    )
    assert page.locator(".st2 details").evaluate("e => e.open") is True
    assert page.locator("#export").evaluate("e => e.nextElementSibling.id") == "exportnet"
    assert page.locator("#classes").evaluate("e => e.nextElementSibling.id") == "sources"
    page.locator("#sources button", has_text="Model study").click()
    assert "study" in page.evaluate("document.body.className")
    assert page.errors == []


def test_a_study_card_shows_the_photo_beside_the_answers_and_stacks_on_a_phone(
    browser, tmp_path, monkeypatch
):
    page = _study_page(browser, tmp_path, monkeypatch)
    page.set_viewport_size({"width": 1400, "height": 900})

    def box(sel):
        return page.locator("#cards li").first.locator(sel).first.bounding_box()

    ph, mk = box("figure"), box(".mk")
    assert ph["x"] < mk["x"] and ph["width"] > 400
    page.set_viewport_size({"width": 390, "height": 844})
    ph, mk = box("figure"), box(".mk")
    assert mk["y"] > ph["y"] + ph["height"] - 1


def test_a_class_with_no_study_photos_names_the_filter_not_a_finish(browser, tmp_path, monkeypatch):
    page = _study_page(browser, tmp_path, monkeypatch)
    page.locator("#qf summary").click()
    page.locator("#classes button", has_text="Insects").click()
    assert page.locator("#qf summary").inner_text().endswith("Insects")
    assert page.inner_text("#cand").startswith("No photos left for this question.")
    assert page.errors == []
