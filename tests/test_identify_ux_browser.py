"""Identify's first-visit and failure paths in Chromium: photos that never load say so and retry,
a failed invasive lookup stays unknown, and the first-step line
under the bar. iNaturalist is stubbed."""

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib
from . import test_identify_www_browser as wb

browser = eb.browser
site = ib.site
CORS = {"access-control-allow-origin": "*"}
TIP_HEIGHT = (
    "document.addEventListener('DOMContentLoaded',"
    "()=>{window.__h=document.getElementById('first').offsetHeight;});"
)


def opened(browser, base, hash_="#lvl=3", fail=None, init=None):
    """ib.open_identify, except the observations answer 429 while fail["on"] is set."""
    page = browser.new_page(viewport={"width": 600, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    if init:
        page.add_init_script(init)
    page.route(ib.WTB, lambda r: r.abort())
    page.route(
        "https://api.inaturalist.org/v1/**", lambda r: r.fulfill(json={"results": []}, headers=CORS)
    )
    eb.stub_inat(page, None)

    def observations(route):
        if fail and fail["on"]:
            route.fulfill(status=429, headers=CORS)
        else:
            route.fallback()

    page.route("https://api.inaturalist.org/v1/observations*", observations)
    page.goto(f"{base}/identify.html{hash_}")
    page.wait_for_function("window.__identify")
    page.wait_for_selector("#grid .card", state="attached")
    return page


def test_photos_say_unavailable_when_inat_fails_and_retry_recovers(browser, site):
    base, _ = site
    fail = {"on": True}
    page = opened(browser, base, fail=fail)
    page.wait_for_function("document.querySelector('#grid .card .ph.bad')")
    assert page.locator("#grid .card .ph").first.inner_text().startswith("Photo unavailable")
    assert page.locator("#grid .card .ph:not(.bad)").count() == 0
    assert "Could not load the photos" in page.inner_text("#count")
    fail["on"] = False
    page.locator("#grid .card .ph.bad button").first.click()
    page.wait_for_selector("#grid .card .ph img")
    assert page.locator("#grid .card").first.locator(".ph img").count() == 1
    assert page.locator("#grid .card .ph.bad").count() > 0  # only the retried card asked again
    assert page.errors == []


def test_a_failed_invasive_lookup_stays_unknown_and_asks_again(browser, site):
    base, _ = site
    page = wb.open_row(browser, base, "#lvl=3&conf=all", meta=lambda m: {**m, "invasive": None})
    page.wait_for_function(wb.KINDS + "===2")
    asked = []

    def taxa(
        route,
    ):  # 403 fails at once; a 429 would first wait out the gate's own 5 s and 15 s retries
        asked.append(route.request.url)
        if len(asked) == 1:
            route.fulfill(status=403, headers=CORS)
        else:
            route.fallback()

    page.route("**/v1/taxa/**", taxa)
    page.get_by_role("checkbox", name="Introduced").check()
    page.wait_for_function(
        "/^Checking \\d+ species…$/.test(document.getElementById('count').textContent)"
    )
    page.wait_for_function("!document.getElementById('count').textContent.startsWith('Checking')")
    page.wait_for_function(wb.KINDS + "===1")  # the retry landed: Bombus b is the invasive one
    assert wb.looks(page) == {"Bombus b"} and len(asked) >= 2
    assert page.errors == []


def test_the_first_step_line_is_reserved_dismissible_and_french(browser, site):
    base, _ = site
    page = opened(browser, base, "", init=TIP_HEIGHT)
    tip = page.locator("#first")
    assert tip.inner_text().startswith("Pick a tab, then open a card")
    assert (
        page.evaluate("__h") == tip.evaluate("e => e.offsetHeight") > 0
    )  # no shift as the page fills in
    tip.get_by_role("button", name="Got it").click()
    assert page.locator("#first").count() == 0
    assert page.evaluate("localStorage.getItem('wtid-tip')") == "1"
    page.reload()
    page.wait_for_function("window.__identify")
    assert page.locator("#first").count() == 0  # dropped before first paint
    fr = opened(browser, base, "", init="localStorage.setItem('wtid-lang','fr');" + TIP_HEIGHT)
    assert fr.inner_text("#first").startswith("Choisissez un onglet")
    assert "Compris" in fr.inner_text("#first")
    assert fr.evaluate("__h") == fr.locator("#first").evaluate("e => e.offsetHeight")
