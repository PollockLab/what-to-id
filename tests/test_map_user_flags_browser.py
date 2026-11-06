"""The map's User ticks in Chromium: they add up, Hide and Observed exclude each other, Hide and
the login are remembered in localStorage, and Sign out forgets them. The site is
test_map_user_browser.py's."""

import time

from . import test_map_user_browser as ub

browser, site = ub.browser, ub.site
open_map, shown, checked, N, IN_GENUS_A = (
    ub.open_map,
    ub.shown,
    ub.checked,
    ub.N,
    ub.IN_GENUS_A,
)
DAY = 864e5


def test_only_my_genera_and_hide_add_up_and_round_trip_in_the_hash(browser, site):
    page = open_map(browser, site, "#user=42&umode=unid,taxa&umin=50")
    shown(page, IN_GENUS_A - 3)  # records 1 to 3, which the user identified, sit in Genus A
    assert checked(page) == ["taxa", "unid"]
    page.wait_for_function("location.hash.includes('user=42&umode=taxa,unid&umin=50')")
    page.uncheck("#usrtaxa")
    shown(page, N - 3)
    page.wait_for_function("location.hash.includes('umode=unid&')")
    assert page.errors == []
    page.close()


def test_hide_and_observed_exclude_each_other(browser, site):
    page = open_map(browser, site, "#user=10&umode=first")
    page.wait_for_function("/^Your top/.test(document.querySelector('#usrbox p').textContent)")
    assert not page.is_disabled("#usrunid") and not page.is_disabled("#usrobserver")
    page.check("#usrunid")
    assert page.is_disabled("#usrobserver") and "ID" in page.get_attribute("#usrobserver", "title")
    page.uncheck("#usrunid")
    page.check("#usrobserver")
    shown(page, N // 2)
    assert page.is_disabled("#usrunid") and not page.is_checked("#usrunid")
    page.wait_for_function("!location.hash.includes('umode')")  # Observed alone, an old link
    page.close()


def type_login(page, login):
    page.evaluate("document.getElementById('usrbox').open = true")
    page.fill("#usrname", login)
    page.press("#usrname", "Enter")


def test_hide_is_off_for_a_typed_login_until_ticked_then_remembered(browser, site):
    page = open_map(browser, site, "")
    shown(page, N)
    type_login(page, "42")
    page.wait_for_function("location.hash.includes('user=42&umode=first')")
    assert checked(page) == []
    page.check("#usrunid")
    shown(page, N - 3)
    sign_out(page)
    page.wait_for_function("!location.hash.includes('user=')")
    page.reload()
    shown(page, N)
    assert page.input_value("#usrname") == ""  # the login was forgotten
    type_login(page, "42")
    page.wait_for_function("location.hash.includes('user=42&umode=unid')")
    shown(page, N - 3)
    page.uncheck("#usrunid")
    assert page.evaluate("localStorage.getItem('wtid.uhide')") == "0"
    page.close()


def sign_out(page):
    page.keyboard.press("Escape")  # a tick's explanation may still be open over the button
    page.click("#usrbox button:has-text('Sign out')")


def stored(page, age):
    page.evaluate(
        "t => localStorage.setItem('wtid.user', JSON.stringify({user: '42', t: Date.now() - t}))",
        age,
    )
    page.evaluate("history.replaceState(null, '', location.pathname + location.search)")
    page.reload()


def test_a_login_from_the_last_day_comes_back_and_an_older_one_does_not(browser, site):
    page = open_map(browser, site, "")
    shown(page, N)
    stored(page, DAY - 60e3)
    page.wait_for_function("location.hash.includes('user=42&umode=first')")
    assert page.input_value("#usrname") == "42" and checked(page) == []
    page.close()
    page = open_map(browser, site, "")
    shown(page, N)
    stored(page, DAY + 60e3)
    shown(page, N)
    time.sleep(0.5)  # the hash is written 250 ms after a refilter
    assert "user=" not in page.evaluate("location.hash") and page.input_value("#usrname") == ""
    page.close()


def test_a_login_in_the_hash_wins_over_the_stored_one(browser, site):
    page = open_map(browser, site, "")
    shown(page, N)
    page.evaluate("localStorage.setItem('wtid.user', JSON.stringify({user: '42', t: Date.now()}))")
    page.close()
    page = open_map(browser, site, "#user=10")
    shown(page, N // 2)
    assert page.input_value("#usrname") == "10"
    page.close()


def test_sign_out_clears_the_hash_and_the_stored_login(browser, site):
    page = open_map(browser, site, "")
    shown(page, N)
    type_login(page, "42")
    page.wait_for_function("localStorage.getItem('wtid.user')")
    assert '"user":"42"' in page.evaluate("localStorage.getItem('wtid.user')")
    page.evaluate("document.querySelector('#usrbox details').open = true")
    page.select_option("#usrbox select", "50")
    page.wait_for_function("location.hash.includes('umin=50')")
    sign_out(page)
    page.wait_for_function("!/(^|[#&])(user|umode|umin)=/.test(location.hash)")
    assert page.evaluate("localStorage.getItem('wtid.user')") is None
    assert page.input_value("#usrname") == "" and page.is_hidden(
        "#usrbox button:has-text('Sign out')"
    )
    page.reload()
    shown(page, N)
    assert page.input_value("#usrname") == ""
    assert page.errors == []
    page.close()


def test_the_page_works_without_local_storage(browser, site):
    page = browser.new_page()
    page.add_init_script(
        "Object.defineProperty(window, 'localStorage', {get() { throw new Error('denied'); }})"
    )
    page.route(
        "https://unpkg.com/**",
        lambda r: r.fulfill(body=ub.LAYERS_STUB, content_type="text/javascript"),
    )
    page.route("https://api.inaturalist.org/**", lambda r: r.fulfill(json=ub.SPECIES_COUNTS))
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(site + "#user=42&umode=taxa,unid")
    page.wait_for_function("/^Your top/.test(document.querySelector('#usrbox p').textContent)")
    sign_out(page)
    page.wait_for_function("!location.hash.includes('user=')")
    assert errors == []
    page.close()
