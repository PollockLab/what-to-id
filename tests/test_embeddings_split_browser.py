"""Photo-space page in Chromium: the split page that relays the selection between its frames.

Fixtures and helpers live in test_embeddings_browser.py.
"""

import pytest

from . import test_embeddings_browser as eb
from .test_embeddings_browser import stub_inat

browser, site = eb.browser, eb.site


def test_split_page_relays_the_selection_between_frames_without_reloads(browser, site):
    base, *_ = site
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    stub_inat(page, None)
    page.goto(f"{base}/split.html?view=side#months=8")
    counts = (
        "[...document.querySelectorAll('iframe')].map(f => f.contentDocument &&"
        " f.contentDocument.getElementById('count') &&"
        " f.contentDocument.getElementById('count').textContent)"
    )
    page.wait_for_function(f"{counts}.every(c => c && c.includes('shown'))")
    left, right = page.frame_locator("#map"), page.frame_locator("#space")
    before = left.locator("#count").inner_text()
    assert before == right.locator("#count").inner_text()
    for f in ("#map", "#space"):
        page.evaluate(f"document.querySelector('{f}').contentWindow.marker = 1")
    left.locator("#groups button[data-g='1']").click()  # pick Insecta in the left frame
    page.wait_for_function(f"{counts}.every(c => c !== {before!r}) && new Set({counts}).size === 1")
    assert "groups=Insecta" in page.evaluate("location.hash")
    assert right.locator("#selbar li", has_text="Insecta").count() == 1
    for f in ("#map", "#space"):
        assert page.evaluate(f"document.querySelector('{f}').contentWindow.marker") == 1
    assert page.errors == []
    page.close()


def test_split_page_mirrors_a_picked_record_in_the_other_frame(browser, site):
    # the fixture loads the photo space in both frames, so this pins the relay, not map.js
    base, *_ = site
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    stub_inat(page, None)
    page.goto(f"{base}/split.html?view=side")
    page.wait_for_function(
        "[...document.querySelectorAll('iframe')].every(f =>"
        " f.contentDocument.getElementById('count').textContent.includes('shown'))"
    )
    pick = [f for f in page.frames if "embed=1" in f.url]
    assert len(pick) == 2
    pick[1].evaluate(
        "window.got = []; addEventListener('message', e =>"
        " e.data.type === 'wtid-matches' && got.push(e.data))"
    )
    pick[0].evaluate("__deck.props.onClick({index: 7, layer: {id: 'pts'}})")
    sel = "__deck.props.layers.find(x => x.id === 'sel').props.data[0]"
    for f in pick:
        f.wait_for_function("__deck.props.layers.some(x => x.id === 'sel')")
        assert f.evaluate(sel) == 7
    pick[0].wait_for_selector(".nbrs li .score")
    assert pick[0].locator(".nbrs li .score").first.inner_text().startswith("Cosine 0.")
    assert pick[0].locator(".nbrs li .rank").first.inner_text() == "1"
    pick[1].wait_for_function("got.length === 1")  # the matches reached the other frame
    hits = pick[1].evaluate("got[0].hits")
    assert len(hits) == 12 and all(0 <= h["score"] <= 1 for h in hits)
    assert [h["score"] for h in hits] == sorted((h["score"] for h in hits), reverse=True)
    pick[1].evaluate("document.querySelector('#card .x').click()")
    for f in pick:
        f.wait_for_function("!__deck.props.layers.some(x => x.id === 'sel')")
    assert page.errors == []
    page.close()


def test_split_photo_search_narrows_both_frames_and_the_chip_clears_it(browser, site):
    base, _, pool, _ = site
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    stub_inat(page, None)
    page.goto(f"{base}/split.html?view=side")
    counts = (
        "[...document.querySelectorAll('iframe')].map(f => f.contentDocument &&"
        " f.contentDocument.getElementById('count') &&"
        " f.contentDocument.getElementById('count').textContent)"
    )
    page.wait_for_function(f"{counts}.every(c => c && c.includes('shown'))")
    before = page.evaluate(counts)
    seed = int(sorted(pool)[0])
    page.fill("#sq", f"https://www.inaturalist.org/observations/{seed}")
    page.press("#sq", "Enter")
    chip = "#selbar li:has-text('Photo search')"
    for f in ("#map", "#space"):
        page.frame_locator(f).locator(chip).wait_for(state="attached")  # the peer folds its panel
    now = page.evaluate(counts)
    num = [int(c.split(" ")[0].replace(",", "")) for c in (*now, *before)]
    assert 0 < num[0] == num[1] < num[2] == num[3]
    page.frame_locator("#map").locator(chip + " button").click()
    for f in ("#map", "#space"):
        page.frame_locator(f).locator(chip).wait_for(state="detached")
    page.wait_for_function(f"{counts}.every(c => c === {before[0]!r})")
    assert page.input_value("#sq") == ""
    assert page.errors == []
    page.close()


