"""The Food web page in Chromium (the four stages: question, matrix, evidence search, network)."""

import json
import re
from pathlib import Path

import pytest

from what_to_id import page_eating

from . import test_embeddings_browser as eb
from .foodweb_page import build_site, open_page

browser = eb.browser


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    yield from build_site(tmp_path_factory.mktemp("eating-site"))


def test_eating_html_redirects_to_the_food_web_page_with_its_hash(browser, base):
    page = browser.new_page()
    page.goto(base.replace("food-web", "eating") + "#q=eats&x=Strix")
    page.wait_for_url("**/food-web.html#q=eats&x=Strix")
    assert page.locator("h1").inner_text() == "Food web in BC"
    assert [a.inner_text() for a in page.locator("nav.site-nav a").all()].count("Food web") == 1


def test_the_survey_is_the_default_and_lists_pairs_in_the_matrix_and_network(browser, base):
    for hash_ in ("", "#q=survey"):
        page = open_page(browser, base + hash_)
        page.wait_for_selector("#mx table")
        assert page.locator("#mx td button").count() >= 4 and page.locator("#mx th").count() >= 3
        assert page.inner_text("#sent") == "What evidence is there for the BC food web?"
        assert page.locator("#modes button[aria-checked=true]").inner_text() == "Survey"
        assert (
            page.locator("#net line.e.before").count() >= 1
            and page.locator("#net text").count() >= 2
        )
        assert "Predicted from the expert food web" in page.inner_text("body")
        assert page.errors == []


def test_the_sentence_builder_updates_the_hash_and_the_slots(browser, base):
    page = open_page(browser, base)
    page.click("#modes [data-q=eats]")
    page.wait_for_function("location.hash.includes('x=Strix')")
    assert (
        page.inner_text("#sent").startswith("What does")
        and page.locator("#sent input").input_value() == "Barred Owl"
    )
    page.click("#modes [data-q=eaten]")
    page.wait_for_function("document.getElementById('sent').textContent.startsWith('What eats')")
    assert page.locator("#sent input").count() == 1
    page.click("#modes [data-q=does]")
    page.locator("#sent input").nth(1).wait_for()
    assert page.locator("#sent input").count() == 2 and page.inner_text("#sent").startswith("Does")
    assert page.locator("#modes [aria-checked=true]").count() == 1 and page.errors == []


def test_a_matrix_cell_click_asks_does_x_eat_y_and_highlights_the_cell(browser, base):
    page = open_page(browser, base)
    page.wait_for_selector("#mx td button")
    page.locator("#mx td button[aria-label*='Strix and House Mouse']").first.click()
    page.wait_for_selector("#mx td.sel")
    assert "x=Strix&y=Mus%20musculus" in page.evaluate("location.hash")
    assert page.locator("#mx td.sel").count() == 1 and page.locator("#mx td.sel.ev").count() == 1
    assert page.locator("#sent input").nth(1).input_value() == "House Mouse"
    assert page.inner_text("#netnote") == "Strix eating House Mouse: photographed before."
    assert page.errors == []


def draw_all(page):
    page.fill("#budget", "50")
    page.press("#budget", "Tab")
    page.click("#draw")


def test_the_example_chips_ask_the_questions_of_the_figure(browser, base):
    page = open_page(browser, base)
    page.click("#try button:has-text('Barred Owl')")
    page.wait_for_function("location.hash.includes('q=eats')")
    assert page.locator("#try button").count() == 1  # the frog and the crow are not in this metaweb


@pytest.mark.parametrize(
    "hash_, values",
    [
        ("#q=eats", ["Barred Owl"]),
        ("#q=eats&x=0", ["Barred Owl"]),
        ("#q=eats&x=nonsense", ["Barred Owl"]),
        ("#q=eats&x=1", ["Barred Owl"]),  # a taxon id
        ("#q=eats&x=barred owl", ["Barred Owl"]),  # a common name
        ("#q=eaten", ["House Mouse"]),
        ("#q=eaten&y=9999", ["House Mouse"]),
        ("#q=does", ["Barred Owl", "Myodes"]),
        ("#q=does&x=nonsense&y=3", ["Barred Owl", "House Mouse"]),
        ("#q=nonsense", []),
    ],
)
def test_a_blank_zero_or_unknown_taxon_falls_back_to_a_default_and_never_shows_zero(
    browser, base, hash_, values
):
    page = open_page(browser, base + hash_)
    page.wait_for_selector("#mx table")
    assert [i.input_value() for i in page.locator("#sent input").all()] == values
    assert "=0" not in page.evaluate("location.hash") and "=null" not in page.evaluate(
        "location.hash"
    )
    assert page.errors == []


