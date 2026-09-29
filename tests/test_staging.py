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
    assert staging.staged_failures(out, "Aves", rows, 0.0) == []
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
    assert staging.staged_failures(out, "Aves", rows, 0.0) is None
    staging.stage_group(out, "Aves", rows, tmp_path / "cache")
    assert fetched.calls == ["https://example.test/3.jpg"]
    assert staging.staged_failures(out, "Aves", rows, 0.0) == []
    assert len(_members(out / "Aves.tar")) == 3


def test_changed_digest_invalidates_status_before_staging(tmp_path, fetched):
    rows = _pool([1])
    out = tmp_path / "photos"
    out.mkdir()
    staging.stage_group(out, "Aves", rows, tmp_path / "cache")
    fetched.broken.add("https://example.test/2.jpg")
    with pytest.raises(RuntimeError, match="1 of 2 photos failed"):
        staging.stage_group(out, "Aves", _pool([1, 2]), tmp_path / "cache")
    assert staging.staged_failures(out, "Aves", _pool([1, 2]), 0.0) is None
    assert staging.staged_failures(out, "Aves", rows, 0.0) is None


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


def test_unfetchable_limit_boundary():
    limit = staging.MAX_UNFETCHABLE_FRACTION
    assert staging.within_limit(0, 1, limit)
    assert staging.within_limit(0, 0, limit)
    assert staging.within_limit(1, 1000, limit)
    assert not staging.within_limit(2, 1000, limit)
    assert not staging.within_limit(1, 999, limit)


def test_failures_at_limit_are_recorded_and_complete_but_above_limit_stop(tmp_path, fetched):
    out = tmp_path / "photos"
    out.mkdir()
    rows = _pool([1, 2])
    fetched.broken.add("https://example.test/2.jpg")
    staging.stage_group(out, "Aves", rows, tmp_path / "cache", fraction=0.5)
    assert staging.staged_failures(out, "Aves", rows, 0.5) == [2]
    assert staging.staged_failures(out, "Aves", rows, 0.4) is None
    fetched.calls.clear()
    staging.stage_group(out, "Aves", rows, tmp_path / "cache", fraction=0.5)
    assert fetched.calls == []
    with pytest.raises(RuntimeError, match="1 of 2 photos failed, above the 40.0%"):
        staging.stage_group(out, "Aves", rows, tmp_path / "cache", fraction=0.4)
    assert staging.staged_failures(out, "Aves", rows, 0.4) is None


def test_reference_stages_completely_or_stops(tmp_path, fetched):
    pool, reference = tmp_path / "pool.parquet", tmp_path / "reference.parquet"
    _pool(range(1, 1001)).to_parquet(pool)
    _pool(range(2001, 3001)).to_parquet(reference)
    fetched.broken.update({"https://example.test/5.jpg", "https://example.test/2005.jpg"})
    sources = {"candidate": pool, "reference": reference}
    with pytest.raises(RuntimeError, match="Aves: 1 of 1000 photos failed, above the 0.0%"):
        staging.stage(tmp_path / "run", sources, tmp_path / "cache")
    assert staging.staged_failures(
        tmp_path / "run/photos/candidate",
        "Aves",
        pd.read_parquet(pool),
        staging.MAX_UNFETCHABLE_FRACTION,
    ) == [5]


def test_check_excludes_unfetchable_candidates_from_the_prepared_pool(tmp_path, fetched):
    run = tmp_path / "run"
    pool, reference = tmp_path / "pool.parquet", tmp_path / "reference.parquet"
    rows = pd.concat([_pool(range(1, 1001)), _pool([4001, 4002], "Plantae")], ignore_index=True)
    rows.to_parquet(pool)
    _pool([5001]).to_parquet(reference)
    sources = {"candidate": pool, "reference": reference}
    fetched.broken.add("https://example.test/7.jpg")
    staging.stage(run, sources, tmp_path / "cache")
    eligible = staging.check(run, sources)
    assert eligible == run / "pool.eligible.parquet"
    kept = pd.read_parquet(eligible)
    assert kept.id.tolist() == [i for i in rows.id if i != 7]
    assert kept.dtypes.equals(rows.dtypes)
    assert json.loads((run / "excluded.json").read_text()) == {
        "schema_version": 1,
        "pool_sha256": staging.sha256_file(pool),
        "eligible_pool_sha256": staging.sha256_file(eligible),
        "max_unfetchable_fraction": staging.MAX_UNFETCHABLE_FRACTION,
        "excluded": {"Aves": [7]},
    }
    # a rerun reproduces the same bytes, so a started preparation still recognises its pool
    before = staging.sha256_file(eligible)
    assert staging.check(run, sources) == eligible and staging.sha256_file(eligible) == before
    # a later retry that fetches the photo leaves the original pool, dropping the stale derivative
    fetched.broken.clear()
    (run / "photos/candidate/Aves.json").unlink()
    staging.stage(run, sources, tmp_path / "cache")
    assert staging.check(run, sources) == pool
    assert not eligible.exists()
    assert json.loads((run / "excluded.json").read_text())["excluded"] == {}
