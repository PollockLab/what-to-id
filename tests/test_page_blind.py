"""The blind page: nothing about the record before the answer, and the answer flow in Chromium."""

import functools
import http.server
import re
import threading

from what_to_id import page_blind

from . import test_embeddings_browser as eb
from .test_page_nav import FORBIDDEN

browser = eb.browser
PX = "data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw=="
RECS = [
    {"id": 7345121, "group": "Fungi", "photos": [PX, PX + "#2"], "planted": False},
    {"id": 8456232, "group": "Aves", "photos": [PX], "planted": True},
]
DATA = re.compile(r'<script type="application/json".*?</script>', re.S)


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def test_nothing_but_group_and_photos_outside_the_data():
    html = page_blind.render(RECS)
    outside = DATA.sub("", html)
    assert "Fungi" in html and "Aves" in html and PX in html
    assert "inaturalist" not in outside and "observations" not in outside
    assert not re.search(r"7345121|8456232", outside)
    assert "planted" not in html
    assert not [w for w in FORBIDDEN if w in html.lower()]


def test_empty_records_say_there_is_nothing_to_identify():
    assert "There is nothing to identify." in page_blind.render([])


def test_answer_then_reveal(browser, tmp_path):
    page_blind.build(tmp_path, RECS)
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Quiet, directory=str(tmp_path))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    pg = browser.new_page(viewport={"width": 390, "height": 800})
    try:
        pg.goto(f"http://127.0.0.1:{server.server_port}/blind.html")
        pg.fill("#login", "alice")
        pg.keyboard.press("Enter")
        assert pg.is_visible("#taxon") and pg.is_hidden("#link")
        pg.fill("#taxon", "Amanita muscaria")
        pg.check("input[value=likely]")
        pg.click("text=Save")
        assert pg.is_visible("#link") and "/observations/" in pg.get_attribute("#link", "href")
        rows = pg.evaluate("JSON.parse(localStorage.getItem('blind.answers'))")
        assert len(rows) == 1 and rows[0]["saved_at"] and rows[0]["confidence"] == "likely"
        assert rows[0]["taxon"] == "Amanita muscaria" and rows[0]["login"] == "alice"
        assert pg.evaluate("document.documentElement.scrollWidth") <= 390
        pg.click("#next")
        assert pg.is_hidden("#link")
        pg.click("#abstain")
        rows = pg.evaluate("JSON.parse(localStorage.getItem('blind.answers'))")
        assert len(rows) == 2 and rows[1]["confidence"] == "abstain" and rows[1]["taxon"] == ""
        assert {r["record_id"] for r in rows} == {7345121, 8456232}
        assert "2 of 2" in pg.inner_text("#count")
    finally:
        pg.close()
        server.shutdown()
