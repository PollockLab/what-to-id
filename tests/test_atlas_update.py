"""Tests for the daily atlas update: plan, sharded resumable encode, apply and the sync script.

A tiny fake encoder stands in for BioCLIP, so nothing here imports torch or touches the network.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from what_to_id import atlas_index as ai
from what_to_id import atlas_update as au
from what_to_id.atlas_neighbors import lookup_neighbors, merge_neighbors, write_neighbor_records
from what_to_id.atlas_update_encoder import Encoder

from .atlas_index_fixture import FIXTURE_DIMS, clustered_unit, write_fixture

faiss = pytest.importorskip("faiss")

D = FIXTURE_DIMS
N_NEW = 40
SYNC = Path(__file__).resolve().parents[1] / "scripts" / "atlas_sync.sh"


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


@pytest.fixture(scope="module")
def new_vectors():
    """N_NEW vectors near the fixture's cluster centres, keyed by observation id."""
    E = clustered_unit(N_NEW, D, 24, seed=0)
    ids = np.arange(100, 100 + N_NEW)  # fixture ids are random in uint32; a clash is negligible
    return dict(zip(ids.tolist(), E, strict=True))


def make_pool(index, new_vectors, tmp_path, *, drop_old=0, extra=None):
    """A pool of the index's ids (minus ``drop_old``) plus the new ids, created_at descending."""
    manifest = ai.read_manifest(index)
    old = ai._existing_ids(index, manifest).astype(np.int64)
    ids = np.concatenate([old[drop_old:], np.array(list(new_vectors), dtype=np.int64)])
    df = pd.DataFrame({"id": ids, "photo_url": [f"https://x/{i}.jpg" for i in ids]})
    # new ids get later dates the larger the id, so "oldest first" is ascending id among them
    df["created_at"] = [f"2026-01-{1 + (i % 28):02d}T00:00:00Z" for i in range(len(df))]
    if extra is not None:
        df = pd.concat([df, extra], ignore_index=True)
    path = tmp_path / "pool.parquet"
    df.to_parquet(path)
    return path, old


def fake_factory(new_vectors, calls=None, bad=(), info=None):
    info = info or {"id": "fixture", "revision": "0"}

    def encode(ids, urls):
        if calls is not None:
            calls.extend(ids)
        ok = [i for i in ids if i not in bad]
        E = np.stack([new_vectors[i] for i in ok]) if ok else np.empty((0, D), dtype=np.float32)
        return ok, E, [(i, "boom") for i in ids if i in bad]

    return lambda work, threads: Encoder(encode, info, D)


def write_todo(path, ids):
    path.write_text(json.dumps({"ids": list(ids), "urls": [f"https://x/{i}.jpg" for i in ids]}))


# ---- plan -------------------------------------------------------------------------------
def test_plan_new_removed_cap_and_empty(index, new_vectors, tmp_path):
    pool, old = make_pool(index, new_vectors, tmp_path, drop_old=5)
    out = tmp_path / "todo.json"
    summary = au.plan(pool, index, out)
    todo = json.loads(out.read_text())
    assert (summary["new"], summary["removed"], summary["planned"]) == (N_NEW, 5, N_NEW)
    assert sorted(todo["ids"]) == sorted(new_vectors) and len(todo["urls"]) == N_NEW
    df = pd.read_parquet(pool).set_index("id")
    dates = df.loc[todo["ids"], "created_at"].tolist()
    assert dates == sorted(dates)  # oldest first

    capped = au.plan(pool, index, out, max_new=7)
    assert (capped["new"], capped["planned"]) == (N_NEW, 7)
    assert json.loads(out.read_text())["ids"] == todo["ids"][:7]

    pool_same, _ = make_pool(index, {}, tmp_path)
    empty = au.plan(pool_same, index, out)
    assert (empty["new"], empty["planned"], empty["removed"]) == (0, 0, 0)
    assert json.loads(out.read_text())["ids"] == []


