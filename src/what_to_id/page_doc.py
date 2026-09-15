"""Code links, references and figure/table numbering for the method section.

`Doc` numbers figures and tables in the order they are rendered and numbers references in the
order they are first cited, so the section can grow or drop parts (an order that is not in the
build) without renumbering by hand.
"""

from __future__ import annotations

REPO = "https://github.com/PollockLab/what-to-id"

CODE = {
    "inat": "src/what_to_id/inat.py",
    "pool_state": "src/what_to_id/pool_state.py",
    "assign": "src/what_to_id/assign.py",
    "arms": "src/what_to_id/arms.py",
    "cells": "src/what_to_id/cells.py",
    "embed": "src/what_to_id/embed.py",
    "batches": "src/what_to_id/batches.py",
    "page": "src/what_to_id/page_rotation.py",
    "manifest": "src/what_to_id/manifest.py",
    "participants": "src/what_to_id/participants.py",
    "readback": "src/what_to_id/readback.py",
    "analysis": "src/what_to_id/analysis.py",
    "power": "src/what_to_id/power.py",
    "replay": "src/what_to_id/replay.py",
    "daily": "scripts/daily.sh",
}

# Numbered in the text by first citation, not by this order. Entries as verified by the lead.
REFERENCES = [
    {
        "key": "schulz2010",
        "text": "Schulz KF, Altman DG, Moher D (2010). CONSORT 2010 Statement: updated "
        "guidelines for reporting parallel group randomised trials. BMJ 340:c332.",
        "url": "https://doi.org/10.1136/bmj.c332",
    },
    {
        "key": "hortal2015",
        "text": "Hortal J, de Bello F, Diniz-Filho JAF, Lewinsohn TM, Lobo JM, Ladle RJ (2015). "
        "Seven shortfalls that beset large-scale knowledge of biodiversity. Annual Review of "
        "Ecology, Evolution, and Systematics 46:523-549.",
        "url": "https://doi.org/10.1146/annurev-ecolsys-112414-054400",
    },
    {
        "key": "gonzalez1985",
        "text": "Gonzalez TF (1985). Clustering to minimize the maximum intercluster distance. "
        "Theoretical Computer Science 38:293-306.",
        "url": "https://doi.org/10.1016/0304-3975(85)90224-5",
    },
    {
        "key": "sener2018",
        "text": "Sener O, Savarese S (2018). Active learning for convolutional neural networks: "
        "a core-set approach. ICLR 2018.",
        "url": "https://arxiv.org/abs/1708.00489",
    },
    {
        "key": "gu2025",
        "text": "Gu J, Stevens S, Campolongo EG, et al. (2025). BioCLIP 2: emergent properties "
        "from scaling hierarchical contrastive learning. NeurIPS 2025.",
        "url": "https://arxiv.org/abs/2505.23883",
    },
    {
        "key": "bioclip25card",
        "text": "Imageomics (2025). BioCLIP 2.5 Huge model card: a ViT-H/14 model trained on an "
        "updated TreeOfLife-200M, starting from CLIP ViT-H/14 pre-trained on LAION-2B. Hugging "
        "Face model imageomics/bioclip-2.5-vith14.",
        "url": "https://huggingface.co/imageomics/bioclip-2.5-vith14",
    },
    {
        "key": "chapelle2012",
        "text": "Chapelle O, Joachims T, Radlinski F, Yue Y (2012). Large-scale validation and "
        "analysis of interleaved search evaluation. ACM Transactions on Information Systems "
        "30(1):6.",
        "url": "https://doi.org/10.1145/2094072.2094078",
    },
    {
        "key": "good2005",
        "text": "Good PI (2005). Permutation, Parametric, and Bootstrap Tests of Hypotheses, "
        "3rd ed. Springer.",
        "url": "https://doi.org/10.1007/b138696",
    },
    {
        "key": "phipson2010",
        "text": "Phipson B, Smyth GK (2010). Permutation p-values should never be zero: "
        "calculating exact p-values when permutations are randomly drawn. Statistical "
        "Applications in Genetics and Molecular Biology 9(1):39.",
        "url": "https://doi.org/10.2202/1544-6115.1585",
    },
    {
        "key": "holm1979",
        "text": "Holm S (1979). A simple sequentially rejective multiple test procedure. "
        "Scandinavian Journal of Statistics 6(2):65-70.",
        "url": "https://www.jstor.org/stable/4615733",
    },
    {
        "key": "hebert2026",
        "text": "Hébert K, Earley NG, Reynolds JD, et al. (2026). Blitz the Gap: a nation-wide "
        "effort to guide citizen science toward the needs of biodiversity science. EcoEvoRxiv "
        "preprint, version 5.",
        "url": "https://doi.org/10.32942/X2T09G",
    },
    {
        "key": "mesaglio2025",
        "text": "Mesaglio T, Shepherd KA, Wege JA, Barrett RL, Sauquet H, Cornwell WK (2025). "
        "Expert identification blitz: a rapid high value approach for assessing and improving "
        "iNaturalist identification accuracy and data precision and confidence. Plants, People, "
        "Planet 7:1469-1484.",
        "url": "https://doi.org/10.1002/ppp3.70005",
    },
    {
        "key": "inatsource",
        "text": "iNaturalist source code, Identify's default search parameters (reviewed false, "
        "quality grade Needs ID, order by id, descending). File "
        "app/webpack/observations/identify/reducers/search_params_reducer.js, lines 10-21, "
        "commit ae0cc5d.",
        "url": "https://github.com/inaturalist/inaturalist/blob/"
        "ae0cc5d4e8fa188151f9adc2805afdb2d0643bcd/app/webpack/observations/identify/reducers/"
        "search_params_reducer.js#L10-L21",
    },
]
_REF = {r["key"]: r for r in REFERENCES}


