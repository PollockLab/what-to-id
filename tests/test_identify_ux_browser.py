"""Identify's first-visit and failure paths in Chromium: photos that never load say so and retry,
a failed invasive lookup stays unknown, and the first-step line
under the bar. iNaturalist is stubbed."""

from . import test_embeddings_browser as eb
from . import test_identify_browser as ib

browser = eb.browser
site = ib.site
CORS = {"access-control-allow-origin": "*"}


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
