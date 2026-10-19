"""Tests for scripts/atlas_sync.sh (local and Hugging Face modes) and the atlas workflow."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from .atlas_index_fixture import write_fixture

faiss = pytest.importorskip("faiss")

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

    # taxon vectors are big and unchanged daily: pulls skip them, pushes without them spare the host
    (host / "taxa-old.f16").write_bytes(b"t")
    run("pull", str(tmp_path / "notaxa"))
    assert not list((tmp_path / "notaxa").glob("taxa-*"))
    run("push", str(work))
    assert (host / "taxa-old.f16").exists()
    (work / "taxa-new.f16").write_bytes(b"t")
    run("push", str(work))  # a directory that has taxa vectors owns them: the old set is pruned
    assert (host / "taxa-new.f16").exists() and not (host / "taxa-old.f16").exists()
    (work / "taxa-new.f16").unlink()

    for gone in ("delta-20260101.refine.u8", "opq.f16"):
        saved = (work / gone).read_bytes()
        (work / gone).unlink()
        refused = run("push", str(work), check=False)
        assert refused.returncode != 0 and f"names {gone}" in refused.stderr
        (work / gone).write_bytes(saved)
    m = json.loads((work / "manifest.json").read_text())
    m["layout"] = {"parts": [{"name": "layout-base", "count": 1}]}
    (work / "manifest.json").write_text(json.dumps(m))
    refused = run("push", str(work), check=False)  # the manifest names a layout part it lacks
    assert refused.returncode != 0 and "names layout-base.bin" in refused.stderr
    (work / "layout-base.bin").write_bytes(b"x")
    run("push", str(work))
    assert (host / "layout-base.bin").exists()
    (work / "layout-base.bin").unlink()
    (work / "manifest.json").write_text(json.dumps({k: v for k, v in m.items() if k != "layout"}))
    run("push", str(work))
    assert not (host / "layout-base.bin").exists()  # pruned once the manifest drops it
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
