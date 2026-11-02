"""Clade colours in Chromium: one group picked on the map breaks its dots and the legend down by
its clades, in the tree's colours; two groups picked list as groups, and a click on one drills in
as a legend-only lens. The map runs over the stand-ins test_map_groups_browser.py uses."""

import numpy as np
import pytest

from what_to_id import tree_page
from what_to_id.page_map import encode_points, render_map

from . import test_embeddings_browser as eb
from . import test_explore_home_browser as eh
from .embeddings_fixture import pool_frame
from .test_tree_browser import serve, stub_taxa

browser = eb.browser
# taxon id -> [parent, latin, common, rank]: Plantae's three phyla (two species in the first, so the
# tree gives it a row of its own), Insecta's two orders, Aves alone
TREE = {
    48460: [None, "Life", "Life", "stateofmatter"],
    47126: [48460, "Plantae", "Plants", "kingdom"],
    211194: [47126, "Tracheophyta", "Vascular Plants", "phylum"],
    311249: [47126, "Bryophyta", "Mosses", "phylum"],
    64615: [47126, "Marchantiophyta", "Liverworts", "phylum"],
    5001: [211194, "Acer macrophyllum", "Bigleaf Maple", "species"],
    5004: [211194, "Thuja plicata", "Western Redcedar", "species"],
    5002: [311249, "Sphagnum fuscum", "", "species"],
    5003: [64615, "Marchantia polymorpha", "", "species"],
    47158: [48460, "Insecta", "Insects", "class"],
    47157: [47158, "Lepidoptera", "Butterflies and Moths", "order"],
    47208: [47158, "Coleoptera", "Beetles", "order"],
    6001: [47157, "Vanessa cardui", "Painted Lady", "species"],
    6002: [47208, "Coccinella septempunctata", "", "species"],
    3: [48460, "Aves", "Birds", "class"],
    7001: [3, "Turdus migratorius", "American Robin", "species"],
}
# records 0-99 Tracheophyta, 100-149 Bryophyta, 150-169 Marchantiophyta, 170-229 Lepidoptera,
# 230-269 Coleoptera, 270-299 Aves
SPLIT = [(5001, 60, "Plantae"), (5004, 40, "Plantae"), (5002, 50, "Plantae"), (5003, 20, "Plantae")]
SPLIT += [(6001, 60, "Insecta"), (6002, 40, "Insecta"), (7001, 30, "Aves")]
FADE = [150, 150, 150, 40]
GREEN = [40, 160, 60, 110]  # Plantae's group colour


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("clade-colour")
    pool = pool_frame(np.arange(1, 301))
    pool["taxon_id"] = [t for t, n, _ in SPLIT for _ in range(n)]
    pool["taxon_name"] = [TREE[t][1] for t, n, _ in SPLIT for _ in range(n)]
    pool["iconic_taxon"] = [g for _, n, g in SPLIT for _ in range(n)]
    blobs, meta = encode_points(pool, TREE)
    for name, blob in blobs.items():
        (root / name).write_bytes(blob)
    (root / "map.html").write_text(render_map(meta, freeze=None))
    tree_page.build(root)
    server, url = serve(root)
    yield url
    server.shutdown()


def open_map(browser, site, width=1280, hash_="", n=300):
    page = eh.open_page(browser, f"{site}/map.html?standalone=1{hash_}", width)
    page.wait_for_function(f"document.getElementById('count').textContent.startsWith('{n} ')")
    page.wait_for_selector("#groups .gt", state="attached")  # the taxa have loaded
    return page


# the fill of records 0, 100, 150, 170 and 270, and the legend: heading, rows, buttons, trail
STATE = """() => { const c = window.__layers[0].props.data.attributes.getFillColor.value,
  at = i => Array.from(c.slice(4 * i, 4 * i + 4)), l = document.querySelector('.lvleg'),
  rows = [...l.querySelectorAll('.lrows > span:not(.lt)')];
  return {dots: [0, 100, 150, 170, 270].map(at), shown: !l.hidden,
    head: (l.querySelector('.lrows > .lt') || {}).textContent || '',
    names: rows.map(s => s.title), swatch: rows.map(s => s.querySelector('i').style.background),
    buttons: rows.map(s => s.getAttribute('role') === 'button')}; }"""


def pick(page, name):
    page.locator("#groups > li", has_text=name).locator(".gb").click()


def rgb(c):
    return f"rgb({c[0]}, {c[1]}, {c[2]})"


def test_one_group_breaks_down_by_clade_in_the_tree_colours_and_clearing_it_goes_back(
    browser, site
):
    page = open_map(browser, site)
    assert not page.evaluate(STATE)["shown"]  # nothing picked: the group colours, no legend
    pick(page, "Plants")
    page.wait_for_function(f"({STATE})().shown")
    got = page.evaluate(STATE)
    assert got["head"] == "Plants by clade"
    assert not page.locator(".lvleg .seg").is_visible()  # no levels to switch to on the bare map
    assert got["names"] == ["Vascular Plants", "Mosses", "Liverworts"]
    assert got["swatch"] == [rgb(d) for d in got["dots"][:3]]  # each dot as its clade's swatch
    assert len({tuple(d) for d in got["dots"][:3]}) == 3 and got["dots"][0] != GREEN
    assert got["buttons"] == [True, False, False]  # only the vascular plants split further
    tree = browser.new_page(viewport={"width": 1280, "height": 900})
    stub_taxa(tree)
    tree.goto(f"{site}/tree.html")
    tree.wait_for_selector("#outline li[data-k]")
    same = tree.evaluate(
        """() => [...document.querySelectorAll('#outline li')]
      .find(e => e.querySelector('.nm').textContent === 'Tracheophyta Vascular Plants')
      .querySelector('i').style.background"""
    )
    assert same == got["swatch"][0]  # the tree draws the clade in the map's colour
    tree.close()
    pick(page, "Plants")  # again clears it
    page.wait_for_function(f"!({STATE})().shown")
    got = page.evaluate(STATE)
    assert got["dots"][0] == GREEN and got["dots"][4][3] == 110
    assert page.errors == []
    page.close()


