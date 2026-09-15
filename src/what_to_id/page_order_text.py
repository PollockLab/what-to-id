"""Plain words for each list order: the short line, the rule, the parameters and the why.

Kept apart from the method sections so neither file grows past the repo's file length limit.
Never an arm name: ARM_WORDS guards the page against that.
"""

from __future__ import annotations

import re

from what_to_id.page_doc import Doc

# Plain words for each order. Never the arm names, which ARM_WORDS guards.
ORDER_TEXT = {
    "recency": "<b>Newest first.</b> The control, close to what iNaturalist shows today.",
    "gap_first": "<b>Data-poor places first.</b> Records from areas with few or old records.",
    "similarity": "<b>Look-alike photos together.</b> Similar photos come in groups.",
    "novelty": "<b>Unfamiliar photos first.</b> Photos least like any Research Grade photo.",
    "surprise": "<b>Unexpected sightings first.</b> Species seen where, or in a climate where, "
    "few Research Grade records of that species are.",
}

# How each order sorts, as arms.py and cells.py do it. Same rule: no arm names.
ORDER_DETAIL = {
    "recency": "<b>Newest first</b> sorts by the time the record was added to iNaturalist, "
    "newest first.",
    "gap_first": "<b>Data-poor places first</b> sorts by the where-to-blitz map score of the "
    "nearest map cell for the record's taxon group, highest first. The score is the map's "
    '"Species discovery" setting: its discovery measure plus 0.6 times its record-age measure, '
    "cut to 0 to 1. This code reads both measures from the where-to-blitz map files as they "
    "are. By the where-to-blitz methods note at the pinned commit, the discovery measure is "
    "higher where a cell has fewer iNaturalist records per km², and highest where it has none. "
    "The record-age measure is higher where a cell has many Research Grade records from all "
    "years but few from the last 5 years. Where where-to-blitz has no such value for a cell, it "
    "uses a stand-in from record density. A record more than 20 km from a cell centre has no "
    "score and goes last. A taxon group without its own map uses the map for all groups.",
    "similarity": "<b>Look-alike photos together</b> uses an image model (BioCLIP 2.5) that "
    "turns each photo into numbers, so photos that look alike sit close together. It picks start "
    "photos spread across all the photos and grows a group of one batch size around each, "
    "adding the free photo closest to the group centre. The last group takes the photos left, "
    "so it can be smaller. Groups with the highest mean map score "
    "come first. Batches are cut from this order, so a batch can end one group and start the "
    "next.",
    "novelty": "<b>Unfamiliar photos first</b> compares each photo, with the same image model, "
    "with every Research Grade photo of its taxon group in the reference pull. Records whose "
    "closest verified photo is least alike come first.",
    "surprise": "<b>Unexpected sightings first</b> gives each record a tail probability: how "
    "far out its place, or its climate, is for the proposed species, against that species' "
    "Research Grade records. Least expected first. Ties go to a range-model score if the build "
    "has one, then to species with the fewest Research Grade records in the region.",
}

_TIES = "Ties go to the newest record, then to the higher record number."
_MODEL = (
    "BioCLIP 2.5 Huge (ViT-H/14, checkpoint <code>imageomics/bioclip-2.5-vith14</code>), a "
    "larger successor of BioCLIP 2 {gu}, described in its model card {card}. The model card says "
    "it was trained on an updated version of TreeOfLife-200M, starting from a CLIP model "
    "pre-trained on LAION-2B. The model computes numbers from the record's first photo, at "
    "iNaturalist's medium size"
)


def _model(d: Doc) -> str:
    return _MODEL.format(gu=d.cite("gu2025"), card=d.cite("bioclip25card"))


