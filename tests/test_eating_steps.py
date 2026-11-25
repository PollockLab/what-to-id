"""The Food web page's predator-class filter and three-step check (Chromium)."""

import copy
import csv
import json
from pathlib import Path

import pytest

from what_to_id import page_eating

from . import test_embeddings_browser as eb
from .foodweb_page import META, OBS, PH, TEXT, answer, open_page, serve

browser = eb.browser

# a mammal predator beside the owl: three Red Fox records eating a House Mouse
FOX = [
    {"id": 200 + i, "t": ["Vulpes vulpes", 8, "Red Fox"], "k": "eating", "c": 0, "q": "research",
     "on": "2026-02-01", "at": "BC", "ph": PH, "f": ["Mus musculus", 3]}
    for i in range(3)
]  # fmt: skip


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    root = tmp_path_factory.mktemp("steps-site")
    meta, obs = copy.deepcopy(META), copy.deepcopy(OBS)
    meta["pairs"].append(["Vulpes vulpes", "Mus musculus", 0.5])
    meta["common"]["Vulpes vulpes"] = "Red Fox"
    meta["parent"].update(
        {"Vulpes vulpes": "Canidae", "Canidae": "Carnivora", "Carnivora": "Mammalia"}
    )
    obs["obs"] += FOX
    for name, data in (("OBS_FILE", obs), ("METAWEB_FILE", meta), ("TEXT_FILE", TEXT)):
        (root / getattr(page_eating, name)).write_text(json.dumps(data))
    page_eating.build(root)
    yield from serve(root, "food-web.html")


def checked(page):
    return page.locator("#classes [aria-checked=true]").get_attribute("aria-label")


def test_the_class_filter_narrows_the_candidates_and_the_drawn_cards(browser, base):
    page = open_page(browser, base)
    assert checked(page) == "Predators of any class"
    assert page.get_by_role("radiogroup", name="Predator class").get_by_role("radio").count() == 6
    page.get_by_role("radio", name="Predators of any class").click()
    assert page.inner_text("#cand").startswith("19 candidate observations")
    page.get_by_role("radio", name="Mammals (Mammalia)").click()
    assert page.inner_text("#cand").startswith("3 candidate observations")
    page.click("#draw")
    cards = page.locator("#cards li .pair").all_inner_texts()
    assert len(cards) == 3 and all(c.startswith("Red Fox") for c in cards)
    page.get_by_role("radio", name="Birds (Aves)").click()
    assert page.inner_text("#cand").startswith("16 candidate observations")
    page.click("#draw")
    assert all(
        c.startswith("Barred Owl") for c in page.locator("#cards li .pair").all_inner_texts()
    )
    page.get_by_role("radio", name="Reptiles (Reptilia)").click()
    assert page.inner_text("#cand") == "No more observations for this question."
    assert page.locator("#draw").is_disabled() and page.errors == []


def test_the_class_filter_is_a_keyboard_radiogroup_and_is_remembered(browser, base):
    page = open_page(browser, base + "#q=eats&x=Strix varia")
    page.get_by_role("radio", name="Predators of any class").focus()
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")
    assert checked(page) == "Mammals (Mammalia)" and page.locator("#cards li").count() == 0
    assert page.inner_text("#cand") == "No more observations for this question."
    page.reload()
    page.wait_for_function("window.__food && window.__text")
    assert checked(page) == "Mammals (Mammalia)"
    assert page.locator("#classes [tabindex='0']").count() == 1 and page.errors == []


def test_marks_saved_before_the_three_checks_still_load(browser, base):
    ask = ["Strix varia", "Myodes"]
    ann = {
        "502": {"v": "yes", "on": "2026-01-02", "ask": ask, "pred": ask[0], "prey": ask[1]},
        "1": {"v": "no", "on": "2026-01-02", "ask": ["Strix varia", "Mus"]},
        "2": {"v": "unsure", "on": "2026-01-02", "ask": ["Strix varia", "Mus"]},
    }  # fmt: skip
    init = f"localStorage.setItem('wtid-loop',JSON.stringify({{budget:30,ann:{json.dumps(ann)}}}))"
    page = open_page(browser, base + "#q=eats&x=Strix varia", init)
    assert page.locator("#net line.e.new").count() == 1  # the old yes is a confirmed pair
    with page.expect_download() as d:
        page.click("#export")
    text = Path(d.value.path()).read_text().splitlines()
    rows = {r["observation_id"]: r for r in csv.DictReader(text)}
    steps = ("is_predator", "is_prey", "is_eating")
    assert [rows["502"][k] for k in steps] == ["yes"] * 3
    assert [rows["1"][k] for k in steps] == ["no"] * 3
    assert [rows["2"][k] for k in steps] == ["unsure"] * 3
    assert rows["502"]["answer"] == "yes" and page.errors == []


def test_the_four_options_save_the_three_checks_and_only_eating_shows_it(browser, base):
    page = open_page(browser, base + "#q=eats&x=Strix varia")
    while page.locator("#draw").is_enabled():
        page.click("#draw")
    card = page.locator("#cards li", has_text="Description mentions “myodes”")
    assert card.locator(".ask").inner_text() == "Is Barred Owl eating Myodes?"
    new = page.locator("#net line.e.new")

    def stored():
        return json.loads(page.evaluate("localStorage.getItem('wtid-loop')"))["ann"]["502"]

    answer(card, "Not eating")
    assert card.locator(".res").inner_text() == "Not visible"
    assert not card.locator(".which").is_visible() and new.count() == 0
    assert stored()["st"] == ["yes", "yes", "no"] and stored()["v"] == "no"
    answer(card, "Not this predator")
    assert card.locator(".res").inner_text() == "Not visible"
    assert not card.locator(".which").is_visible() and new.count() == 0 and stored()["v"] == "no"
    assert stored()["st"] == ["no", "unsure", "unsure"]
    answer(card, "Can’t tell")
    assert card.locator(".res").inner_text() == "Can’t tell" and new.count() == 0
    answer(card, "Eating")
    assert card.locator(".which").is_visible()
    card.locator(".which button", has_text="Confirm").click()
    assert new.count() == 1 and stored()["v"] == "yes"
    assert stored()["st"] == ["yes", "yes", "yes"]
    assert card.locator(".sum").inner_text() == "Predator: yes · Prey: yes · Eating: yes"
    with page.expect_download() as d:
        page.click("#export")
    line = [r for r in Path(d.value.path()).read_text().splitlines() if r.startswith('"502"')][0]
    assert line.endswith('"yes","yes","yes"') and page.errors == []


def test_keys_1_to_4_answer_the_current_card_with_one_press(browser, base):
    page = open_page(browser, base + "#q=eats&x=Strix varia")
    for k in "123":
        page.keyboard.press(k)
    res = page.locator("#cards .res").all_inner_texts()
    assert res[:3] == [
        "Not visible",
        "Not visible",
        "Can’t tell",
    ]  # card 1 saved no, unsure, unsure
    assert page.locator("#cards li.done").count() == 3
    page.keyboard.press("4")  # eating on a card whose field names a genus asks which prey
    assert page.locator("#cards li.cur .which").is_visible()
    assert page.errors == []
