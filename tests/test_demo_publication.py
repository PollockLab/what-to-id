"""Publication contract tests at the gh subprocess and archive boundaries."""

import io
import json
import os
import stat
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

from what_to_id.demo_publication import PublicationError, deployed_artifact, prepare_site

REPO = "PollockLab/what-to-id"
SHA = "a" * 40
BASE = f"repos/{REPO}"
TIME = "2099-01-01T01:00:00Z"


def archive(files, *, member=None, zip_name="artifact.tar", zip_mode=None):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
        if member:
            tar.addfile(member)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as zipped:
        entry = zipfile.ZipInfo(zip_name)
        if zip_mode:
            entry.external_attr = zip_mode << 16
        zipped.writestr(entry, buffer.getvalue())
    return output.getvalue()


@pytest.fixture
def github(monkeypatch):
    responses = {
        f"{BASE}/deployments?environment=github-pages&per_page=100": [
            [{"id": 1, "sha": SHA, "created_at": "2099-01-01T00:00:00Z"}]
        ],
        f"{BASE}/deployments/1/statuses?per_page=100": [
            [
                {
                    "state": "success",
                    "created_at": TIME,
                    "log_url": f"https://github.com/{REPO}/actions/runs/10/job/20",
                }
            ]
        ],
        f"{BASE}/actions/runs/10": {
            "id": 10,
            "head_sha": SHA,
            "run_attempt": 1,
            "repository": {"id": 42, "full_name": REPO},
            "head_repository": {"id": 42},
        },
        f"{BASE}/actions/jobs/20": {
            "id": 20,
            "run_id": 10,
            "head_sha": SHA,
            "run_attempt": 1,
            "steps": [
                {
                    "name": "Run actions/deploy-pages@pinned",
                    "status": "completed",
                    "conclusion": "success",
                    "started_at": "2099-01-01T00:59:00Z",
                    "completed_at": TIME,
                }
            ],
        },
        f"{BASE}/actions/jobs/20/logs": (
            "2099-01-01T00:59:01.1Z Creating Pages deployment with payload:\n"
            "2099-01-01T00:59:01.2Z {\n"
            '2099-01-01T00:59:01.3Z "artifact_id": 30,\n'
            f'2099-01-01T00:59:01.4Z "pages_build_version": "{SHA}"\n'
            "2099-01-01T00:59:01.5Z }\n"
        ).encode(),
        f"{BASE}/actions/artifacts/30": {
            "id": 30,
            "name": "github-pages",
            "expired": False,
            "expires_at": "2099-01-02T00:00:00Z",
            "workflow_run": {
                "id": 10,
                "repository_id": 42,
                "head_repository_id": 42,
                "head_sha": SHA,
            },
        },
        f"{BASE}/actions/artifacts/30/zip": archive(
            {
                "./index.html": b"<html>study</html>",
                "./map.html": b"<html>map</html>",
                "./pool.bin": b"\x00\xffmap",
                "./metadata/state.json": b'{"map":"frozen"}',
                "./.nojekyll": b"",
                "./embeddings.html": b"old demo",
                "./embeddings-data/Old.json": b"old group",
                "./dinov3/embeddings-data/Old.json": b"old dino group",
            }
        ),
    }
    calls = []

    def fake_run(args, *, check, capture_output):
        assert args[:2] == ["gh", "api"]
        assert check and capture_output
        calls.append(args)
        value = responses[args[2]]
        if isinstance(value, Exception):
            raise value
        return subprocess.CompletedProcess(
            args, 0, value if isinstance(value, bytes) else json.dumps(value).encode(), b""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    return responses, calls


@pytest.fixture
def demo(tmp_path):
    root = tmp_path / "demo"
    for prefix in (root, root / "dinov3"):
        prefix.mkdir(parents=True, exist_ok=True)
        (prefix / "embeddings.html").write_text("<!doctype html><html>new demo</html>")
        (prefix / "embeddings-data").mkdir()
        (prefix / "embeddings-data/Plantae.json").write_text(
            '{"group":"Plantae","records":[{"id":1}]}'
        )
    return root


def test_overlay_preserves_every_non_demo_byte_and_removes_stale_groups(github, demo, tmp_path):
    output = tmp_path / "full_site"
    assert prepare_site(REPO, demo, output) == 30
    actual = {
        p.relative_to(output).as_posix(): p.read_bytes() for p in output.rglob("*") if p.is_file()
    }
    assert actual == {
        "index.html": b"<html>study</html>",
        "map.html": b"<html>map</html>",
        "pool.bin": b"\x00\xffmap",
        "metadata/state.json": b'{"map":"frozen"}',
        ".nojekyll": b"",
        **{p.relative_to(demo).as_posix(): p.read_bytes() for p in demo.rglob("*") if p.is_file()},
    }
    assert github[1][-1][2] == f"{BASE}/actions/artifacts/30/zip"


def test_selects_success_status_chronology_not_deployment_or_run_recency(github):
    responses, _ = github
    responses[f"{BASE}/deployments?environment=github-pages&per_page=100"] = [
        [{"id": 2, "sha": "wrong", "created_at": "2099-01-01T03:00:00Z"}],
        responses[f"{BASE}/deployments?environment=github-pages&per_page=100"][0],
    ]
    responses[f"{BASE}/deployments/2/statuses?per_page=100"] = [
        [
            {"state": "success", "created_at": "2099-01-01T00:00:00Z", "log_url": "wrong"},
            {"state": "in_progress", "created_at": "2099-01-01T05:00:00Z"},
            {"state": "failure", "created_at": "2099-01-01T06:00:00Z"},
        ]
    ]
    assert deployed_artifact(REPO) == 30


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", "not-pages"),
        ("expired", True),
        ("expires_at", "2000-01-01T00:00:00Z"),
    ],
)
def test_rejects_wrong_or_expired_artifact(github, field, value):
    github[0][f"{BASE}/actions/artifacts/30"][field] = value
    with pytest.raises(PublicationError):
        deployed_artifact(REPO)


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", 999),
        ("repository_id", 999),
        ("head_repository_id", 999),
        ("head_sha", "wrong"),
    ],
)
def test_rejects_artifact_provenance_mismatch(github, field, value):
    github[0][f"{BASE}/actions/artifacts/30"]["workflow_run"][field] = value
    with pytest.raises(PublicationError, match="provenance"):
        deployed_artifact(REPO)


