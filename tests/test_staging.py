"""Per-group photo archive identity, resume and preparation checks."""

from __future__ import annotations

import io
import json
import tarfile

import numpy as np
import pandas as pd
import pytest

from what_to_id import embed, staging

Image = pytest.importorskip("PIL.Image")


def _jpeg() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (2, 2), "green").save(out, format="JPEG")
    return out.getvalue()


def _pool(ids, taxon="Aves"):
    return pd.DataFrame(
        {
            "id": np.asarray(ids, dtype=np.int64),
            "iconic_taxon": taxon,
            "photo_url": [f"https://example.test/{i}.jpg" for i in ids],
        }
    )


@pytest.fixture
def fetched(monkeypatch):
    """Serve a valid JPEG for every URL except those listed in ``fetched.broken``."""
    calls = []
    broken = set()

    class _Resp:
        def __init__(self, url):
            self.status_code = 500 if url in broken else 200
            self.content = _jpeg()

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"http {self.status_code}")

    def get(url, timeout=None, headers=None):
        calls.append(url)
        return _Resp(url)

    monkeypatch.setattr(embed.requests, "get", get)
    monkeypatch.setattr(embed.time, "sleep", lambda _: None)
    monkeypatch.setenv("COPYFILE_DISABLE", "1")  # no AppleDouble members from macOS tar
    get.calls, get.broken = calls, broken
    return get


def _members(archive):
    with tarfile.open(archive) as source:
        return sorted(m.name for m in source.getmembers() if m.isfile())


def test_digest_ignores_row_order_and_frame_but_tracks_urls():
    rows = _pool([3, 1, 2])
    assert staging.staged_rows_digest(rows) == staging.staged_rows_digest(rows.iloc[::-1])
    changed = rows.copy()
    changed.loc[0, "photo_url"] = "https://example.test/other.jpg"
    assert staging.staged_rows_digest(changed) != staging.staged_rows_digest(rows)
    # the same group rows drawn from a partial and a fuller pool, with other dtypes and index
    partial = pd.concat([_pool([1, 2, 3]), _pool([9], "Insecta")], ignore_index=True)
    full = pd.concat([_pool([7], "Plantae"), _pool([2, 3, 1]), _pool([9, 8], "Insecta")])
    full["id"] = full["id"].astype("int32")
    a = dict(tuple(partial.groupby("iconic_taxon")))["Aves"]
    b = dict(tuple(full.groupby("iconic_taxon")))["Aves"]
    assert staging.staged_rows_digest(a) == staging.staged_rows_digest(b)


def test_stage_binds_group_to_rows_and_skips_on_rerun(tmp_path, fetched):
    rows = _pool([1, 2])
    out = tmp_path / "photos"
    out.mkdir()
    staging.stage_group(out, "Aves", rows, tmp_path / "cache")
    status = json.loads((out / "Aves.json").read_text())
    assert status == {
        "expected": 2,
        "rows_sha256": staging.staged_rows_digest(rows),
        "failures": [],
    }
    assert len(_members(out / "Aves.tar")) == 2
    assert staging.group_is_staged(out, "Aves", rows)
    fetched.calls.clear()
    staging.stage_group(out, "Aves", rows, tmp_path / "cache")
    assert fetched.calls == []


def test_foreign_archive_is_resumed_fetching_only_missing_rows(tmp_path, fetched):
    old = _pool([1, 2])
    source = tmp_path / "old"
    source.mkdir()
    staging.stage_group(source, "Aves", old, tmp_path / "cache")
    out = tmp_path / "new"
    out.mkdir()
    # copied from another run without its status: rows 1 and 2 are reused, only 3 is fetched
    (out / "Aves.tar").write_bytes((source / "Aves.tar").read_bytes())
    rows = _pool([1, 2, 3])
    fetched.calls.clear()
    assert not staging.group_is_staged(out, "Aves", rows)
    staging.stage_group(out, "Aves", rows, tmp_path / "cache")
    assert fetched.calls == ["https://example.test/3.jpg"]
    assert staging.group_is_staged(out, "Aves", rows)
    assert len(_members(out / "Aves.tar")) == 3


def test_changed_digest_invalidates_status_before_staging(tmp_path, fetched):
    rows = _pool([1])
    out = tmp_path / "photos"
    out.mkdir()
    staging.stage_group(out, "Aves", rows, tmp_path / "cache")
    fetched.broken.add("https://example.test/2.jpg")
    with pytest.raises(RuntimeError, match="1 photos failed"):
        staging.stage_group(out, "Aves", _pool([1, 2]), tmp_path / "cache")
    assert not staging.group_is_staged(out, "Aves", _pool([1, 2]))
    assert not staging.group_is_staged(out, "Aves", rows)


def test_check_requires_every_group_bound_to_current_rows(tmp_path, fetched):
    pool, reference = tmp_path / "pool.parquet", tmp_path / "reference.parquet"
    _pool([1, 2]).to_parquet(pool)
    _pool([5]).to_parquet(reference)
    staging.stage(tmp_path / "run", {"candidate": pool, "reference": reference}, tmp_path / "c")
    sources = {"candidate": pool, "reference": reference}
    staging.check(tmp_path / "run", sources)
    pd.concat([_pool([1, 2]), _pool([4], "Plantae")]).to_parquet(pool)
    with pytest.raises(ValueError, match="candidate photo archive for Plantae"):
        staging.check(tmp_path / "run", sources)
    staging.stage(tmp_path / "run", sources, tmp_path / "c")
    staging.check(tmp_path / "run", sources)