def test_draw_ten_returns_at_most_ten_ranked_cards_and_spends_the_budget(browser, base):
    page = open_page(browser, base + "#q=eats&x=Strix varia")
    assert page.inner_text("#cand").startswith("6 candidate observations")  # 16, ten already drawn
    assert page.locator("#cards li").count() == 10 and page.inner_text("#used") == "10 used"
    assert page.get_attribute("#mbar", "aria-valuenow") == "10"
    assert page.inner_text("#draw") == "Draw ten more"
    first = page.locator("#cards li").first
    assert (
        "The field names the pair" in first.inner_text()
        and "Barred Owl eats House Mouse" in first.inner_text()
    )
    assert first.locator("button").all_inner_texts()[:3] == [
        "Shows it 1",
        "Not visible 2",
        "Can’t tell 3",
    ]
    assert (
        first.locator("a.open")
        .get_attribute("href")
        .startswith("https://www.inaturalist.org/observations/")
    )
    page.fill("#budget", "12")
    page.press("#budget", "Tab")
    page.click("#draw")
    assert page.locator("#cards li").count() == 12 and page.inner_text("#used") == "12 used"
    assert page.locator("#draw").is_disabled() and "Budget spent" in page.inner_text("#cand")
    assert page.errors == []


def test_why_drawn_names_the_text_that_mentions_a_candidate(browser, base):
    page = open_page(browser, base + "#q=eats&x=Strix varia")
    draw_all(page)
    why = " ".join(page.locator("#cards li").all_inner_texts())
    assert "Description mentions “mouse”" in why and "Description mentions “myodes”" in why
    assert "The field names Mus, not a species" in why
    page = open_page(browser, base + "#q=eaten&y=Myodes")
    assert page.locator("#cards li").count() >= 1
    assert page.errors == []


def test_shows_it_asks_which_prey_and_a_confirmed_pair_turns_its_edge_green(browser, base):
    page = open_page(browser, base + "#q=eats&x=Strix varia")
    assert (
        page.locator("#net line.e.new").count() == 0
        and page.locator("#net line.e.before").count() == 1
    )
    draw_all(page)
    card = page.locator("#cards li", has_text="Description mentions “myodes”")
    card.locator("button", has_text="Shows it").click()
    assert (
        card.locator(".which").is_visible()
        and card.locator(".which input").input_value() == "Myodes"
    )
    card.locator(".which button", has_text="Confirm").click()
    assert (
        page.locator("#net line.e.new").count() == 1
        and page.locator("#net line.e.before").count() == 1
    )
    assert card.locator(".res").inner_text() == "Shows it: Barred Owl eating Myodes"
    assert page.locator("#mx td.ev").count() >= 2
    stored = json.loads(page.evaluate("localStorage.getItem('wtid-loop')"))
    assert stored["ann"]["502"]["v"] == "yes" and stored["ann"]["502"]["prey"] == "Myodes"
    page.reload()
    page.wait_for_function("window.__food && window.__text")
    assert page.locator("#net line.e.new").count() == 1 and page.inner_text("#used") == "10 used"
    assert page.errors == []


def test_switching_to_the_survey_draws_nothing_and_each_question_has_its_own_budget(browser, base):
    page = open_page(browser, base + "#q=eats&x=Strix varia")
    assert page.inner_text("#used") == "10 used"
    page.get_by_role("radio", name="What evidence is there for the BC food web?").click()
    page.wait_for_function("document.querySelectorAll('#cards li').length==0")
    assert page.inner_text("#used") == "0 used"
    assert "Pick a species" in page.inner_text("#cand") and page.locator("#draw").is_enabled()
    page.evaluate("location.hash='#q=eats&x=Strix varia'")
    page.wait_for_function("document.querySelectorAll('#cards li').length==10")
    assert page.inner_text("#used") == "10 used" and "No more" not in page.inner_text("#cand")
    assert page.errors == []


def test_the_survey_draws_its_first_ten_on_load_only(browser, base):
    page = open_page(browser, base)
    assert page.locator("#cards li").count() > 0 and page.inner_text("#used") != "0 used"