def test_plan_skips_rows_without_a_photo_and_rejects_duplicates(index, new_vectors, tmp_path):
    extra = pd.DataFrame({"id": [7, 8], "photo_url": [None, ""], "created_at": ["2026-01-01"] * 2})
    pool, _ = make_pool(index, new_vectors, tmp_path, extra=extra)
    summary = au.plan(pool, index, tmp_path / "todo.json")
    assert (summary["new"], summary["no_photo"]) == (N_NEW, 2)
    dup = pd.read_parquet(pool)
    dup = pd.concat([dup, dup.head(1)])
    dup.to_parquet(pool)
    with pytest.raises(ValueError, match="duplicate ids"):
        au.plan(pool, index, tmp_path / "todo.json")
    with pytest.raises(ValueError, match="positive"):
        au.plan(pool, index, tmp_path / "todo.json", max_new=0)


# ---- encode -----------------------------------------------------------------------------
def test_encode_shards_partition_the_todo(new_vectors, tmp_path):
    todo = tmp_path / "todo.json"
    write_todo(todo, new_vectors)
    seen = []
    for shard in range(3):
        out = tmp_path / f"vec-{shard}.npz"
        r = au.encode(todo, shard, 3, out, factory=fake_factory(new_vectors), chunk=5)
        z = au._load_vectors(out)
        assert (z["ids"] % 3 == shard).all() and r["stopped"] == "complete"
        np.testing.assert_allclose(np.linalg.norm(z["E"], axis=1), 1, atol=1e-5)
        assert z["E"].dtype == np.float32 and z["E"].shape == (len(z["ids"]), D)
        seen += z["ids"].tolist()
    assert sorted(seen) == sorted(new_vectors)


def test_encode_deadline_keeps_work_and_resume_finishes(new_vectors, tmp_path):
    todo, out = tmp_path / "todo.json", tmp_path / "vec.npz"
    write_todo(todo, new_vectors)
    ticks = iter(range(0, 10_000, 40))  # 40 s per clock read: start, then one read per chunk
    calls: list[int] = []
    bad = {list(new_vectors)[3]}
    factory = fake_factory(new_vectors, calls, bad)
    r = au.encode(
        todo, 0, 1, out, deadline_minutes=1.5, factory=factory, chunk=4, clock=lambda: next(ticks)
    )
    assert r["stopped"] == "deadline" and r["encoded"] + r["failed"] == 8  # two chunks fit
    part = au._load_vectors(out)
    assert len(part["ids"]) + len(part["failed"]) == 8

    before = len(calls)
    r = au.encode(todo, 0, 1, out, resume=out, factory=factory, chunk=4)
    assert r["stopped"] == "complete" and len(calls) - before == N_NEW - 8  # nothing re-encoded
    done = au._load_vectors(out)
    assert sorted(done["ids"].tolist() + done["failed"].tolist()) == sorted(new_vectors)
    assert done["failed"].tolist() == sorted(bad)
    assert len(set(calls)) == len(calls)


def test_encode_resume_rejects_another_model_and_empty_work_is_a_noop(new_vectors, tmp_path):
    todo, out = tmp_path / "todo.json", tmp_path / "vec.npz"
    write_todo(todo, new_vectors)
    au.encode(todo, 0, 1, out, deadline_minutes=0, factory=fake_factory(new_vectors))
    assert not out.exists() or len(au._load_vectors(out)["ids"]) == 0
    au.encode(todo, 0, 1, out, factory=fake_factory(new_vectors), chunk=100)
    other = fake_factory(new_vectors, info={"id": "other", "revision": "1"})
    # a fully resumed shard does not even load the encoder, so extend the todo to force a load
    write_todo(todo, [*new_vectors, 9_999_999])
    with pytest.raises(ValueError, match="resume file was encoded with"):
        au.encode(todo, 0, 1, out, resume=out, factory=other)

    write_todo(todo, [])
    empty = tmp_path / "empty.npz"
    r = au.encode(todo, 0, 2, empty, factory=lambda *_: pytest.fail("encoder must not load"))
    assert r["pending"] == 0 and not empty.exists()
    with pytest.raises(ValueError, match="shard"):
        au.encode(todo, 2, 2, empty)


