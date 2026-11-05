"""The site's glossary: a plain sentence a term, shown by the toggletips, site_assets/explain.js.

Tag an element with ``data-explain="<key>"`` to explain it; page_nav puts this table on every page
but the study page. Each entry is (definition, use when or None); page_nav adds the More link.
Every sentence restates wording already on the site or in the repo: no new facts here. Stdlib
only, no imports, as page_nav runs on a bare python3.
"""

GLOSSARY: dict[str, tuple[str, str | None]] = {
    "needs-id": (
        "A record on iNaturalist that still needs an ID. It stops needing one once it becomes"
        " Research Grade or casual.",
        None,
    ),
    "research-grade": (
        "A quality grade on iNaturalist: a Research Grade record no longer needs an ID.",
        None,
    ),
    "left-needs-id": (
        "Records that stopped needing an ID in the last 7 or 30 days, for example by becoming"
        " Research Grade.",
        None,
    ),
    "batch": (
        "A block of up to 200 records that opens as one iNaturalist Identify page.",
        "Use it when a selection holds more than 200 records: each click on Identify opens the"
        " next batch in a new tab.",
    ),
    "identify-only": (
        "A project added for Identify only goes into the Identify link but does not change the"
        " map or its counts.",
        None,
    ),
    "closest-matches": (
        "The photos that look most like this one to the model, found in the full image space."
        " 1 is the most alike.",
        None,
    ),
    "match-n": (
        "Its place among the closest matches, where 1 is the most alike. The numbers match the"
        " map markers.",
        None,
    ),
    "cosine": (
        "The model's match score: how alike two things look to it. Higher means more alike.",
        None,
    ),
    "globi": (
        "GloBI (Global Biotic Interactions) lists species found together, like a rust on its rose,"
        " so pairs often photographed together are skipped.",
        None,
    ),
    "life-groups": (
        "Big groups of life, such as birds, plants and fungi. Each has its own colour on the map"
        " and in the photo space. The bar shows each group's share of the records in view, or in"
        " all of BC with All of BC on. Click a group to pick it, again to clear it; groups combine"
        " with each other and with the taxa.",
        None,
    ),
    "taxa-filter": (
        "Pick several to combine. A taxon keeps everything below it, so Bryophyta keeps all"
        " mosses.",
        None,
    ),
    "your-selection": (
        "What the map keeps. Click a chip to flip it, between keep and leave out.",
        None,
    ),
    "location-hidden": (
        "The exact place is hidden (obscured), so the map draws the record at a rounded spot.",
        None,
    ),
    "location-uncertain": (
        "The observer or device reported that the location could be more than 1 km off.",
        None,
    ),
    "location-accuracy": (
        "How accurate the observer or device reported the location to be. Picking a distance"
        " also hides records whose location is hidden.",
        None,
    ),
    "introduced": ("A species that is not native to BC.", None),
    "threatened": ("A species with a threatened status.", None),
    "observer-filter": ("Keeps the records this user observed.", None),
    "my-taxa": (
        "Keeps the records inside a genus or family this user has identified in BC.",
        None,
    ),
    "not-identified-by-me": (
        "Hides the records this user has already identified.",
        None,
    ),
    "colour-by-levels": (
        "Colours each dot by its Identify level. Dots without a level stay faint grey.",
        None,
    ),
    "colour-by-groups": (
        "Colours each dot by its life group. With one group or taxon picked, the groups below it"
        " get their own colours.",
        None,
    ),
    "levels": (
        "A level sorts records for review. It does not say that a label is right or wrong.",
        None,
    ),
    "level-clear-matches": (
        "Labelled at species, and the photo looks just like its label.",
        "Use it when you want to confirm many in one go.",
    ),
    "level-close-calls": (
        "Another species looks almost as likely as the label, or it may be something else.",
        "Use it when you have time for a careful look.",
    ),
    "level-narrow-it-down": (
        "Labelled above species, and the photo points to one species of it.",
        "Use it when you can take a record to species.",
    ),
    "level-odd-shots": (
        "Hard photos, like hands, eggs and close-ups, that match no species well.",
        "Use it when you feel lucky.",
    ),
    "level-might-be-mislabelled": (
        "The photo matches another species clearly better than its label.",
        "Use it when you want to check whether a label is wrong.",
    ),
    "photo-space": (
        "Every photo placed so that photos the model finds alike sit together. Distance is not"
        " confidence.",
        None,
    ),
    "taxonomy": (
        "Every BC record that still needs an ID, counted at the taxon its community ID has"
        " reached and rolled up iNaturalist's taxonomy.",
        None,
    ),
    "confused-pairs": (
        "A photo is confused when, to the model, it matches another species' name better than"
        " its own label.",
        None,
    ),
    "in-view": ("Counts the records in the map view.", None),
    "all-of-bc": ("Counts every record in BC, wherever the map is.", None),
    "observed": ("The date the photo was taken.", None),
    "uploaded": ("The date the record was added to iNaturalist.", None),
    "backlog-per-identifier": (
        "The records here that need an ID, divided by the number of people who identify this"
        " taxon in BC.",
        None,
    ),
    "share-needing-id": (
        "This taxon's share of all the records that need an ID.",
        None,
    ),
    "clade": (
        "A branch of the tree of life: one group and everything below it, such as a genus, family"
        " or order.",
        None,
    ),
    "agreeing-ids": ("How many of the IDs agree with the record's community ID.", None),
    "your-groups": (
        "The map shows only the groups you saved. Show all brings back every group.",
        None,
    ),
    "identified-to-rank": (
        "Records whose ID stops at this taxon and goes no further down.",
        None,
    ),
}