def test_a_confirmed_mark_hands_off_to_inaturalist_with_a_copyable_name(browser, base):
    stub = (
        "Object.defineProperty(navigator,'clipboard',{configurable:true,"
        "value:{writeText:t=>window.__fail?Promise.reject():(window.__c=t,Promise.resolve())}})"
    )
    page = open_page(browser, base + "#q=eats&x=Strix varia", stub)
    draw_all(page)
    card = page.locator("#cards li", has_text="Description mentions “myodes”")
    assert not card.locator(".hand").is_visible() and card.locator("a.open").is_visible()
    card.locator("button", has_text="Shows it").click()
    card.locator(".which button", has_text="Confirm").click()
    assert card.locator(".hand").is_visible() and not card.locator("a.open").is_visible()
    link = card.locator(".hand a")
    assert link.inner_text() == "Add Eating = Myodes on iNaturalist"
    assert link.get_attribute("href") == "https://www.inaturalist.org/observations/502"
    assert link.get_attribute("target") == "_blank" and "noopener" in link.get_attribute("rel")
    assert "pick Eating" in card.locator(".hand .hint").inner_text()
    assert card.locator(".hand .cs").get_attribute("aria-live") == "polite"
    card.locator(".hand .cp").click()
    assert (
        card.locator(".hand .cs").inner_text() == "Copied"
        and page.evaluate("window.__c") == "Myodes"
    )
    page.evaluate(
        "Object.defineProperty(navigator,'clipboard',{value:{writeText:()=>Promise.reject()}})"
    )
    card.locator(".hand .cp").click()
    assert card.locator(".hand .cs").inner_text() == "Copy failed"
    stored = json.loads(page.evaluate("localStorage.getItem('wtid-loop')"))
    assert stored["ann"]["502"]["v"] == "yes"
    assert page.errors == []


def test_the_eaten_by_field_is_handed_off_when_the_unknown_is_the_predator(browser, base):
    page = open_page(browser, base + "#q=eaten&y=Mus musculus")
    card = page.locator("#cards li", has=page.locator("a[href$='/observations/99']"))
    card.locator("button", has_text="Shows it").click()
    assert card.locator(".hand a").inner_text() == "Add Eaten by = Barred Owl on iNaturalist"
    assert "pick Eaten by" in card.locator(".hand .hint").inner_text()
    assert page.errors == []


def test_the_question_modes_chips_and_keys_work_without_blocking(browser, base):
    page = open_page(browser, base)
    page.evaluate(
        "window.__worst=0;let l=performance.now();"
        "setInterval(()=>{const n=performance.now();"
        "window.__worst=Math.max(window.__worst,n-l-50);l=n},50)"
    )
    modes = page.get_by_role("radio")
    assert modes.all_inner_texts() == [
        "Survey",
        "X eats",
        "eats Y",
        "X eats Y",
    ]  # named by their longer labels
    page.locator("#try .chip").first.click()
    page.wait_for_function("document.querySelectorAll('#cards li').length>0")
    for k in "123":
        page.keyboard.press(k)
    assert page.locator("#cards li.done").count() == 3
    for name in [
        "What does X eat?",
        "What eats Y?",
        "Does X eat Y?",
        "What evidence is there for the BC food web?",
    ]:
        page.get_by_role("radio", name=name).click()
    assert page.evaluate("window.__worst") < 1000 and page.errors == []


def test_keys_annotate_and_move_the_current_card(browser, base):
    page = open_page(browser, base + "#q=eats&x=Strix varia")
    cards = page.locator("#cards li")
    assert "cur" in cards.nth(0).get_attribute("class")
    page.keyboard.press("2")
    assert cards.nth(0).locator(".res").inner_text() == "Not visible" and "cur" in cards.nth(
        1
    ).get_attribute("class")
    page.keyboard.press("j")
    assert "cur" in cards.nth(2).get_attribute("class")
    page.keyboard.press("k")
    page.keyboard.press("k")
    page.keyboard.press("3")
    assert cards.nth(0).locator(".res").inner_text() == "Can’t tell"
    assert page.locator("#net line.e.new").count() == 0 and page.errors == []


def test_export_is_a_csv_of_the_annotations(browser, base):
    page = open_page(browser, base + "#q=eats&x=Strix varia")
    page.keyboard.press("1")  # a field-named pair: no question, the pair is the answer
    page.keyboard.press("2")
    with page.expect_download() as d:
        page.click("#export")
    rows = Path(d.value.path()).read_text().splitlines()
    assert rows[0] == "observation_id,url,predator,prey,answer,date"
    assert len(rows) == 3 and rows[1].startswith('"0","https://www.inaturalist.org/observations/0"')
    assert '"Strix varia","Mus musculus","yes"' in rows[1] and rows[2].split(",")[4] == '"no"'
    assert page.errors == []