# ---- apply ------------------------------------------------------------------------------
def encode_all(new_vectors, tmp_path, shards=2):
    todo = tmp_path / "todo.json"
    write_todo(todo, new_vectors)
    files = []
    for s in range(shards):
        out = tmp_path / f"vec-{s}.npz"
        au.encode(todo, s, shards, out, factory=fake_factory(new_vectors), chunk=6)
        files.append(str(out))
    return files


def test_apply_appends_searchable_part_and_neighbours(index, new_vectors, tmp_path):
    pool, old = make_pool(index, new_vectors, tmp_path)
    files = encode_all(new_vectors, tmp_path)
    before = ai.read_manifest(index)
    raw = tmp_path / "raw.npz"
    r = au.apply(index, files, pool, "delta-20260301", raw_out=raw)
    assert (r["added"], r["count"]) == (N_NEW, before["count"] + N_NEW)
    m = ai.read_manifest(index)
    assert [p["name"] for p in m["parts"]] == ["base", "delta-20260101", "delta-20260301"]
    assert m["neighbors"][-1]["name"] == "neighbors-delta-20260301"
    assert m["neighbors"][-1]["count"] == N_NEW

    some = list(new_vectors)[:10]
    found, _ = ai.search(index, np.stack([new_vectors[i] for i in some]), 1, 16)
    assert found[:, 0].tolist() == some
    for obs_id in some:
        nb, cos = lookup_neighbors(index, obs_id)
        assert len(nb) == 12 and obs_id not in nb and (np.diff(cos) <= 1e-3).all()
        assert (cos <= 1.0).all() and (cos > 0).all()
    assert lookup_neighbors(index, int(old[0])) is not None  # base set still answers old ids
    assert lookup_neighbors(index, 5) is None

    with np.load(raw) as z:
        assert z["E"].dtype == np.float16 and sorted(z["ids"].tolist()) == sorted(new_vectors)

    again = au.apply(index, files, pool, "delta-20260302")  # a rerun adds nothing
    assert again["added"] == 0 and len(ai.read_manifest(index)["parts"]) == 3


def test_apply_skips_vectors_that_left_the_pool(index, new_vectors, tmp_path):
    gone = list(new_vectors)[:4]
    pool, _ = make_pool(index, {i: v for i, v in new_vectors.items() if i not in gone}, tmp_path)
    r = au.apply(index, encode_all(new_vectors, tmp_path), pool, "delta-20260301")
    assert r["added"] == N_NEW - 4
    assert not np.isin(ai._existing_ids(index, ai.read_manifest(index)), gone).any()


def test_delta_neighbors_merges_exact_and_adc_candidates(index, new_vectors, monkeypatch):
    ids = np.array(list(new_vectors))
    E = np.stack(list(new_vectors.values()))
    # no existing candidates: pure exact cosine among the new rows, self excluded
    monkeypatch.setattr(
        au.atlas_index,
        "search",
        lambda *a, **k: (np.full((len(E), 12), -1), np.zeros((len(E), 12))),
    )
    nb, cos = au.delta_neighbors(index, E, ids)
    sims = E @ E.T
    np.fill_diagonal(sims, -np.inf)
    assert (nb[:, 0] == ids[sims.argmax(1)]).all()
    np.testing.assert_allclose(cos[:, 0], sims.max(1), atol=2e-3)
    # an index hit scoring above every exact one leads the row; -1 padding rows are ignored
    hit = np.full((len(E), 12), -1)
    hit[:, 0] = 4_000_000_000
    score = np.zeros((len(E), 12))
    score[:, 0] = 0.999
    monkeypatch.setattr(au.atlas_index, "search", lambda *a, **k: (hit, score))
    nb, cos = au.delta_neighbors(index, E, ids)
    assert (nb[:, 0] == 4_000_000_000).all() and np.allclose(cos[:, 0], 0.999, atol=1e-3)
    # fewer candidates than k pads with id 0 and cosine -1
    monkeypatch.setattr(
        au.atlas_index, "search", lambda *a, **k: (np.full((1, 12), -1), np.zeros((1, 12)))
    )
    nb, cos = au.delta_neighbors(index, E[:1], ids[:1])
    assert (nb[0, 1:] == 0).all() and (cos[0, 1:] == -1).all()


