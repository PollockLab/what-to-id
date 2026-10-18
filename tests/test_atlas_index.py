"""Tests for the static IVF-PQ atlas index on synthetic clustered unit vectors."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from what_to_id import atlas_index as ai
from what_to_id.atlas_index_io import load_core

from .atlas_index_fixture import clustered_unit, write_fixture

faiss = pytest.importorskip("faiss")

N, D, NLIST, M = 5000, 64, 32, 16


@pytest.fixture(scope="module")
def data():
    E = clustered_unit(N, D, 40, seed=3, noise=0.8)
    ids = np.random.default_rng(4).choice(2**32 - 1, N, replace=False)
    return E, ids


@pytest.fixture(scope="module")
def built(tmp_path_factory, data):
    E, ids = data
    out = tmp_path_factory.mktemp("idx")
    ai.build(E, ids, out, nlist=NLIST, m=M, train_size=N, model={"id": "t"})
    return out


@pytest.fixture
def index(tmp_path, built):
    """A private copy of the built index that a test may mutate."""
    dest = tmp_path / "idx"
    dest.mkdir()
    for f in built.iterdir():
        (dest / f.name).write_bytes(f.read_bytes())
    return dest


def test_layout_sizes_and_dtypes(built, data):
    _, ids = data
    man = json.loads((built / "manifest.json").read_text())
    assert (man["version"], man["dims"], man["nlist"], man["m"]) == (1, D, NLIST, M)
    assert (man["nbits"], man["metric"], man["by_residual"], man["count"]) == (8, "ip", True, N)
    assert man["model"] == {"id": "t"}
    assert man["parts"][0]["name"] == "base" and man["parts"][0]["count"] == N
    assert (built / "centroids.f16").stat().st_size == NLIST * D * 2
    assert (built / "pq.f32").stat().st_size == M * 256 * (D // M) * 4
    assert (built / "base.offsets.u32").stat().st_size == (NLIST + 1) * 4
    assert (built / "base.ids.u32").stat().st_size == N * 4
    assert (built / "base.codes.u8").stat().st_size == N * M
    offsets = np.fromfile(built / "base.offsets.u32", dtype="<u4")
    assert offsets[0] == 0 and offsets[-1] == N and np.all(np.diff(offsets.astype(np.int64)) >= 0)
    assert sorted(np.fromfile(built / "base.ids.u32", dtype="<u4")) == sorted(ids)
    assert not list(built.glob("*.tmp"))


def test_rows_sit_in_their_nearest_list(built, data):
    E, ids = data
    c, _ = load_core(built, json.loads((built / "manifest.json").read_text()))
    offsets = np.fromfile(built / "base.offsets.u32", dtype="<u4").astype(int)
    stored = np.fromfile(built / "base.ids.u32", dtype="<u4")
    by_id = dict(zip(ids.tolist(), range(N), strict=True))
    for lst in (0, 7, NLIST - 1):
        rows = [by_id[i] for i in stored[offsets[lst] : offsets[lst + 1]].tolist()]
        if rows:
            assert np.all((E[rows] @ c.T).argmax(1) == lst)


def test_adc_scores_match_faiss(built, data):
    E, ids = data
    man = json.loads((built / "manifest.json").read_text())
    c, pq = load_core(built, man)
    quantizer = faiss.IndexFlatIP(D)
    quantizer.add(c)
    ref = faiss.IndexIVFPQ(quantizer, D, NLIST, M, 8, faiss.METRIC_INNER_PRODUCT)
    faiss.copy_array_to_vector(pq.ravel(), ref.pq.centroids)
    ref.is_trained = True
    ref.add_with_ids(E, ids.astype(np.int64))
    ref.nprobe = 8
    Q = E[::500][:10]
    want_s, want_i = ref.search(Q, 10)
    got_i, got_s = ai.search(built, Q, 10, 8)
    np.testing.assert_allclose(got_s, want_s, atol=1e-4)
    assert (got_i == want_i).mean() > 0.95


def test_recall_vs_exact(built, data):
    E, ids = data
    r = ai.recall_at_k(built, E, ids, k=10, nprobe=8, n_queries=200)
    assert r > 0.6
    # Probing every list removes the IVF loss, leaving only PQ error.
    assert ai.recall_at_k(built, E, ids, k=10, nprobe=NLIST, n_queries=200) >= r


def test_search_pads_and_clamps(built, data):
    E, _ = data
    found, scores = ai.search(built, E[:1], k=5, nprobe=10_000)
    assert found.shape == (1, 5) and np.all(np.diff(scores[0]) <= 0)
    found, scores = ai.search(built, E[0], k=N + 10, nprobe=NLIST)  # 1-D query, k > rows
    assert (found[0] >= 0).sum() == N and found[0, -1] == -1 and scores[0, -1] == -np.inf


def test_append_then_search_finds_new(index, data):
    E, ids = data
    new = clustered_unit(100, D, 40, seed=9, noise=0.8)
    new_ids = np.arange(100, dtype=np.int64) + 10**6
    man = ai.append(index, "delta-20260102", new, new_ids)
    assert man["count"] == N + 100 and [p["name"] for p in man["parts"]] == [
        "base",
        "delta-20260102",
    ]
    assert (index / "delta-20260102.ids.u32").stat().st_size == 400
    assert (index / "delta-20260102.codes.u8").stat().st_size == 100 * M
    found, _ = ai.search(index, new, 10, NLIST)
    assert np.mean([new_ids[i] in found[i] for i in range(100)]) > 0.9
    with pytest.raises(ValueError, match="already exists"):
        ai.append(index, "delta-20260102", new, new_ids + 1)
    with pytest.raises(ValueError, match="already in the index"):
        ai.append(index, "delta-x", new, ids[:100])
    with pytest.raises(ValueError, match="invalid part name"):
        ai.append(index, "../evil", new, new_ids + 5)


def test_compact_preserves_results_and_drops(index, data):
    E, ids = data
    new = clustered_unit(100, D, 40, seed=9, noise=0.8)
    new_ids = np.arange(100, dtype=np.int64) + 10**6
    ai.append(index, "delta-a", new[:50], new_ids[:50])
    ai.append(index, "delta-b", new[50:], new_ids[50:])
    Q = np.vstack([E[:5], new[:5]])
    before = ai.search(index, Q, 10, 8)
    man = ai.compact(index)
    assert man["parts"][0]["name"] == "base" and len(man["parts"]) == 1 and man["count"] == N + 100
    assert not list(index.glob("delta-*")) and not list(index.glob("*.tmp"))
    after = ai.search(index, Q, 10, 8)
    np.testing.assert_allclose(after[1], before[1], atol=1e-5)
    assert (after[0] == before[0]).mean() > 0.98

    drop = np.concatenate([ids[:200], new_ids[:10]])
    keep = np.setdiff1d(np.concatenate([ids, new_ids]), drop)
    man = ai.compact(index, keep_ids=keep)
    assert man["count"] == N + 100 - 210
    assert (index / "base.ids.u32").stat().st_size == man["count"] * 4
    found, _ = ai.search(index, E[:50], 10, NLIST)
    assert not np.isin(found, drop).any()
    assert ai.compact(index, keep_ids=[])["count"] == 0
    assert (ai.search(index, E[:2], 3, 4)[0] == -1).all()


def test_neighbors_match_brute_force_and_lookup(index, data):
    E, ids = data
    n = 600
    entry = ai.neighbors(E[:n], ids[:n], index, k=12, block=100, device="numpy")
    assert entry == {"name": "neighbors", "count": n, "block": 100, "k": 12}
    assert (index / "neighbors.bin").stat().st_size == n * 76
    order = np.argsort(ids[:n])
    directory = np.fromfile(index / "neighbors.dir.u32", dtype="<u4")
    np.testing.assert_array_equal(directory, ids[:n][order][::100])
    sims = E[:n] @ E[:n].T
    np.fill_diagonal(sims, -np.inf)
    for row in (0, 17, 599):
        ids_nb, cos = ai.lookup_neighbors(index, int(ids[row]))
        top = np.argsort(-sims[row])[:12]
        np.testing.assert_array_equal(ids_nb, ids[:n][top])
        np.testing.assert_allclose(cos, sims[row][top], atol=2e-3)
    for missing in (0, int(ids[:n].max()) + 1):
        assert ai.lookup_neighbors(index, missing) is None
    man = json.loads((index / "manifest.json").read_text())
    assert man["neighbors"] == [entry]
    ai.neighbors(E[:n], ids[:n], index, k=12, block=100, device="numpy")  # re-register in place
    assert len(json.loads((index / "manifest.json").read_text())["neighbors"]) == 1
    with pytest.raises(KeyError):
        ai.lookup_neighbors(index, 5, name="other")


def test_neighbors_normalizes_and_checks_size(index, data):
    E, ids = data
    with pytest.raises(ValueError, match="more than k"):
        ai.neighbors(E[:12], ids[:12], index, k=12, device="numpy")
    with pytest.raises(ValueError, match="dims mismatch"):
        ai.neighbors(E[:50, :32], ids[:50], index, device="numpy")


def test_build_errors(tmp_path, data):
    E, ids = data
    with pytest.raises(ValueError, match="dims .* not divisible"):
        ai.build(E, ids, tmp_path / "a", m=10)
    with pytest.raises(ValueError, match="empty input"):
        ai.build(E[:0], ids[:0], tmp_path / "b", m=M)
    with pytest.raises(ValueError, match="duplicate ids"):
        ai.build(E[:300], np.zeros(300, dtype=np.int64), tmp_path / "c", m=M)
    with pytest.raises(ValueError, match="uint32"):
        ai.build(E[:300], np.arange(300) + 2**32, tmp_path / "d", m=M)
    with pytest.raises(ValueError, match="uint32"):
        ai.build(E[:300], np.arange(300) - 1, tmp_path / "d", m=M)
    with pytest.raises(ValueError, match="integers"):
        ai.build(E[:300], np.arange(300, dtype=np.float64), tmp_path / "d", m=M)
    with pytest.raises(ValueError, match="1-D"):
        ai.build(E[:300], ids[:299], tmp_path / "d", m=M)
    with pytest.raises(ValueError, match="at least 256"):
        ai.build(E[:100], ids[:100], tmp_path / "e", m=M)
    with pytest.raises(ValueError, match="2-D"):
        ai.build(E[0], ids[:1], tmp_path / "f", m=M)
    assert not (tmp_path / "a" / "manifest.json").exists()


def test_build_clamps_nlist_and_normalizes(tmp_path, data, caplog):
    E, ids = data
    scaled = (E[:300] * 3.0).astype(np.float32)
    with caplog.at_level(logging.WARNING, logger="what_to_id"):
        man = ai.build(scaled, ids[:300], tmp_path / "s", nlist=4096, m=M)
    assert man["nlist"] == 300
    assert "clamped" in caplog.text and "not unit-norm" in caplog.text
    assert (tmp_path / "s" / "centroids.f16").stat().st_size == 300 * D * 2
    found, _ = ai.search(tmp_path / "s", E[:3], 3, 300)
    assert found.shape == (3, 3)


def test_search_and_append_errors(index, data):
    E, ids = data
    with pytest.raises(ValueError, match="dims mismatch"):
        ai.search(index, np.zeros((1, D + 1), dtype=np.float32), 5, 4)
    with pytest.raises(ValueError, match="dims mismatch"):
        ai.append(index, "delta-z", E[:5, :32], ids[:5])
    with pytest.raises(ValueError, match="empty input"):
        ai.append(index, "delta-z", E[:0], ids[:0])
    with pytest.raises(FileNotFoundError, match="build the index first"):
        ai.search(index / "nope", E[:1], 5, 4)


def test_write_fixture_and_reference(tmp_path):
    ref = write_fixture(tmp_path / "fx")
    out = tmp_path / "fx"
    man = json.loads((out / "manifest.json").read_text())
    assert (man["dims"], man["nlist"], man["m"], man["count"]) == (1024, 16, 64, 2200)
    assert [p["name"] for p in man["parts"]] == ["base", "delta-20260101"]
    assert man["neighbors"] == [{"name": "neighbors", "count": 2200, "block": 256, "k": 12}]
    assert (out / "neighbors.bin").stat().st_size == 2200 * 76
    assert (out / "pq.f32").stat().st_size == 64 * 256 * 16 * 4
    saved = json.loads((out / "reference.json").read_text())
    assert saved["k"] == 10 and len(saved["queries"]) == 8
    q = np.asarray(saved["queries"], dtype=np.float32)
    for s in saved["searches"]:
        found, scores = ai.search(out, q, saved["k"], s["nprobe"])
        assert found.tolist() == s["ids"]
        np.testing.assert_array_equal(scores, np.asarray(s["scores"], dtype=np.float32))
    assert saved["lookups"][-1]["neighbors"] is None and saved["lookups"][0]["neighbors"]
    assert ref["searches"][0]["nprobe"] == 1
    # The generator is deterministic and runnable as a script for the JS tests.
    again = tmp_path / "fx2"
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, str(root / "tests" / "atlas_index_fixture.py"), str(again)],
        check=True,
        env=os.environ | {"PYTHONPATH": str(root / "src")},
    )
    assert (again / "reference.json").read_text() == (out / "reference.json").read_text()


def test_cli_roundtrip(tmp_path, data, capsys):
    E, ids = data
    np.save(tmp_path / "E.npy", E[:1000])
    np.save(tmp_path / "ids.npy", ids[:1000])
    idx = str(tmp_path / "idx")
    base = ["--index", idx]
    src = ["--E", str(tmp_path / "E.npy"), "--ids", str(tmp_path / "ids.npy")]
    ai.main(["build", *base, *src, "--nlist", "8", "--m", str(M)])
    ai.main(["neighbors", *base, *src, "--k", "5", "--device", "numpy"])
    np.save(tmp_path / "Q.npy", E[:2])
    ai.main(["search", *base, "--queries", str(tmp_path / "Q.npy"), "--k", "3", "--nprobe", "8"])
    out = capsys.readouterr().out.strip().splitlines()
    assert len(json.loads(out[-1])["ids"]) == 2
    ai.main(["recall", *base, *src, "--n-queries", "50", "--nprobe", "8"])
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["recall"] > 0.5
    ai.main(["compact", *base])