@pytest.mark.parametrize(
    "init",
    [
        "localStorage.setItem('wtid-loop','{not json')",
        "localStorage.setItem('wtid-loop','[1,2]')",
        "localStorage.setItem('wtid-loop',JSON.stringify({budget:'x',drawn:5,ann:7}))",
        "Storage.prototype.setItem=function(){throw new Error('quota')}",
        "Object.defineProperty(window,'localStorage',{get(){throw new Error('denied')}})",
    ],
)
def test_the_page_survives_unreadable_or_unwritable_storage(browser, base, init):
    page = open_page(browser, base + "#q=eats&x=Strix varia", init)
    assert page.input_value("#budget") == "30" and page.locator("#cards li").count() >= 1
    page.keyboard.press("2")
    assert page.locator("#cards .res", has_text="Not visible").count() == 1 and page.errors == []


def test_a_photo_that_does_not_load_leaves_a_link_not_alt_text(browser, base):
    page = open_page(browser, base + "#q=eats&x=Strix varia")
    page.evaluate("document.querySelector('#cards img').dispatchEvent(new Event('error'))")
    assert (
        page.locator("#cards li").first.locator(".nophoto").inner_text() == "Photo not shown here"
    )
    assert (
        page.locator("#cards li a")
        .first.get_attribute("href")
        .startswith("https://www.inaturalist.org/")
    )


def test_empty_states_are_written(browser, base):
    page = open_page(browser, base + "#q=does&x=Buteo&y=Myodes")
    assert page.inner_text("#cand") == "No more observations for this question."
    assert page.locator("#draw").is_disabled() and page.inner_text("#netnote").startswith(
        "Nothing found yet for Buteo"
    )


@pytest.mark.parametrize("hash_", ["", "#q=eats", "#q=eaten&y=3", "#q=does&x=1&y=3"])
def test_no_taxon_id_is_ever_visible(browser, base, hash_):
    page = open_page(browser, base + hash_)
    page.wait_for_selector("#mx table")
    text = page.inner_text("body") + " ".join(
        page.locator("#mx button, #net title, #sent input").evaluate_all(
            "es => es.map(e => (e.title || '') + ' ' + (e.value || ''))"
        )
    )
    text = re.sub(r"\d{4}-\d\d-\d\d", "", text)  # dates
    assert not re.search(r"\b\d{4,}\b", text), text
    assert page.errors == []


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


def test_the_page_is_the_food_web_tab(base):
    html = page_eating.render()
    assert (
        "<title>Food web:" in html
        and "<h1>Food web in BC</h1>" in html
        and not re.search(r"__[A-Z_]+__", html)
    )
    assert 'href="food-web.html" aria-current="page" data-optional' in html


def test_the_page_paints_before_the_food_word_file_arrives(browser, base):
    page = browser.new_page()
    held = []
    page.route("**/foodweb-text.json", lambda route: held.append(route))
    page.goto(base + "#q=eats&x=Strix varia")
    page.wait_for_function("window.__food")
    page.wait_for_selector("#mx table")
    assert page.evaluate("!window.__text") and page.inner_text("#cand").startswith("13 candidate")
    assert page.locator("#cards li").count() == 0  # nothing is drawn from a partial search
    held[0].continue_()
    page.wait_for_function("window.__text")
    assert page.locator("#cards li").count() == 10 and page.inner_text("#draw") == "Draw ten more"
    assert page.inner_text("#cand").startswith("6 candidate observations")


def test_the_food_word_file_does_not_block_the_main_thread(browser, base):
    page = browser.new_page()
    held = []
    page.route("**/foodweb-text.json", lambda route: held.append(route))
    page.goto(base)
    page.wait_for_function("window.__food")
    held[0].continue_()
    worst = page.evaluate(
        """async () => {
            let worst = 0, last = performance.now();
            while (!window.__text) {
                await new Promise(r => setTimeout(r, 0));
                const now = performance.now();
                worst = Math.max(worst, now - last);
                last = now;
            }
            return worst;
        }"""
    )
    assert worst < 1000
    assert page.evaluate("1") == 1


def test_the_matrix_has_a_legend_and_full_names_are_reachable(browser, base):
    page = open_page(browser, base + "#q=eats&x=Strix varia")
    assert "photographed in BC" in page.inner_text("#mxkey")
    assert page.get_attribute("#mx", "tabindex") == "0"
    assert page.locator("#mx th button").first.get_attribute("title")
    assert page.locator("#mx th.v button").first.inner_text() in ("House Mouse", "Myodes")
