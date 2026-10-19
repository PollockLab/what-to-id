"""Tests for the 2D layout parts: format, placement of new observations, compaction, manifest."""

from __future__ import annotations

import gzip
import json
import shutil

import numpy as np
import pandas as pd
import pytest

from what_to_id import atlas_index as ai
from what_to_id import atlas_layout as al
from what_to_id import atlas_update as au

from .atlas_index_fixture import FIXTURE_DIMS, clustered_unit, write_fixture
from .test_atlas_update import encode_all, make_pool

faiss = pytest.importorskip("faiss")

BBOX = [-10.0, 5.0, 30.0, 25.0]


def new_vectors(n=40):
    return dict(zip(range(100, 100 + n), clustered_unit(n, FIXTURE_DIMS, 24, seed=0), strict=True))


# ---- format -----------------------------------------------------------------------------
def test_round_trip_unsorted_ids_and_big_steps(tmp_path):
    ids = np.array([4_000_000_000, 7, 70_000, 70_001, 0, 2**32 - 1])  # steps beyond 65535 and 2**24
    xy = np.random.default_rng(0).uniform([-10, 5], [30, 25], (len(ids), 2)).astype(np.float32)
    path = tmp_path / "p.bin"
    assert al.write_part(path, ids, xy, BBOX) == len(ids)
    assert len(gzip.decompress(path.read_bytes())) == 8 * len(ids)
    got_ids, got_xy = al.read_part(path, len(ids), BBOX)
    order = np.argsort(ids)
    np.testing.assert_array_equal(got_ids, ids[order])
    assert got_ids.dtype == np.int64
    half_cell = np.array([40, 20]) / 65535 / 2 + 1e-5
    assert (np.abs(got_xy - xy[order]) <= half_cell).all()
    with pytest.raises(ValueError, match="expected"):
        al.read_part(path, len(ids) + 1, BBOX)


def test_empty_part_duplicates_and_bad_input(tmp_path):
    al.write_part(tmp_path / "e.bin", [], np.empty((0, 2)), BBOX)
    ids, xy = al.read_part(tmp_path / "e.bin", 0, BBOX)
    assert ids.shape == (0,) and xy.shape == (0, 2)
    with pytest.raises(ValueError, match="duplicate"):
        al.write_part(tmp_path / "d.bin", [1, 1], np.zeros((2, 2)), BBOX)
    with pytest.raises(ValueError, match="uint32"):
        al.write_part(tmp_path / "d.bin", [2**32], np.zeros((1, 2)), BBOX)
    with pytest.raises(ValueError, match="shape"):
        al.write_part(tmp_path / "d.bin", [1, 2], np.zeros((3, 2)), BBOX)


def test_quantization_bound_clamp_and_degenerate_span():
    v = np.linspace(-3, 9, 1001)
    err = np.abs(al.dequantize(al.quantize(v, -3, 9), -3, 9) - v)
    assert err.max() <= 12 / 65535 / 2 + 1e-5
    assert al.quantize([-100, 100], -3, 9).tolist() == [0, 65535]
    assert al.dequantize(al.quantize([5.0], 5.0, 5.0), 5.0, 5.0)[0] == 5.0


# ---- place ------------------------------------------------------------------------------
def test_place_weighted_mean_and_unknown_neighbours():
    known_ids, known_xy = np.array([10, 20, 30]), np.array([[0, 0], [10, 0], [0, 10]], "f4")
    nb = np.array([[10, 20, 99], [98, 99, 97], [10, 20, 30]])
    cos = np.array([[0.75, 0.25, 0.9], [0.9, 0.9, 0.9], [-0.5, -0.5, -0.5]])
    ids, xy = al.place([1, 2, 3], nb, cos, known_ids, known_xy)
    assert ids.tolist() == [1, 3]  # row 2 has no known neighbour: not placed
    np.testing.assert_allclose(xy[0], [2.5, 0])  # 99 skipped; weights 0.75, 0.25
    np.testing.assert_allclose(xy[1], [10 / 3, 10 / 3])  # all weights 0: plain mean of the known
    ids, xy = al.place([1], nb[:1], cos[:1], np.array([], np.int64), np.empty((0, 2)))
    assert len(ids) == 0 and xy.shape == (0, 2)
    ids, _ = al.place([], nb[:0], cos[:0], known_ids, known_xy)
    assert len(ids) == 0
    ids, xy = al.place([1], [[10, 20]], [[1.0, -1.0]], known_ids, known_xy)  # negative cos ignored
    np.testing.assert_allclose(xy[0], [0, 0])


# ---- base cli, manifest, update ---------------------------------------------------------
@pytest.fixture(scope="module")
def fixture_index(tmp_path_factory):
    out = tmp_path_factory.mktemp("fixture")
    write_fixture(out)
    return out


@pytest.fixture
def index(tmp_path, fixture_index):
    dest = tmp_path / "index"
    shutil.copytree(fixture_index, dest)
    return dest


@pytest.fixture
def laid_out(index, tmp_path):
    """The fixture index with a base layout written through the CLI and an unknown manifest key."""
    m = ai.read_manifest(index)
    m["unknown"] = {"keep": [1, 2]}
    ai.write_manifest(index, m)
    ids = ai._existing_ids(index, m).astype(np.int64)
    xy = np.random.default_rng(3).uniform(-50, 50, (len(ids), 2)).astype(np.float32)
    np.save(tmp_path / "ids.npy", ids)
    np.save(tmp_path / "xy.npy", xy)
    (tmp_path / "fid.json").write_text(json.dumps({"top12": 0.5}))
    argv = ["base", "--xy", str(tmp_path / "xy.npy"), "--ids", str(tmp_path / "ids.npy")]
    argv += ["--out", str(index), "--method", "test", "--fidelity", str(tmp_path / "fid.json")]
    assert al.main(argv) == 0
    return index, ids, xy