@pytest.mark.parametrize("change", ["url", "run_sha", "job_sha", "repo", "fork", "rerun", "step"])
def test_rejects_unproven_deploying_job(github, change):
    responses, _ = github
    if change == "url":
        responses[f"{BASE}/deployments/1/statuses?per_page=100"][0][0]["log_url"] = (
            "https://github.com/other/repo/actions/runs/10/job/20"
        )
    elif change == "run_sha":
        responses[f"{BASE}/actions/runs/10"]["head_sha"] = "wrong"
    elif change == "job_sha":
        responses[f"{BASE}/actions/jobs/20"]["head_sha"] = "wrong"
    elif change == "repo":
        responses[f"{BASE}/actions/runs/10"]["repository"]["full_name"] = "other/repo"
    elif change == "fork":
        responses[f"{BASE}/actions/runs/10"]["head_repository"]["id"] = 999
    elif change == "rerun":
        responses[f"{BASE}/actions/runs/10"]["run_attempt"] = 2
    else:
        responses[f"{BASE}/actions/jobs/20"]["steps"][0]["conclusion"] = "failure"
    with pytest.raises(PublicationError):
        deployed_artifact(REPO)


@pytest.mark.parametrize("change", ["missing", "duplicate", "wrong_sha", "outside_step"])
def test_rejects_ambiguous_or_invalid_deployment_payload(github, change):
    responses, _ = github
    key = f"{BASE}/actions/jobs/20/logs"
    log = responses[key]
    responses[key] = {
        "missing": b"",
        "duplicate": log + log,
        "wrong_sha": log.replace(SHA.encode(), b"wrong"),
        "outside_step": log.replace(b"00:59:01", b"00:58:01"),
    }[change]
    with pytest.raises(PublicationError, match="payload"):
        deployed_artifact(REPO)


def test_success_tie_and_no_success_fail_closed(github):
    responses, _ = github
    key = f"{BASE}/deployments/1/statuses?per_page=100"
    responses[key][0].append(dict(responses[key][0][0]))
    with pytest.raises(PublicationError, match="Ambiguous"):
        deployed_artifact(REPO)
    responses[key] = [[{"state": "in_progress"}]]
    with pytest.raises(PublicationError, match="No successful"):
        deployed_artifact(REPO)