def test_apply_compact_drops_ids_that_left_the_pool(index, new_vectors, tmp_path):
    pool, old = make_pool(index, new_vectors, tmp_path, drop_old=30)
    files = encode_all(new_vectors, tmp_path)
    r = au.apply(index, files, pool, "delta-20260301", compact=True, raw_out=tmp_path / "raw.npz")
    assert r["compacted"] and r["dropped"] == 30
    m = ai.read_manifest(index)
    live = pd.read_parquet(pool)["id"].to_numpy()
    # new names every compaction, so no published file is rewritten in place
    assert [p["name"] for p in m["parts"]] == ["base-20260301"] and m["count"] == len(live)
    assert [e["name"] for e in m["neighbors"]] == ["neighbors-base-20260301"]
    assert not list(index.glob("delta-*")) and not list(index.glob("base.*"))
    assert sorted(f.name for f in index.glob("neighbors*")) == [
        "neighbors-base-20260301.bin",
        "neighbors-base-20260301.dir.u32",
    ]
    assert np.isin(ai._existing_ids(index, m), live).all()
    gone, kept = int(old[0]), int(old[40])
    assert lookup_neighbors(index, gone) is None
    nb, _ = lookup_neighbors(index, kept)
    assert len(nb) == 12  # ids pointing at dropped observations may stay; the front end filters
    assert lookup_neighbors(index, list(new_vectors)[0]) is not None
    found, _ = ai.search(index, np.stack(list(new_vectors.values())[:5]), 5, 16)
    assert not np.isin(found, old[:30]).any()


def test_apply_compact_refuses_a_truncated_pool(index, new_vectors, tmp_path):
    pool, _ = make_pool(index, new_vectors, tmp_path, drop_old=1500)
    with pytest.raises(ValueError, match="truncated"):
        au.apply(index, encode_all(new_vectors, tmp_path), pool, "delta-20260301", compact=True)


def test_merge_neighbors_newer_record_wins(index):
    ids = np.array([1, 2, 3])
    write_neighbor_records(index, "a", ids, np.full((3, 12), 9), np.full((3, 12), 0.5), 2)
    write_neighbor_records(index, "b", ids[:1], np.full((1, 12), 8), np.full((1, 12), 0.7), 2)
    names = [e["name"] for e in ai.read_manifest(index)["neighbors"]]
    assert names[-2:] == ["a", "b"]
    assert lookup_neighbors(index, 1)[0][0] == 8 and lookup_neighbors(index, 2)[0][0] == 9
    merge_neighbors(index, keep_ids=[1, 2], name="merged")
    assert [e["name"] for e in ai.read_manifest(index)["neighbors"]] == ["merged"]
    assert lookup_neighbors(index, 1)[0][0] == 8 and lookup_neighbors(index, 3) is None


# ---- errors and cli ---------------------------------------------------------------------
def test_apply_errors(index, new_vectors, tmp_path, capsys):
    pool, _ = make_pool(index, new_vectors, tmp_path)
    files = encode_all(new_vectors, tmp_path)
    ids = np.array(list(new_vectors))[:3]
    info = json.dumps({"id": "fixture", "revision": "0"})

    def save(name, ids, E, model=info):
        path = tmp_path / name
        np.savez(path, ids=ids, E=E, failed=np.empty(0, np.int64), model=np.array(model))
        return str(path)

    good = np.stack([new_vectors[i] for i in ids])
    with pytest.raises(ValueError, match="dims mismatch"):
        au.apply(index, [save("d.npz", ids, good[:, :8])], pool, "delta-x")
    with pytest.raises(ValueError, match="model mismatch"):
        bad_model = json.dumps({"id": "fixture", "revision": "9"})
        au.apply(index, [save("m.npz", ids, good, bad_model)], pool, "delta-x")
    with pytest.raises(ValueError, match="duplicate ids"):
        au.apply(index, [files[0], files[0]], pool, "delta-x")
    with pytest.raises(ValueError, match="no model record"):
        np.savez(tmp_path / "plain.npz", ids=ids, E=good, failed=np.empty(0, np.int64))
        au.apply(index, [str(tmp_path / "plain.npz")], pool, "delta-x")
    assert len(ai.read_manifest(index)["parts"]) == 2  # nothing was appended
    # no vectors and no compaction is a no-op, not an error
    assert au.main(["apply", "--index", str(index), "--pool", str(pool), "--part", "delta-x"]) == 0
    assert (
        au.main(
            [
                "apply",
                "--index",
                str(index),
                "--vectors",
                "nope-*.npz",
                "--pool",
                str(pool),
                "--part",
                "d",
            ]
        )
        == 1
    )
    assert "atlas_update apply" in capsys.readouterr().err


