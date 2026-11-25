"""Shared pieces of the Food web page tests: sample data, a static server, the page opener."""

import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from what_to_id import page_eating

META = {
    "source": "test",
    "rule": "r",
    "pairs": [
        ["Strix", "Mus musculus", 0.9],
        ["Strix", "Myodes", 0.5],
        ["Buteo", "Mus musculus", 0.5],
        ["Strix", "Mus musculus domesticus", 0.5],  # the same animal under another name
    ],
    "common": {"Mus musculus": "House Mouse", "Mus musculus domesticus": "House Mouse"},
    "parent": {
        "Mus musculus": "Mus",
        "Mus": "Muridae",
        "Muridae": "Rodentia",
        "Myodes": "Cricetidae",
        "Cricetidae": "Rodentia",
        "Rodentia": "Mammalia",
        "Strix": "Strigidae",
        "Strigidae": "Strigiformes",
        "Strigiformes": "Aves",
        "Buteo": "Accipitridae",
        "Accipitridae": "Accipitriformes",
        "Accipitriformes": "Aves",
    },
    "rank": {
        "Strigidae": "family",
        "Accipitridae": "family",
        "Muridae": "family",
        "Rodentia": "order",
    },
    "groups": {"Aves": "Birds", "Mammalia": "Mammals"},
}
OBS = {
    "fetched": "2026-11-13",
    "n": {"obs": 13, "named": 13},
    "obs": [
        {
            "id": i,
            "t": ["Strix varia", 1, "Barred Owl"],
            "k": "eating",
            "c": 0,
            "q": "needs_id",
            "on": "2026-01-01",
            "at": "BC",
            "ph": "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7",
            "f": ["Mus", 2] if i else ["Mus musculus", 3],
        }
        for i in range(12)
    ]
    + [
        {
            "id": 99,
            "t": ["Mus musculus", 3, "House Mouse"],
            "k": "by",
            "c": 0,
            "q": "research",
            "on": "",
            "at": "",
            "ph": "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7",
            "f": ["Strix varia", 1],
        }
    ],
}


PH = OBS["obs"][0]["ph"]
OWL = ["Strix varia", 1, "Barred Owl"]


def hit(id_, d, g=(), c=0, np=1):
    return {"id": id_, "t": OWL, "k": "text", "c": c, "q": "research", "on": "2026-03-01",
            "at": "BC", "ph": PH, "np": np, "d": d, "g": list(g)}  # fmt: skip


# food-word hits: the owl with a mouse in the description, with a Myodes, and with food words only
TEXT = {
    "fetched": "2026-11-13",
    "n": 3,
    "obs": [
        hit(501, "Barred Owl with a mouse"),
        hit(502, "Eating a Myodes", c=1, np=2),
        hit(503, "", ["predation"]),
    ],
}


# a model hint for observation 0 (the first card of the owl question): feeding, a box, a prey guess
VLM = {
    "model": "test",
    "obs": {"0": {"p": 0.95, "box": [100, 200, 600, 800], "prey": [["Mus musculus", 0.6]]}},
}


def serve(root, name):
    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    handler.log_message = lambda *a: None
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/{name}"
    server.shutdown()


def build_site(root, vlm=True, data_url=""):
    (root / page_eating.OBS_FILE).write_text(json.dumps(OBS))
    assert page_eating.build(root / "none") is None  # no data files, no page
    (root / page_eating.METAWEB_FILE).write_text(json.dumps(META))
    (root / page_eating.TEXT_FILE).write_text(json.dumps(TEXT))
    if vlm:
        (root / page_eating.VLM_FILE).write_text(json.dumps(VLM))
    assert page_eating.build(root, data_url).name == "food-web.html"
    return serve(root, "food-web.html")


# the model study is the default source; tests start on all sources unless study=True
ALL_SOURCES = (
    "if(!localStorage.getItem('wtid-loop'))localStorage.setItem('wtid-loop','{\"src\":\"\"}')"
)


def open_page(browser, url, init=None, study=False):
    page = browser.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    if not study:
        page.add_init_script(ALL_SOURCES)
    if init:
        page.add_init_script(init)
    page.goto(url)
    page.wait_for_function("window.__food && window.__text")
    return page


OPTIONS = ["Not this predator", "Not eating", "Can’t tell", "Eating"]


def answer(card, option):
    """Click one of the card's four options (keys 1-4)."""
    card.locator(".mk button").nth(OPTIONS.index(option)).click()