def test_split_divider_resizes_by_keys_and_double_click_and_remembers(browser, site):
    base, *_ = site
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(f"{base}/split.html?view=side")
    width = "document.getElementById('map').getBoundingClientRect().width"
    page.wait_for_selector("#map")
    half = page.evaluate(width)
    sep = page.locator("#sep")
    sep.focus()
    for _ in range(5):
        page.keyboard.press("ArrowRight")
    assert page.evaluate(width) == pytest.approx(half + 0.1 * 1280, abs=3)
    page.reload()
    page.wait_for_selector("#map")
    assert page.evaluate(width) > half + 100  # remembered
    sep.dblclick()
    assert page.evaluate(width) == pytest.approx(half, abs=3)
    page.close()


def _split(browser, site, w, h, query="", hash_=""):
    base, *_ = site
    page = browser.new_page(viewport={"width": w, "height": h})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    stub_inat(page, None)
    page.goto(f"{base}/split.html{query}{hash_}")
    return page


FRAMES = "[...document.querySelectorAll('iframe')].filter(f => !f.hidden).map(f => f.id)"


def test_split_opens_the_map_and_the_tree_and_switches_views(browser, site):
    page = _split(browser, site, 1280, 800)
    assert page.evaluate(FRAMES) == ["map", "tree"]
    assert page.locator("[data-v=tree]").get_attribute("aria-pressed") == "true"
    assert page.inner_text(".seg") == "Map + photos\nMap\nPhotos\nMap + tree"  # names its panes
    page.click("[data-v=space]")
    page.wait_for_function(f"{FRAMES}.join() === 'space'")
    assert "view=space" in page.evaluate("location.search")
    page.click("[data-v=side]")
    page.wait_for_function(f"{FRAMES}.join() === 'map,space'")
    page.close()


def test_split_has_one_header_and_the_note_behind_an_i_button(browser, site):
    page = _split(browser, site, 1280, 800, "?view=side")
    page.wait_for_function(f"{FRAMES}.length === 2")
    assert page.locator(".site-shell:visible").count() == 1
    for f in ("#map", "#space"):
        shell = page.frame_locator(f).locator(".site-shell")
        assert shell.count() == 0 or not shell.is_visible()
    assert page.locator("#note").is_hidden()
    page.click("#i")
    assert page.locator("#note").is_visible() and "share one selection" in page.inner_text("#note")
    page.keyboard.press("Escape")
    assert page.locator("#note").is_hidden()
    assert page.errors == []
    page.close()


def test_a_phone_holds_one_frame_at_a_time(browser, site):
    page = _split(browser, site, 390, 800, hash_="#months=8")
    assert page.evaluate("[...document.querySelectorAll('iframe')].map(f => f.id)") == ["tree"]
    assert page.locator("[data-v=side]").is_hidden()
    assert page.inner_text("[data-v=tree]") == "Tree"  # one pane at a time, so no pair to name
    page.click("[data-v=space]")
    page.wait_for_function(
        "document.querySelectorAll('iframe').length === 1 && document.querySelector('#space')"
    )
    assert "months=8" in page.evaluate("document.querySelector('#space').src")
    page.close()


def test_old_page_urls_open_the_matching_explore_view_with_the_hash(browser, site):
    base, *_ = site
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    stub_inat(page, None)
    page.goto(f"{base}/embeddings.html#months=8")
    page.wait_for_url(f"{base}/split.html?view=space#months=8")
    assert page.evaluate(FRAMES) == ["space"]
    page.close()
