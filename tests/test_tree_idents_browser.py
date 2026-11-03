"""The tree card's identifier count in Chromium: how many people identify the selected taxon in BC
and the needs-ID backlog each carries, read from api.inaturalist.org's total_results alone."""

from urllib.parse import parse_qs, urlparse

from . import test_tree_browser as tb

browser = tb.browser
site = tb.site
CORS = {"access-control-allow-origin": "*"}
LOGIN = "secretlogin"


def open_tree(browser, site, answers):
    """The tree on Genus A, identifiers answered by answers(route, n), n counting requests."""
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.errors, page.calls = [], []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    tb.stub_taxa(page)

    def idents(route):
        q = parse_qs(urlparse(route.request.url).query)
        page.calls.append({k: v[0] for k, v in q.items()})
        answers(route, len(page.calls))

    page.route("https://api.inaturalist.org/v1/observations/identifiers*", idents)
    page.goto(f"{site}/tree.html#sel=900")
    page.wait_for_selector("#card [data-idents]")
    return page


def line(page, text):
    page.wait_for_function(
        "t => document.querySelector('#card [data-idents]')?.textContent.includes(t)",
        arg=text,
        timeout=15000,
    )
    return page.inner_text("#card [data-idents]")


def ok(total):
    body = {"total_results": total, "results": [{"user": {"login": LOGIN, "id": 99}, "count": 3}]}
    return lambda route, n: route.fulfill(json=body, headers=CORS)


def test_the_card_shows_identifiers_and_backlog_per_identifier(browser, site):
    page = open_tree(browser, site, ok(7))
    text = line(page, "per identifier")
    need = int(page.locator("#card dt:has-text('Need an ID') + dd").inner_text().replace(",", ""))
    assert text == f"7 identifiers in BC · {round(need / 7)} needs-ID per identifier"
    call = next(c for c in page.calls if c["taxon_id"] == "900")
    assert call["place_id"] == "7085" and call["per_page"] == "0"
    assert LOGIN not in page.inner_text("body") and LOGIN not in page.content()
    assert page.errors == []
    page.close()


def test_no_identifiers_says_so(browser, site):
    page = open_tree(browser, site, ok(0))
    assert line(page, "no identifiers") == "no identifiers in BC yet"
    page.close()


def test_a_throttled_reply_is_retried_and_the_count_follows(browser, site):
    def answers(route, n):
        if n == 1:  # iNaturalist's 429 carries no CORS headers, so the page sees a failed fetch
            return route.fulfill(status=429, body="slow down")
        ok(3)(route, n)

    page = open_tree(browser, site, answers)
    line(page, "trying again")
    assert "3 identifiers in BC" in line(page, "3 identifiers")
    assert len(page.calls) >= 2 and page.calls[0] == page.calls[1]
    page.close()
