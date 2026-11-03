"""Each data file is named by its own bytes; a deploy keeps the live site's files one more round."""

import gzip

import pytest

from what_to_id import site_files
from what_to_id.page_map import write_map

from .conftest import make_pool


def _meta(site):
    return site_files.read_meta((site / site_files.MAP_NAME).read_text())


def test_new_levels_bytes_change_only_the_levels_name(tmp_path):
    write_map(tmp_path, make_pool(40))
    site_files.publish(tmp_path, "levels", "pool-levels.bin", gzip.compress(b"\1\2", mtime=0))
    site_files.publish(tmp_path, "looks", "pool-levels-looks.bin", gzip.compress(b"x", mtime=0))
    before = _meta(tmp_path)
    site_files.publish(tmp_path, "levels", "pool-levels.bin", gzip.compress(b"\1\3", mtime=0))
    after = _meta(tmp_path)
    assert after["files"]["levels"] != before["files"]["levels"]
    assert {**after, "files": {}} == {**before, "files": {}}  # shards, taxa, observer stay
    assert after["files"]["looks"] == before["files"]["looks"]
    assert (tmp_path / after["files"]["levels"]).read_bytes() == gzip.compress(b"\1\3", mtime=0)
    site_files.publish(tmp_path, "looks", "pool-levels-looks.bin", None)
    assert "looks" not in _meta(tmp_path)["files"] and site_files.path(tmp_path, "looks") is None


def test_keep_copies_the_live_generation_and_drops_older_ones(tmp_path):
    live, new = tmp_path / "live", tmp_path / "new"
    write_map(live, make_pool(40, seed=1))
    site_files.publish(live, "levels", "pool-levels.bin", b"old levels")
    (live / "pool-levels.000000000000.bin").write_bytes(b"two deploys ago")  # not in live META
    write_map(new, make_pool(40, seed=2))
    site_files.publish(new, "levels", "pool-levels.bin", b"new levels")
    built = {p.name for p in new.iterdir()}
    served = {"https://x.io/site/" + p.name: p.read_bytes() for p in live.iterdir()}
    kept = site_files.keep(new, "https://x.io/site", served.__getitem__)
    previous = set(site_files.data_files(_meta(live)))
    assert {p.name for p in new.iterdir()} == built | previous
    assert set(kept) == previous - built and "pool-levels.000000000000.bin" not in kept
    assert all((new / n).read_bytes() == (live / n).read_bytes() for n in previous)


def test_keep_reads_a_page_from_before_the_hashed_names_and_refuses_a_path(tmp_path):
    meta = {"shards": [{"file": "pool-0.bin?v=abc", "n": 1}], "taxa": "../x.bin?v=abc"}
    page = f"<script>var META={site_files.dump(meta)};var BASEMAPS={{}};".encode()
    get = {"u/map.html": page, "u/pool-0.bin": b"0"}.__getitem__
    with pytest.raises(ValueError, match="plain file name"):
        site_files.keep(tmp_path, "u", get)
    assert (tmp_path / "pool-0.bin").read_bytes() == b"0"