def ext(url: str, text: str) -> str:
    return f'<a href="{url}" target="_blank" rel="noopener">{text}</a>'


def a(path: str, text: str) -> str:
    """A link to a file (and optional #heading) on the repo's main branch."""
    return ext(f"{REPO}/blob/main/{path}", text)


def code(key: str) -> str:
    path = CODE[key]
    return a(path, f"<code>{path.rsplit('/', 1)[-1]}</code>")


def codes(*keys: str) -> str:
    return '<p class="src">Code: ' + ", ".join(code(k) for k in keys) + ".</p>"


class Doc:
    """Figure, table and reference counters for one rendering of the section."""

    def __init__(self) -> None:
        self.n_fig = 0
        self.n_tab = 0
        self.cited: list[str] = []
        self.named: dict[str, tuple[str, int]] = {}

    def ref(self, name: str) -> str:
        """A link to a figure or table rendered earlier under `name`, e.g. "Table 2"."""
        if name not in self.named:
            raise KeyError(f"no figure or table named {name!r} rendered yet")
        kind, n = self.named[name]
        return f'<a href="#{kind[:3].lower()}-{n}">{kind} {n}</a>'

    def cite(self, *keys: str) -> str:
        nums = []
        for k in keys:
            if k not in _REF:
                raise KeyError(f"no reference {k!r} in REFERENCES")
            if k not in self.cited:
                self.cited.append(k)
            n = self.cited.index(k) + 1
            nums.append(f'<a href="#ref-{n}">{n}</a>')
        return f'<span class="cite">[{", ".join(nums)}]</span>'

    def figure(self, svg: str, caption: str, *, name: str | None = None) -> str:
        self.n_fig += 1
        n = self.n_fig
        if name:
            self.named[name] = ("Figure", n)
        return (
            f'<figure class="fig" id="fig-{n}">{svg}'
            f"<figcaption><b>Figure {n}.</b> {caption}</figcaption></figure>"
        )

    def table(
        self,
        caption: str,
        head: list[str],
        rows: list[list[str]],
        *,
        wrap: bool = False,
        name: str | None = None,
    ) -> str:
        self.n_tab += 1
        n = self.n_tab
        if name:
            self.named[name] = ("Table", n)
        th = "".join(f'<th scope="col">{h}</th>' for h in head)
        body = "".join(
            f'<tr><th scope="row">{r[0]}</th>{"".join(f"<td>{c}</td>" for c in r[1:])}</tr>'
            for r in rows
        )
        cls = ' class="wrap"' if wrap else ""
        return (
            f'<div class="tablewrap"><table{cls} id="tab-{n}"><caption><b>Table {n}.</b> '
            f"{caption}</caption><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>"
        )

    def references(self) -> str:
        items = []
        for i, k in enumerate(self.cited, 1):
            r = _REF[k]
            more = f" ({ext(r['extra'][1], r['extra'][0])})" if "extra" in r else ""
            items.append(f'<li id="ref-{i}">{r["text"]} {ext(r["url"], r["url"])}{more}</li>')
        return f'<ol class="refs">{"".join(items)}</ol>'
