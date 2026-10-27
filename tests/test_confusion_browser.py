"""The confused-pairs page in Chromium, photo hosts stubbed: group tabs, a pair's records worst
first, the tree's #t<id> link, the Identify handoff, keys and seen marks, the pairs-only build."""

import pytest

from what_to_id import page_confusion

from . import test_embeddings_browser as eb
from .test_atlas_search_browser import PNG
from .test_page_confusion import pairs_frame, records_frame
from .test_tree_browser import serve

browser = eb.browser
OBS = "https://www.inaturalist.org/observations/"


def site_for(tmp_path_factory, records):
    root = tmp_path_factory.mktemp("confusion-site")
    pq, rq = root / "c.parquet", root / "r.parquet"
    pairs_frame().to_parquet(pq)
    if records:
        records_frame().to_parquet(rq)
    page_confusion.build(root, None, pq, rq if records else None)
    server, url = serve(root)
    yield url
    server.shutdown()


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    yield from site_for(tmp_path_factory, True)


@pytest.fixture(scope="module")
def pairs_site(tmp_path_factory):
    yield from site_for(tmp_path_factory, False)


def open_page(browser, url, hash_="", w=1280):
    page = browser.new_page(viewport={"width": w, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    for host in (
        "https://inaturalist-open-data.s3.amazonaws.com/**",
        "https://static.inaturalist.org/**",
    ):
        page.route(host, lambda r: r.fulfill(body=PNG, content_type="image/png"))
    page.goto(f"{url}/confusion.html{hash_}")
    page.wait_for_selector("#pairs .pair")
    return page


def obs_links(page):
    return page.locator("#cards a.obs").evaluate_all("as => as.map(a => a.href)")


def test_tabs_filter_the_pairs(browser, site):
    page = open_page(browser, site)
    assert page.locator("#pairs .pair").count() == 3
    assert page.locator("#tabs button").all_inner_texts() == ["All 6", "Plantae 4", "Fungi 2"]
    assert page.locator("#caveat").is_hidden()
    page.get_by_role("button", name="Fungi, 2 records").click()
    assert page.locator("#pairs .pair").all_inner_texts() == [
        "Labelled Eus fus → looks like Cus dus\n9 photos, 75% of its photos"
    ]
    assert page.locator("#caveat").is_visible()
    page.get_by_role("button", name="Plantae, 4 records").click()
    assert page.locator("#pairs .pair i").all_inner_texts() == [
        "Aus bus",
        "Gus hus",
        "Aus bus",
        "Cus dus",
    ]
    assert "g=Plantae" in page.url and page.errors == []


def test_a_pair_shows_its_records_worst_first(browser, site):
    page = open_page(browser, site)
    page.locator("#pairs .pair", has_text="Cus dus").filter(has_text="Aus bus").click()
    assert obs_links(page) == [OBS + "103", OBS + "101"]
    assert (
        page.locator("#cards img").evaluate_all("a => a.map(i => i.alt)")
        == ["labelled Aus bus"] * 2
    )
    assert page.locator("#cards img").first.get_attribute("loading") == "lazy"
    assert page.locator("#rec-title").inner_text() == "Labelled Aus bus → looks like Cus dus"
    assert "2 records of its 3 photos" in page.locator("#rec-sub").inner_text()
    assert page.locator("#pairs .pair[aria-pressed=true]").count() == 1
    assert "t=1&l=2" in page.url and page.errors == []


def test_tree_link_opens_the_species_first_pair(browser, site):
    page = open_page(browser, site, "#t7")
    page.wait_for_selector("#cards .card")
    assert obs_links(page) == [OBS + "201", OBS + "202"]
    assert (
        page.locator("#pairs .pair[aria-pressed=true]").inner_text().startswith("Labelled Eus fus")
    )
    assert page.url.endswith("#t=7&l=2")
    assert page.locator("#caveat").is_visible()  # Eus fus is a fungus


def test_identify_link_carries_the_selected_ids(browser, site):
    page = open_page(browser, site, "#t=1&l=2")
    ident = page.locator("#act a.identify")
    assert ident.inner_text() == "Identify these 2"
    assert ident.get_attribute("href").endswith("&id=103,101")
    page.get_by_label("Include observation 101 in Identify").uncheck()
    assert ident.inner_text() == "Identify these 1"
    assert ident.get_attribute("href").endswith("&id=103")
    all_ = page.locator("#act a.all")
    assert all_.inner_text() == "Identify all of Aus bus"
    assert "taxon_id=1&place_id=7085&quality_grade=needs_id" in all_.get_attribute("href")


def test_search_picks_a_species_across_its_pairs(browser, site):
    page = open_page(browser, site)
    page.fill("#q", "Aus bus")
    page.press("#q", "Enter")
    page.wait_for_selector("#cards .card")
    assert obs_links(page) == [OBS + str(i) for i in (102, 103, 104, 101)]
    assert page.locator("#cards .card").nth(2).inner_text().startswith("No photo")
    page.fill("#q", "Gus hus")
    page.press("#q", "Enter")
    assert page.locator("#rec-title").inner_text() == "Records that look like Gus hus"
    assert obs_links(page) == [OBS + "102", OBS + "104"]


def test_keys_move_between_cards_and_mark_them_seen(browser, site):
    page = open_page(browser, site, "#t=1&l=2")
    page.context.route("https://www.inaturalist.org/**", lambda r: r.fulfill(body="ok"))
    page.keyboard.press("j")
    page.keyboard.press("j")
    assert page.evaluate("document.activeElement.dataset.id") == "101"
    page.keyboard.press("k")
    with page.context.expect_page() as popup:
        page.keyboard.press("Enter")
    assert popup.value.url == OBS + "103"
    assert page.locator("#cards .card.seen").count() == 1
    page.reload()
    page.wait_for_selector("#cards .card.seen")
    assert page.locator("#cards .card.seen").get_attribute("data-id") == "103"


def test_phone_width_stacks_the_columns(browser, site):
    page = open_page(browser, site, "#t=1&l=2", w=375)
    assert page.evaluate("document.documentElement.scrollWidth") <= 375
    pairs, cards = (page.locator(s).bounding_box() for s in ("#pairs-col", "#records"))
    assert cards["y"] >= pairs["y"] + pairs["height"]


def test_pairs_only_build_renders(browser, pairs_site):
    page = open_page(browser, pairs_site)
    assert page.locator("#pairs .pair").count() == 3
    assert page.locator("#norecords").is_visible()
    assert page.locator("#tabs button").all_inner_texts() == ["All"]
    page.locator("#pairs .pair").first.click()
    assert page.locator("#rec-sub").inner_text() == "Per-record rows arrive with the next build."
    assert page.locator("#cards .card").count() == 0
    assert page.locator("#act a.all").inner_text() == "Identify all of Eus fus"
    assert page.errors == []


def pair_names(page):
    return page.locator("#pairs .pair").evaluate_all(
        "bs => bs.map(b => b.innerText.split('\\n')[0].replace('Labelled ', ''))"
    )


def test_sort_by_share_flips_and_rides_the_hash(browser, site):
    page = open_page(browser, site)
    default = pair_names(page)
    assert page.locator("#sort").input_value() == "" and "sort=" not in page.url
    page.select_option("#sort", "pct")
    shares = page.locator("#pairs .sub").all_inner_texts()
    assert [s.split(", ")[1] for s in shares] == [
        "30% of its photos",
        "50% of its photos",
        "75% of its photos",
    ]
    assert "sort=pct" in page.url and "dir=" not in page.url
    page.click("#dir")
    assert page.locator("#dir").get_attribute("aria-label") == "Sort direction: descending"
    assert [s.split(", ")[1][:3] for s in page.locator("#pairs .sub").all_inner_texts()] == [
        "75%",
        "50%",
        "30%",
    ]
    assert "sort=pct&dir=desc" in page.url
    page.select_option("#sort", "")
    page.click("#dir")
    assert pair_names(page) == default and "sort=" not in page.url and "dir=" not in page.url
    page.select_option("#sort", "lab")
    assert pair_names(page)[0].startswith("Aus bus")
    page.select_option("#sort", "n")
    assert [s.split(" ")[0] for s in page.locator("#pairs .sub").all_inner_texts()] == [
        "3",
        "5",
        "9",
    ]
    assert page.errors == []


def test_sort_and_range_restore_from_the_hash(browser, site):
    page = open_page(browser, site, "#sort=pct&dir=desc&min=40&max=75")
    assert page.locator("#sort").input_value() == "pct"
    assert page.locator("#lo").input_value() == "40" and page.locator("#hi").input_value() == "75"
    assert [s.split(", ")[1][:3] for s in page.locator("#pairs .sub").all_inner_texts()] == [
        "75%",
        "50%",
    ]


def test_range_filter_hides_pairs_outside_the_bounds(browser, site):
    page = open_page(browser, site)
    assert (page.locator("#lo").input_value(), page.locator("#hi").input_value()) == ("0", "100")
    assert page.locator("#pairs .pair").count() == 3 and "min=" not in page.url
    page.fill("#lo", "50")
    page.press("#lo", "Enter")
    assert page.locator("#pairs .pair").count() == 2  # 50 is inclusive
    assert page.locator("#status").inner_text() == "2 pairs from 50% to 100%"
    assert "min=50" in page.url and "max=" not in page.url
    page.fill("#hi", "74")
    page.press("#hi", "Enter")
    assert page.locator("#pairs .pair").count() == 1
    page.fill("#hi", "75")
    page.press("#hi", "Enter")
    assert page.locator("#pairs .pair").count() == 2  # 75 is inclusive
    page.fill("#lo", "76")
    page.press("#lo", "Enter")
    assert page.locator("#pairs .pair").count() == 0
    assert page.locator("#status").inner_text() == "0 pairs from 76% to 75%"
    page.fill("#lo", "0")
    page.fill("#hi", "100")
    page.press("#hi", "Enter")
    assert page.locator("#pairs .pair").count() == 3
    assert "min=" not in page.url and "max=" not in page.url and page.errors == []
    page.fill("#hi", "250")  # out of range: the bound stays
    page.press("#hi", "Enter")
    assert page.locator("#hi").input_value() == "100"