def test_two_groups_list_as_groups_and_a_click_drills_into_one_until_esc(browser, site):
    page = open_map(browser, site)
    pick(page, "Plants")
    pick(page, "Insects")
    page.wait_for_function(f"({STATE})().names.length === 2")
    got = page.evaluate(STATE)
    assert got["names"] == ["Insects", "Plants"] and got["buttons"] == [True, True]
    assert got["dots"][0] == GREEN  # no sub-clades yet
    page.locator(".lvleg [role=button]", has_text="Plants").click()
    page.wait_for_function(f"({STATE})().names.length === 3")
    got = page.evaluate(STATE)
    assert got["head"] == "All groups / Plants"
    assert got["names"] == ["Vascular Plants", "Mosses", "Liverworts"]
    assert got["dots"][3] == FADE and got["dots"][0] != GREEN  # the insects turn grey
    assert got["swatch"][0] == rgb(got["dots"][0])
    page.keyboard.press("Escape")
    page.wait_for_function(f"({STATE})().names.length === 2")
    got = page.evaluate(STATE)
    assert got["dots"][0] == GREEN and got["dots"][3][3] == 110
    page.locator(".lvleg [role=button]", has_text="Insects").focus()
    page.keyboard.press("Enter")  # the rows work from the keyboard too
    page.wait_for_function(f"({STATE})().head === 'All groups / Insects'")
    page.locator(".lvleg .lb").click()  # the trail steps back out
    page.wait_for_function(f"({STATE})().names.length === 2")
    page.locator(".lvleg [role=button]", has_text="Insects").click()
    page.wait_for_function(f"({STATE})().head === 'All groups / Insects'")
    pick(page, "Insects")  # the drilled group leaves the selection: the lens goes, one group stays
    page.wait_for_function(f"({STATE})().head === 'Plants by clade'")
    assert page.errors == []
    page.close()


def test_on_a_phone_the_legend_keeps_to_a_corner(browser, site):
    page = open_map(browser, site, width=400, hash_="#groups=Plantae,Insecta", n=270)
    page.wait_for_function(f"({STATE})().names.length === 2")
    page.locator(".lvleg [role=button]", has_text="Plants").click()
    page.wait_for_function(f"({STATE})().names.length === 3")
    share = page.evaluate(
        """() => { const l = document.querySelector('.lvleg').getBoundingClientRect(),
      m = document.getElementById('map').getBoundingClientRect();
      return l.width * l.height / (m.width * m.height); }"""
    )
    assert share <= 0.34
    assert page.errors == []
    page.close()


def test_the_legend_lists_the_clades_the_filters_leave_and_keeps_their_colours(browser, site):
    page = open_map(browser, site, hash_="#groups=Plantae", n=170)
    page.wait_for_function(f"({STATE})().names.length === 3")
    was = page.evaluate(STATE)
    assert was["names"] == ["Vascular Plants", "Mosses", "Liverworts"]
    page.evaluate("location.hash = 'groups=Plantae&taxa=-64615'")  # leaves out every liverwort
    page.wait_for_function(f"({STATE})().names.length === 2")
    got = page.evaluate(STATE)
    assert got["names"] == ["Vascular Plants", "Mosses"]
    assert got["swatch"] == was["swatch"][:2]  # the clades left keep their colours
    assert got["dots"][0] == was["dots"][0]
    assert page.errors == []
    page.close()


def swatch(browser, site, hash_, name):
    tree = browser.new_page(viewport={"width": 1280, "height": 900})
    stub_taxa(tree)
    tree.goto(f"{site}/tree.html{hash_}")
    tree.wait_for_selector("#outline li[data-k]")
    got = tree.evaluate(
        """(n) => [...document.querySelectorAll('#outline li')]
      .find(e => e.querySelector('.nm').textContent === n).querySelector('i').style.background""",
        name,
    )
    tree.close()
    return got


def test_a_drilled_sub_clade_and_the_tree_focused_on_it_share_the_focused_colours(browser, site):
    page = open_map(browser, site)
    pick(page, "Plants")
    page.wait_for_function(f"({STATE})().names.length === 3")
    page.locator(".lvleg [role=button]", has_text="Vascular Plants").click()
    page.wait_for_function(f"({STATE})().head.endsWith('/ Vascular Plants')")
    got = page.evaluate(STATE)
    assert got["names"] == ["Acer macrophyllum", "Thuja plicata"]
    assert got["swatch"][0] == rgb(got["dots"][0])
    maple = "Acer macrophyllum"
    assert swatch(browser, site, "#focus=211194", maple) == got["swatch"][0]
    assert (
        swatch(browser, site, "#sel=5001", maple) != got["swatch"][0]
    )  # the overview colours it otherwise
    assert page.errors == []
    page.close()
