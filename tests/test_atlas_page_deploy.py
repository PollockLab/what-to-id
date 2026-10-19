"""Every Pages deploy uploads a whole site, so each build path must add the search page."""

import os
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "atlas_page.sh"
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))


def _upload_jobs():
    for workflow in WORKFLOWS:
        for name, job in yaml.safe_load(workflow.read_text())["jobs"].items():
            steps = job.get("steps", [])
            uploads = [s for s in steps if "upload-pages-artifact" in s.get("uses", "")]
            if uploads:
                yield pytest.param(steps, uploads[0]["with"]["path"], id=f"{workflow.name}:{name}")


def test_four_deploy_paths_are_covered():
    assert len(list(_upload_jobs())) == 4


@pytest.mark.parametrize("steps,path", _upload_jobs())
def test_deploy_path_adds_the_search_page_before_upload(steps, path):
    # The overlay job keeps the deployed site's bytes, which already hold search.html.
    if any("demo_publication" in s.get("run", "") for s in steps):
        pytest.skip("overlay preserves the deployed site")
    upload = next(i for i, s in enumerate(steps) if "upload-pages-artifact" in s.get("uses", ""))
    page = [
        s for s in steps[:upload] if s.get("run", "").strip() == f"scripts/atlas_page.sh {path}"
    ]
    assert len(page) == 1
    assert page[0]["env"]["ATLAS_HF_REPO"] == "${{ vars.ATLAS_HF_REPO }}"


def test_script_is_executable_in_git():
    mode = subprocess.check_output(
        ["git", "ls-files", "-s", "scripts/atlas_page.sh"], cwd=ROOT, text=True
    )
    assert mode.startswith("100755")


def _run(tmp_path, **env):
    full = {k: v for k, v in os.environ.items() if k != "ATLAS_HF_REPO"}
    full.update(env)
    return subprocess.run(
        [str(SCRIPT), str(tmp_path / "site")], capture_output=True, text=True, env=full
    )


@pytest.mark.parametrize("env", [{}, {"ATLAS_HF_REPO": ""}])
def test_script_without_repo_writes_nothing(tmp_path, env):
    result = _run(tmp_path, **env)
    assert result.returncode == 0
    assert "skipping" in result.stdout
    assert not (tmp_path / "site").exists()


def test_script_with_repo_writes_page_with_data_url(tmp_path):
    result = _run(tmp_path, ATLAS_HF_REPO="Org/atlas")
    assert result.returncode == 0, result.stderr
    page = (tmp_path / "site" / "search.html").read_text()
    assert "https://huggingface.co/datasets/Org/atlas/resolve/main/" in page
    assert "map.html" in page
    photo_space = (tmp_path / "site" / "embeddings.html").read_text()
    assert "https://huggingface.co/datasets/Org/atlas/resolve/main/" in photo_space
    assert "embeddings-sample.html" in photo_space
