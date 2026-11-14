"""Identify's What, When and Where row in Chromium: When writes the map filter's from=, Where
links to the map, At risk (from the map's list, no request) and Invasive (iNat's BC status) keep
level 3 cards by their suggestion. iNaturalist is stubbed."""

from urllib.parse import parse_qs, urlparse

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib
from .identify_sheets import reveal

browser = eb.browser
site = ib.site
KINDS = "new Set([...document.querySelectorAll('#grid .card .look i')].map(e=>e.textContent)).size"
IDS = {"Bombus a": 951, "Bombus b": 952, "Apis c": 953}


def open_row(browser, base, hash_):
    page = browser.new_page(viewport={"width": 600, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    eb.stub_inat(page, None)
    page.asked = []

    def taxa(route):
        url = route.request.url
        if "/v1/taxa?" in url:
            name = parse_qs(urlparse(url).query)["q"][0]
            photo = {"url": "https://static.inaturalist.org/photos/1/square.jpg"}
            body = {"results": [{"id": IDS[name], "name": name, "default_photo": photo}]}
        else:
            ids = [int(i) for i in url.split("/v1/taxa/")[1].split("?")[0].split(",")]
            page.asked.append((ids, parse_qs(urlparse(url).query)))
            bc = {"place": {"id": 7085}}
            body = {
                "results": [
                    {
                        "id": i,
                        "name": f"Taxon {i}",
                        "taxon_photos": [
                            {
                                "photo": {
                                    "url": f"https://static.inaturalist.org/photos/{i}/square.jpg"
                                }
                            }
                        ],
                        "conservation_status": {"status": "wrong"},
                        "conservation_statuses": [{**bc, "iucn": 40}] if i == 953 else [],
                        "establishment_means": {"establishment_means": "introduced", **bc}
                        if i == 952
                        else None,
                    }
                    for i in ids
                ]
            }
        route.fulfill(json=body, headers={"access-control-allow-origin": "*"})

    page.route("**/v1/taxa**", taxa)
    page.goto(f"{base}/identify.html{hash_}")
    page.wait_for_selector("#grid .card .look", state="attached")
    return page


def looks(page):
    return set(page.locator("#grid .card .look i").all_inner_texts())


def test_at_risk_and_invasive_keep_cards_by_their_suggestions_bc_status(browser, site):
    base, _ = site
    page = open_row(browser, base, "#lvl=3&conf=all")
    page.wait_for_function(KINDS + "===2")  # Bombus a never reaches level 3 here
    page.get_by_role("checkbox", name="At risk").check()
    page.wait_for_function("document.querySelectorAll('#grid .card').length>0")
    page.wait_for_function(
        "[...document.querySelectorAll('#grid .card .look i')].every(e=>e.textContent==='Apis c')"
    )
    assert "risk=1" in page.evaluate("location.hash") and page.asked == []
    page.get_by_role("checkbox", name="Invasive").check()
    page.wait_for_function(KINDS + "===2")
    assert looks(page) == {"Apis c", "Bombus b"}
    assert page.asked and all(
        len(ids) <= 30 and q["preferred_place_id"] == ["7085"] for ids, q in page.asked
    )
    page.get_by_role("checkbox", name="At risk").uncheck()
    page.wait_for_function(KINDS + "===1")
    assert looks(page) == {"Bombus b"}
    page.get_by_role("checkbox", name="Invasive").uncheck()
    page.wait_for_function(KINDS + "===2")
    assert "risk=" not in page.evaluate("location.hash") and page.errors == []


def test_a_category_tab_shows_one_group_and_keeps_the_order(browser, site):
    base, _ = site
    page = open_row(browser, base, "#lvl=3&conf=all")
    every = page.get_by_role("button", name="All", exact=True)
    assert every.get_attribute("aria-pressed") == "true"
    before = page.evaluate("__identify.ids()")
    tabs = page.locator("#cats .cat")
    for k in range(1, tabs.count()):
        tabs.nth(k).click()
        got = page.evaluate("__identify.ids()")
        if got and got != before:
            break
    tab = tabs.nth(k)
    assert tab.get_attribute("aria-pressed") == "true"
    assert page.locator("#cats [aria-pressed=true]").count() == 1
    assert "groups=" in page.evaluate("location.hash")
    assert page.inner_text("#bwhat b") == tab.inner_text().strip()
    kept = [i for i in before if i in set(got)]
    assert kept == [i for i in got if i in set(kept)]  # a tab filters, it never reorders
    tab.click()
    assert page.evaluate("__identify.ids()") == before
    assert "groups=" not in page.evaluate("location.hash")
    page.locator("#mix i").first.click()  # a strip segment picks its group like its tab
    assert page.locator("#cats [aria-pressed=true]").count() == 1
    assert (
        page.get_by_role("button", name="All", exact=True).get_attribute("aria-pressed") == "false"
    )
    assert "groups=" in page.evaluate("location.hash") and page.errors == []


def test_when_writes_the_map_filters_dates(browser, site):
    base, pts = site
    page = open_row(browser, base, "#lvl=3")
    page.click("#bwhen")
    page.locator("#presets button", has_text="Last 30 days").click()
    since = page.input_value("#from")  # a preset counts back from the data's last day
    assert f"from={since}" in page.evaluate("location.hash")
    want = {i for i, d in zip(pts["id"], ib.day(pts), strict=True) if d.date().isoformat() >= since}
    assert set(page.evaluate("__identify.ids()")) <= want
    page.locator("#presets button", has_text="All dates").click()
    assert "from=" not in page.evaluate("location.hash")
    page.keyboard.press("Escape")
    page.goto(f"{base}/identify.html#lvl=3&from=2026-08-05&to=2026-08-20")
    page.reload()
    page.wait_for_function("window.__identify")
    assert page.inner_text("#bwhen b") == "2026-08-05 to 2026-08-20" and page.errors == []


def test_by_species_runs_each_suggestion_together_under_one_header(browser, site):
    base, _ = site
    page = open_row(browser, base, "#lvl=3&conf=all&run=1")
    page.wait_for_selector("#grid .sep.run img", state="attached")
    names = page.locator("#grid .card .look i").all_inner_texts()
    blocks = [n for k, n in enumerate(names) if not k or names[k - 1] != n]
    assert len(blocks) == len(set(names)) and max(names.count(n) for n in names) > 3
    heads = page.locator("#grid .sep.run i").all_inner_texts()
    assert heads == blocks and page.locator("#grid .sep.run").first.locator("img").count() == 1
    assert "; all per suggested species)" in page.inner_text("#cap")
    reveal(page, "#frun input")
    page.get_by_role("switch", name="Group by suggested species").uncheck()
    page.wait_for_function("!document.querySelector('#grid .sep.run')")
    assert page.errors == []


def test_group_by_species_lives_in_sort_on_level_3_and_is_not_a_filter(browser, site):
    base, _ = site
    page = open_row(browser, base, "#lvl=3&conf=all")
    reveal(page, "#frun input")
    box = page.get_by_role("switch", name="Group by suggested species")
    box.check()
    page.wait_for_selector("#grid .sep.run", state="attached")
    assert "run=1" in page.evaluate("location.hash")
    assert page.text_content("#sorth") == "Prioritize"
    assert "grouped" in page.text_content("#sortb")
    page.keyboard.press("Escape")
    page.click("#tab1")
    page.wait_for_function("__identify.level() === 1")
    # Prioritize stays on every mode, the grouping is level 3 only
    assert not page.locator("#frun input").is_visible()
    assert page.errors == []


def test_progress_counts_cards_opened_today_and_a_logins_improving_ids(browser, site):
    base, _ = site
    page = browser.new_page(viewport={"width": 600, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.add_init_script("window.open = () => ({focus() {}});")
    eb.stub_inat(page, None)
    asked = []

    def ids(route):
        asked.append(parse_qs(urlparse(route.request.url).query))
        route.fulfill(json={"total_results": 4}, headers={"access-control-allow-origin": "*"})

    page.route("**/v1/identifications?*", ids)
    page.goto(f"{base}/identify.html#lvl=3&me=someone")
    page.wait_for_selector("#grid .card .look", state="attached")
    page.wait_for_function("document.getElementById('prog').textContent.includes('4/10')")
    q = asked[0]
    assert q["user_id"] == ["someone"] and q["category"] == ["improving"]
    assert q["own_observation"] == ["false"] and q["per_page"] == ["1"]
    assert "0 opened today" in page.inner_text("#prog")
    page.keyboard.press("j")
    page.keyboard.press("i")
    page.wait_for_function("document.getElementById('prog').textContent.includes('1 opened today')")
    page.reload()
    page.wait_for_selector("#grid .card .look", state="attached")
    assert "1 opened today" in page.inner_text("#prog") and len(asked) == 2  # cached
    assert page.errors == []


def test_only_level_3_fetches_the_runner_up_file_after_its_cards(browser, site):
    base, _ = site
    page = browser.new_page(viewport={"width": 600, "height": 900})
    eb.stub_inat(page, None)
    got = []
    page.on("request", lambda r: got.append(r.url))
    page.goto(f"{base}/identify.html#lvl=1")
    page.wait_for_selector("#grid .card")
    page.wait_for_timeout(500)
    assert not [u for u in got if "why" in u.rsplit("/", 1)[-1]]
    page.click("#tab3")
    page.wait_for_selector("#grid .card .why", state="attached")
    assert [u for u in got if "why" in u.rsplit("/", 1)[-1]]


def test_phones_name_the_dates_in_the_bar(browser, site):
    base, _ = site
    page = browser.new_page(viewport={"width": 390, "height": 800})
    eb.stub_inat(page, None)
    page.goto(f"{base}/identify.html#lvl=3&run=1&from=2026-08-10&to=2026-09-10")
    page.wait_for_function("document.querySelector('#sortb').textContent.includes('grouped')")
    page.wait_for_function(
        "document.querySelector('#bwhen b').textContent === '2026-08-10 to 2026-09-10'"
    )


def test_ten_improving_ids_turn_the_bar_green_with_the_oauth_link(browser, site):
    base, _ = site
    page = browser.new_page(viewport={"width": 600, "height": 900})
    eb.stub_inat(page, None)
    page.route(
        "**/v1/identifications?*",
        lambda r: r.fulfill(
            json={"total_results": 12}, headers={"access-control-allow-origin": "*"}
        ),
    )
    page.goto(f"{base}/identify.html#lvl=3&me=someone")
    link = page.locator("#prog a", has_text="OAuth ready")
    link.wait_for(state="attached")
    assert link.get_attribute("href") == "https://www.inaturalist.org/oauth/app_owner_application"
    assert "ok" in page.get_attribute("#prog", "class") and "12/10" in page.text_content("#prog")
    assert page.inner_text("#today") == "12 of 10 improving IDs today"  # the line beside the cards
    assert "ok" in page.get_attribute("#today", "class")
