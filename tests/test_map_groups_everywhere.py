"""Every page that shows the pool's life groups carries the Life groups setting (map_groups.js),
so a new view cannot show the split plant groups by default by leaving it out."""

from pathlib import Path

from what_to_id import (
    embeddings_page,
    page_confusion,
    page_eating,
    page_identify,
    page_map,
    split_page,
    tree_page,
)

SRC = Path(page_map.__file__).parent
# a template that inlines one of these shows or filters on the pool's groups
GROUP_SCRIPTS = ("__MAP_FILTER__", "__MAP_CHIPS__", "__EATING_PICKER_JS__", "__CONFUSION_APP__")


def test_every_template_that_shows_groups_inlines_map_groups():
    found = []
    for t in sorted(SRC.glob("*_assets/*.html")):
        html = t.read_text()
        at = [html.index(k) for k in GROUP_SCRIPTS if k in html]
        if at:
            found.append(t.name)
            assert "__MAP_GROUPS__" in html, t
    assert {"identify.html", "embeddings.html", "tree.html", "split.html"} <= set(found)
    assert {"confusion.html", "food_web.html"} <= set(found)


def test_every_builder_fills_map_groups_and_the_map_loads_it():
    for mod in (page_identify, embeddings_page, split_page, tree_page, page_confusion):
        assert mod.SCRIPTS["__MAP_GROUPS__"].name == "map_groups.js", mod.__name__
    assert "map_groups.js" in page_map.MAP_JS
    assert "var MapGroups=" in page_eating.render()
    assert "var MapGroups=" in page_eating.render(kind="pollination")