def test_base_cli_writes_part_and_keeps_manifest_keys(laid_out):
    index, ids, xy = laid_out
    m = ai.read_manifest(index)
    lay = m["layout"]
    assert m["unknown"] == {"keep": [1, 2]} and m["count"] == len(ids)
    assert lay["version"] == 1 and lay["method"] == "test" and lay["fidelity"] == {"top12": 0.5}
    assert lay["bbox"] == [*xy.min(axis=0).tolist(), *xy.max(axis=0).tolist()]
    assert lay["parts"] == [{"name": "layout-base", "count": len(ids)}]
    got_ids, got_xy = al.read_part(index / "layout-base.bin", len(ids), lay["bbox"])
    order = np.argsort(ids)
    np.testing.assert_array_equal(got_ids, ids[order])
    assert np.abs(got_xy - xy[order]).max() < 100 / 65535


def test_base_cli_errors(index, tmp_path, capsys):
    np.save(tmp_path / "ids.npy", np.array([1, 2]))
    np.save(tmp_path / "xy.npy", np.array([[0, 0], [np.nan, 1]], "f4"))
    argv = ["base", "--xy", str(tmp_path / "xy.npy"), "--ids", str(tmp_path / "ids.npy")]
    assert al.main([*argv, "--out", str(index), "--method", "t"]) == 1
    assert "non-finite" in capsys.readouterr().err
    assert al.main([*argv, "--out", str(tmp_path / "nope"), "--method", "t"]) == 1


def test_apply_places_new_rows_and_keeps_the_layout_key(laid_out, tmp_path):
    index, _, xy = laid_out
    new = new_vectors()
    pool, _ = make_pool(index, new, tmp_path)
    files = encode_all(new, tmp_path)
    r = au.apply(index, files, pool, "delta-20260301", raw_out=tmp_path / "r.npz")
    m = ai.read_manifest(index)
    names = [p["name"] for p in m["layout"]["parts"]]
    assert names == ["layout-base", "layout-delta-20260301"] and m["unknown"] == {"keep": [1, 2]}
    assert r["placed"] == m["layout"]["parts"][1]["count"] > 0
    pid, pxy = al.read_part(index / "layout-delta-20260301.bin", r["placed"], m["layout"]["bbox"])
    assert np.isin(pid, list(new)).all()
    assert ((pxy >= xy.min(axis=0) - 1e-3) & (pxy <= xy.max(axis=0) + 1e-3)).all()


def test_apply_without_new_rows_writes_no_layout_part(laid_out, tmp_path):
    index, _, _ = laid_out
    pool, _ = make_pool(index, {}, tmp_path)
    r = au.apply(index, [], pool, "delta-20260301")
    assert "placed" not in r
    assert [p["name"] for p in ai.read_manifest(index)["layout"]["parts"]] == ["layout-base"]
    assert not list(index.glob("layout-delta*"))


def test_place_delta_second_pass_uses_same_day_neighbours(laid_out):
    index, ids, _ = laid_out
    new = np.array([5, 6])
    nb = np.array([[6, 6], [ids[0], ids[0]]])  # 5 sees only 6, which sees a base id
    layout = ai.read_manifest(index)["layout"]
    assert au._place_delta(index, layout, "delta-1", new, nb, np.full((2, 2), 0.5)) == 2
    m = ai.read_manifest(index)["layout"]
    assert m["parts"][-1] == {"name": "layout-delta-1", "count": 2}
    pid, pxy = al.read_part(index / "layout-delta-1.bin", 2, m["bbox"])
    np.testing.assert_allclose(pxy[0], pxy[1], atol=1e-4)  # 5 sits where 6 was placed


def test_compact_folds_layout_and_drops_ids_not_in_the_index(laid_out, tmp_path):
    index, _, _ = laid_out
    new = new_vectors()
    pool, _ = make_pool(index, new, tmp_path, drop_old=30)
    files = encode_all(new, tmp_path)
    r = au.apply(index, files, pool, "delta-20260301", compact=True, raw_out=tmp_path / "r.npz")
    m = ai.read_manifest(index)
    assert [p["name"] for p in m["layout"]["parts"]] == ["layout-base-20260301"]
    assert sorted(f.name for f in index.glob("layout-*")) == ["layout-base-20260301.bin"]
    part = m["layout"]["parts"][0]
    lid, _ = al.read_part(index / "layout-base-20260301.bin", part["count"], m["layout"]["bbox"])
    live = pd.read_parquet(pool)["id"].to_numpy()
    assert r["dropped"] == 30 and m["unknown"] == {"keep": [1, 2]}
    assert np.isin(lid, ai._existing_ids(index, m)).all() and np.isin(lid, live).all()
    assert part["count"] >= len(live) - len(new)  # every surviving base row keeps coordinates


def test_no_layout_key_changes_nothing(index, tmp_path):
    new = new_vectors(10)
    pool, _ = make_pool(index, new, tmp_path)
    files = encode_all(new, tmp_path)
    r = au.apply(index, files, pool, "delta-20260301", raw_out=tmp_path / "r.npz")
    assert "placed" not in r and "layout" not in ai.read_manifest(index)
    assert not list(index.glob("layout-*"))