ORDER_PARAMS = {
    "recency": lambda d: (
        "The time iNaturalist gives as the record's creation time. Ties go to "
        "the higher record number."
    ),
    "gap_first": lambda d: (
        "Map: where-to-blitz, one map per taxon group, with cells of 25 km as where-to-blitz "
        "states. Score: "
        "discovery plus 0.6 times record age, cut to 0 to 1. Nearest cell centre within 20 km, "
        f"else no score. {_TIES}"
    ),
    "similarity": lambda d: (
        f"Image model: {_model(d)}. Number of start photos: the records in the list and taxon "
        "group that have numbers that the image model computes from each photo, divided by the "
        "batch size, rounded up. Start photos are picked farthest-first in cosine distance, the "
        f"first at random {d.cite('gonzalez1985', 'sener2018')}. A start photo already taken by "
        "an earlier group is replaced by the closest free photo. Each start grows to one batch "
        "size, and the last group takes the photos left, so it can be smaller. Groups with no "
        "scored record go last. Inside a group, photos closest to the group centre come first. "
        "Records with no such numbers go last, newest first."
    ),
    "novelty": lambda d: (
        f"Image model: {_model(d)}. Distance: 1 minus the highest cosine likeness to any "
        "Research Grade photo of the same taxon group. "
        f"Largest distance first. {_TIES} Records with no numbers from the image model, or in a "
        "taxon group with no reference photos, go last, newest first. Reference photos: a second "
        "run of the pull code that asks for Research Grade records in place of Needs ID: BC "
        "(place 7085), with a photo, one taxon group at a time, newest first, with the dates and "
        "page cap given when it is run. The build keeps only a checksum of the file of numbers "
        "computed from those photos, not the pull's dates or page cap, so this page cannot say "
        "how many reference photos there are. The daily job does not run this pull."
    ),
    "surprise": lambda d: (
        "Tail probability: the share of the species' Research Grade records "
        "that sit in a denser part of the species' own cloud than the record does. Density: a "
        "Gaussian kernel, 25 km wide for place. A species with fewer than 5 reference records "
        "scores 1. At most 1,500 reference records per species, drawn at random. Records with no "
        "score go last."
    ),
}
ORDER_WHY = {
    "recency": lambda d: (
        "The control. Identify shows records newest first by default (iNaturalist source "
        f"{d.cite('inatsource')}), so this list is close to what identifiers meet today."
    ),
    "gap_first": lambda d: (
        "The value question. The idea to test: an ID in a data-poor place helps fill a gap in "
        f"where species are known to occur, the Wallacean shortfall {d.cite('hortal2015')}, and "
        "in how recent the records are. Blitz the Gap calls these spatial and temporal gaps "
        f"{d.cite('hebert2026')}. The draft protocol expects this list to lose on the plain "
        "count and to win on the weighted count."
    ),
    "similarity": lambda d: (
        "The speed question. The idea to test: fewer switches between kinds "
        "of photo make identifying faster."
    ),
    "novelty": lambda d: (
        "The value question. The idea to test: an ID on a photo unlike any verified photo is "
        "more likely to add a species, or a look of a species, that the verified record does not "
        "cover yet."
    ),
    "surprise": lambda d: (
        "The idea to test: a record far from where its species is known is "
        "either a wrong ID or news about the species' range, and both are worth an expert's look. "
        "The order ranks records for a person to check. It never marks one as wrong."
    ),
}
ORDER_CAPTION = {
    "recency": "on 12 made-up records, placed by the time they were added. The newest go first.",
    "gap_first": "on 12 made-up records in a made-up grid of map cells. Stronger shading means a "
    "higher score. Records 11 and 12 are more than 20 km from any cell centre, so they have no "
    "score and go last.",
    "similarity": "a schematic on 14 made-up photos, placed so that photos that look alike are "
    "close. Ringed photos are the start photos, from a farthest-first helper written for this "
    "figure. The build picks them with the labelfirst library. Each start grows a group of up to "
    "4 with the build's own code, and the group number is its rank by mean map score. The "
    "batches are cut from that order, so a batch can end one group and start the next.",
    "novelty": "on 8 made-up photos (numbered) and 15 made-up Research Grade photos (grey), "
    "placed so that photos that look alike are close. Each line joins a photo to its closest "
    "verified photo. The longest lines go first.",
    "surprise": "on 8 made-up records of one species (numbered) among 44 made-up verified "
    "records of that species (grey). The number next to each record is its tail probability, "
    "from the scoring code with a 25 km kernel. The highest go first.",
}


def order_name(arm: str) -> str:
    return re.match(r"<b>(.*?)\.</b>", ORDER_TEXT[arm]).group(1)