def test_cli_end_to_end_with_globbed_vectors(index, new_vectors, tmp_path, capsys):
    pool, _ = make_pool(index, new_vectors, tmp_path)
    todo = tmp_path / "todo.json"
    assert au.main(["plan", "--pool", str(pool), "--index", str(index), "--out", str(todo)]) == 0
    assert json.loads(capsys.readouterr().out)["new"] == N_NEW
    for s in range(2):
        argv = [
            "encode",
            "--todo",
            str(todo),
            "--shard",
            str(s),
            "--shards",
            "2",
            "--out",
            str(tmp_path / f"vec-{s}.npz"),
        ]
        assert au.main(argv, factory=fake_factory(new_vectors)) == 0
    argv = [
        "apply",
        "--index",
        str(index),
        "--vectors",
        str(tmp_path / "vec-*.npz"),
        "--pool",
        str(pool),
    ]
    assert au.main([*argv, "--part", "delta-20260301", "--raw-out", str(tmp_path / "r.npz")]) == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["added"] == N_NEW
    assert au.main(["plan", "--pool", str(pool), "--index", str(index), "--out", str(todo)]) == 0
    assert json.loads(capsys.readouterr().out)["new"] == 0  # the next plan is empty


# ---- sync script ------------------------------------------------------------------------
@pytest.mark.skipif(shutil.which("jq") is None, reason="atlas_sync.sh needs jq")
def test_sync_script_local_mode_orders_manifest_last_and_prunes(index, tmp_path):
    host, work, log = tmp_path / "host", tmp_path / "work", tmp_path / "log"
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "ATLAS_HOST": "local",
           "ATLAS_LOCAL_DIR": str(host), "ATLAS_SYNC_LOG": str(log)}  # fmt: skip

    def run(*args, check=True):
        return subprocess.run(
            ["bash", str(SYNC), *args], env=env, capture_output=True, text=True, check=check
        )

    run("push", str(index))
    pushed = log.read_text().splitlines()
    assert pushed[-1] == "push manifest.json" and "push base.codes.u8" in pushed
    assert (host / "manifest.json").read_bytes() == (index / "manifest.json").read_bytes()

    log.unlink()
    run("pull", str(work), "ids")
    assert sorted(p.name for p in work.iterdir()) == sorted(
        ["manifest.json", *[p.name for p in index.glob("*.ids.u32")]]
    )
    shutil.rmtree(work)
    run("pull", str(work))
    assert (work / "base.codes.u8").exists()

    (host / "stale.bin").write_bytes(b"x")  # e.g. a delta part a compaction folded away
    (host / "model").mkdir()
    (host / "model" / "text_encoder-abc.onnx").write_bytes(b"m")  # seeded once, never synced
    run("push", str(work))
    assert not (host / "stale.bin").exists()  # files the pushed index no longer has are pruned
    assert (host / "model" / "text_encoder-abc.onnx").exists()
    run("pull", str(tmp_path / "again"))
    assert not (tmp_path / "again" / "model").exists()

    (work / "delta-20260101.codes.u8").unlink()
    broken = run("push", str(work), check=False)
    assert broken.returncode != 0 and "lacks it" in broken.stderr
    assert run("pull", str(tmp_path / "x"), check=False).returncode == 0
    env.pop("ATLAS_HOST")
    assert run("pull", str(tmp_path / "y"), check=False).returncode != 0