@pytest.mark.parametrize(
    "kind",
    [
        "traversal",
        "absolute",
        "backslash",
        "symlink",
        "hardlink",
        "fifo",
        "duplicate",
        "zip_link",
        "zip_traversal",
        "missing_map",
    ],
)
def test_archive_rejection_leaves_output_absent(github, demo, tmp_path, kind):
    member = None
    files = {"index.html": b"study", "map.html": b"map", "pool.bin": b"pool"}
    kwargs = {}
    if kind in ("traversal", "absolute", "backslash"):
        files[
            {"traversal": "../escape", "absolute": "/escape", "backslash": "..\\escape"}[kind]
        ] = b"x"
    elif kind in ("symlink", "hardlink", "fifo"):
        member = tarfile.TarInfo("link")
        member.type = {
            "symlink": tarfile.SYMTYPE,
            "hardlink": tarfile.LNKTYPE,
            "fifo": tarfile.FIFOTYPE,
        }[kind]
        member.linkname = "../escape"
    elif kind == "duplicate":
        files["./index.html"] = b"second index"
    elif kind == "zip_link":
        kwargs["zip_mode"] = stat.S_IFLNK | 0o777
    elif kind == "zip_traversal":
        kwargs["zip_name"] = "../artifact.tar"
    else:
        del files["map.html"]
    github[0][f"{BASE}/actions/artifacts/30/zip"] = archive(files, member=member, **kwargs)
    with pytest.raises(PublicationError):
        prepare_site(REPO, demo, tmp_path / "output")
    assert not (tmp_path / "output").exists()
    assert not (tmp_path / "escape").exists()
    assert not list(tmp_path.glob(".pages-overlay-*"))


@pytest.mark.parametrize(
    "kind",
    [
        "collision",
        "malformed_json",
        "wrong_group",
        "empty_records",
        "missing_page",
        "bad_html",
        "symlink",
        "unexpected_dir",
    ],
)
def test_bad_demo_does_not_contact_github_or_modify_existing_files(github, demo, tmp_path, kind):
    if kind == "collision":
        (demo / "index.html").write_text("bad")
    elif kind in ("malformed_json", "wrong_group", "empty_records"):
        (demo / "embeddings-data/Plantae.json").write_text(
            {
                "malformed_json": "{",
                "wrong_group": '{"group":"Birds","records":[1]}',
                "empty_records": '{"group":"Plantae","records":[]}',
            }[kind]
        )
    elif kind == "missing_page":
        (demo / "dinov3/embeddings.html").unlink()
    elif kind == "bad_html":
        (demo / "embeddings.html").write_text("broken")
    elif kind == "symlink":
        (demo / "link").symlink_to(demo / "embeddings.html")
    else:
        (demo / "extra").mkdir()
    sentinel = tmp_path / "sentinel"
    sentinel.write_bytes(b"untouched")
    with pytest.raises(ValueError):
        prepare_site(REPO, demo, tmp_path / "output")
    assert github[1] == []
    assert sentinel.read_bytes() == b"untouched"
    assert not (tmp_path / "output").exists()


def test_existing_output_and_api_failure_leave_site_unchanged(github, demo, tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    (output / "map.html").write_bytes(b"existing live copy")
    with pytest.raises(PublicationError, match="already exists"):
        prepare_site(REPO, demo, output)
    assert (output / "map.html").read_bytes() == b"existing live copy"
    github[0][f"{BASE}/actions/artifacts/30/zip"] = subprocess.CalledProcessError(1, "gh")
    with pytest.raises(subprocess.CalledProcessError):
        prepare_site(REPO, demo, tmp_path / "new_output")
    assert not (tmp_path / "new_output").exists()


@pytest.mark.parametrize(
    "changed,event,expected",
    [
        ("demo/embeddings.html", "push", "false"),
        ("src/what_to_id/demo_publication.py", "push", "false"),
        ("site/index.html", "push", "true"),
        (".github/workflows/pages.yml", "push", "true"),
        ("demo/embeddings.html", "workflow_dispatch", "true"),
    ],
)
def test_workflow_routes_demo_updates_without_a_map_refresh(tmp_path, changed, event, expected):
    workflow = Path(__file__).parents[1] / ".github/workflows/pages.yml"
    text = workflow.read_text()
    route = text.split("          set -euo pipefail\n", 1)[1].split("  # Changes to", 1)[0]
    script = "set -euo pipefail\n" + "\n".join(line[10:] for line in route.splitlines())

    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True).strip()

    git("init", "-q")
    git(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.org",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "base",
    )
    before = git("rev-parse", "HEAD")
    path = tmp_path / changed
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("change")
    git("add", changed)
    git("-c", "user.name=Test", "-c", "user.email=test@example.org", "commit", "-qm", "change")
    result = tmp_path / "route-output"
    subprocess.run(
        ["bash", "-c", script],
        cwd=tmp_path,
        check=True,
        env={
            **os.environ,
            "EVENT": event,
            "BEFORE": before,
            "AFTER": git("rev-parse", "HEAD"),
            "GITHUB_OUTPUT": str(result),
        },
    )
    assert result.read_text() == f"refresh={expected}\n"


def test_dangling_output_symlink_is_preserved(github, demo, tmp_path):
    output = tmp_path / "output"
    target = tmp_path / "missing"
    output.symlink_to(target)
    with pytest.raises(PublicationError, match="already exists"):
        prepare_site(REPO, demo, output)
    assert output.is_symlink()
    assert output.readlink() == target
    assert not target.exists()
    assert github[1] == []
