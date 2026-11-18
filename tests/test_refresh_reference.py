import json
from pathlib import Path

import pytest
import refresh_reference as rr

OLD = {"invasive_bc_taxa": [1, 2], "at_risk_bc_taxa": [[10, 1, 5], [11, 3, 0]]}


def _write(path, rows, fetched):
    path.write_text(json.dumps({"fetched": fetched, "taxa": rows}))


@pytest.fixture
def run(tmp_path, monkeypatch):
    """main() with each fetcher replaced by one that writes the `new` rows over the `old` ones."""

    def go(new):
        out = tmp_path / "gh_output"
        monkeypatch.setattr(rr.rc, "DATA", tmp_path)
        monkeypatch.setattr(rr, "names", lambda taxa: {})
        monkeypatch.setattr(rr.sys, "argv", ["refresh_reference.py", str(tmp_path / "s.md")])
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        for name, rows in OLD.items():
            _write(tmp_path / f"{name}.json", rows, "2026-01-01")

        def fetch(cmd, **kw):
            name = Path(cmd[1]).stem
            _write(tmp_path / f"{name}.json", new[name], "2026-02-02")

        monkeypatch.setattr(rr.subprocess, "run", fetch)
        rr.main()
        return out.read_text().strip(), (tmp_path / "s.md").read_text()

    return go


def test_counts_and_dates_alone_open_no_pr(run):
    flag, _ = run({**OLD, "at_risk_bc_taxa": [[10, 1, 99], [11, 3, 7]]})
    assert flag == "changed=false"


def test_a_tier_change_opens_a_pr(run):
    flag, md = run({**OLD, "at_risk_bc_taxa": [[10, 2, 5], [11, 3, 0]]})
    assert flag == "changed=true" and "1 changed tier" in md


def test_an_added_taxon_opens_a_pr(run):
    assert run({**OLD, "invasive_bc_taxa": [1, 2, 3]})[0] == "changed=true"
