"""Selecting in the photo space without hidden shortcuts: the life-group legend in the split view,
the Draw button for a lasso without a shift key, and the card's one-click "only this group"."""

from . import test_embeddings_browser as eb
from . import test_split_subsets_browser as sb
from .test_embeddings_browser import POOL_N, shown
from .test_split_subsets_browser import INSIDE, LASSO

browser, site, split = eb.browser, eb.site, sb.split

KEPT_GROUPS = "__deck.props.layers.find(x => x.id === 'pts').props.filterCategories[0]"
LISTEN = (
    "window.__msgs = []; addEventListener('message', e => { if (e.data && e.data.type) "
    "__msgs.push(e.data.type); })"
)


def test_the_split_views_group_chips_are_visible_and_narrow_the_photo_space(split):
    page, (left, right) = split
    page.evaluate(LISTEN)
    chip = right.locator("#groups button[data-g='0']")
    assert chip.is_visible() and "Aves" in chip.inner_text()
    assert right.locator("#q").is_hidden() and right.locator("#tree").is_hidden()
    chip.click()
    right.wait_for_function(
        f"!document.getElementById('count').textContent.startsWith('{POOL_N:,}')"
    )
    assert 0 < shown(right) < POOL_N
    assert "wtid-selection" in page.evaluate("__msgs")
    assert page.errors == []


def test_the_draw_button_lets_a_plain_drag_draw_a_lasso_and_turns_itself_off(split):
    page, (left, right) = split
    page.evaluate(
        "window.__keep = []; addEventListener('message', e => { if (e.data && e.data.type ==="
        " 'wtid-keep') __keep.push(e.data.ids && Array.from(e.data.ids)); })"
    )
    draw = left.locator("#ldraw")
    draw.click()
    assert draw.get_attribute("aria-pressed") == "true"
    assert left.evaluate("document.getElementById('plot').classList.contains('draw')")
    box = left.locator("#plot").bounding_box()
    page.mouse.move(box["x"] + LASSO[0][0], box["y"] + LASSO[0][1])
    page.mouse.down()
    for x, y in LASSO[1:]:
        page.mouse.move(box["x"] + x, box["y"] + y)
    page.mouse.up()
    page.wait_for_function("__keep.length === 1")
    got = left.evaluate(INSIDE)
    assert got["bad"] == 0 and got["ring"] and 0 < got["inside"] < POOL_N
    assert shown(left) == got["inside"] == len(page.evaluate("__keep[0]"))
    assert draw.get_attribute("aria-pressed") == "false"
    assert left.locator("#lclear").is_visible() and draw.is_visible()
    assert page.errors == []


def test_escape_turns_the_draw_button_off(split):
    page, (left, _) = split
    left.locator("#ldraw").click()
    page.keyboard.press("Escape")
    assert left.locator("#ldraw").get_attribute("aria-pressed") == "false"
    assert page.errors == []


def test_the_cards_only_group_action_keeps_that_group_and_all_groups_undoes_it(split):
    page, (left, _) = split
    left.evaluate("__deck.props.onClick({index: 7, layer: {id: 'pts'}})")
    only = left.locator("#card .actions button")
    assert only.inner_text().startswith("Only ")
    only.click()
    kept = left.evaluate(KEPT_GROUPS)
    assert len(kept) == 1 and 0 < shown(left) < POOL_N
    assert left.locator("#groups button[aria-pressed='true']").count() == 1
    assert only.inner_text() == "All groups"
    only.click()
    assert shown(left) == POOL_N and len(left.evaluate(KEPT_GROUPS)) > 1
    assert page.errors == []
