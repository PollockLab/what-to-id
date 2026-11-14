"""Shared vocabulary for the identifier-facing pages: the arm-name leak guard and plain group names.

Arm names never reach the HTML; pages show only the blind label (A/B/C). The label to arm
mapping lives in manifest.json alone.
"""

from __future__ import annotations

from pathlib import Path

ARM_WORDS = ("recency", "gap_first", "similarity", "novelty", "gap first", "surprise")

GROUP_NAMES = {
    "Actinopterygii": "Fish",
    "Amphibia": "Amphibians",
    "Animalia": "Other animals",
    "Arachnida": "Spiders and allies",
    "Aves": "Birds",
    "Chromista": "Kelp and allies",
    "Fungi": "Fungi and lichens",
    "Insecta": "Insects",
    "Mammalia": "Mammals",
    "Mollusca": "Molluscs",
    "Plantae": "Plants",
    "Protozoa": "Slime moulds",
    "Reptilia": "Reptiles",
}


def group_name(group: str) -> str:
    """Plain name for an iconic taxon, with the Latin group in brackets when they differ."""
    plain = GROUP_NAMES.get(group)
    return f"{plain} ({group})" if plain else group


def _assert_blind(html: str, path: Path) -> None:
    low = html.lower()
    for w in ARM_WORDS:
        if w in low:
            raise ValueError(f"{path.name}: arm name {w!r} leaked into the page")