# Stand-in for the hf CLI: each glob flag takes one value, so a stray value is an extra positional,
# which the real CLI rejects ("Got unexpected extra argument").
FAKE_HF = """#!/usr/bin/env python3
import json, os, sys
args, pos, flags = sys.argv[1:], [], []
i = 1
while i < len(args):
    if args[i].startswith("--"):
        flags.append([args[i], args[i + 1]]); i += 2
    else:
        pos.append(args[i]); i += 1
want = {"upload": 3, "download": 1}[args[0]]
if len(pos) != want:
    sys.exit(f"Got unexpected extra argument ({pos[want:]})")
with open(os.environ["HF_LOG"], "a") as log:
    log.write(json.dumps({"cmd": args[0], "pos": pos, "flags": flags}) + "\\n")
if args[0] == "download":
    local = dict(flags)["--local-dir"]
    os.makedirs(local, exist_ok=True)
    open(os.path.join(local, "manifest.json"), "w").write("{}")
"""


@pytest.mark.skipif(shutil.which("jq") is None, reason="atlas_sync.sh needs jq")
def test_sync_script_hf_mode_passes_one_glob_per_flag_and_prunes_only_index_files(index, tmp_path):
    bin_dir, log = tmp_path / "bin", tmp_path / "hf.log"
    bin_dir.mkdir()
    (bin_dir / "hf").write_text(FAKE_HF)
    (bin_dir / "hf").chmod(0o755)
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "ATLAS_HOST": "hf",
           "ATLAS_HF_REPO": "someone/atlas", "HF_LOG": str(log)}  # fmt: skip

    def run(*args):
        done = subprocess.run(["bash", str(SYNC), *args], env=env, capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
        return [json.loads(line) for line in log.read_text().splitlines()]

    calls = run("push", str(index))
    assert [c["cmd"] for c in calls] == ["upload"] * 3
    assert calls[1]["pos"][1:] == [str(index / "manifest.json"), "manifest.json"]
    deletes = [v for f, v in calls[2]["flags"] if f == "--delete"]
    assert deletes and "*" not in deletes and all("*" in d for d in deletes)
    assert ["--exclude", "model/*"] in calls[2]["flags"]
    log.unlink()
    calls = run("pull", str(tmp_path / "ids"), "ids")
    includes = [v for f, v in calls[0]["flags"] if f == "--include"]
    assert includes == ["manifest.json", "*.ids.u32"]
    assert ["--exclude", "model/*"] in calls[0]["flags"]


def test_workflow_is_gated_pinned_and_off_the_pages_group():
    yaml = pytest.importorskip("yaml")
    text = (SYNC.parents[1] / ".github" / "workflows" / "atlas.yml").read_text()
    wf = yaml.safe_load(text)
    assert (
        wf["concurrency"]["group"] != "pages" and wf["concurrency"]["cancel-in-progress"] is False
    )
    assert set(wf["jobs"]) == {"plan", "encode", "apply"}
    for name, job in wf["jobs"].items():
        assert "vars.ATLAS_ENABLED == 'true'" in job["if"], name
    assert "inputs.dry_run" in wf["jobs"]["plan"]["if"]
    assert wf["jobs"]["encode"]["timeout-minutes"] <= 180
    for name in ("plan", "apply"):  # atlas_sync.sh needs the hf CLI, which requirements.lock lacks
        assert any("huggingface_hub==" in step.get("run", "") for step in wf["jobs"][name]["steps"])
    uses = re.findall(r"uses: (\S+)@(\S+)", text)
    assert uses and all(re.fullmatch(r"[0-9a-f]{40}", ref) for _, ref in uses)
    for action in ("checkout", "setup-python", "upload-artifact"):
        # same SHAs as map.yml / daily.yml
        shas = {ref for a, ref in uses if a == f"actions/{action}"}
        assert len(shas) == 1
