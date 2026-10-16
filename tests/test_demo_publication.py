"""Publication contract tests at the gh subprocess and archive boundaries."""

import copy
import io
import json
import os
import stat
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

from what_to_id.demo_publication import (
    PublicationError,
    deployed_artifact,
    deployed_revision,
    main,
    prepare_site,
)

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


def test_publish_step_chronology_overrides_status_and_creation_recency(github):
    responses, _ = github
    job = add_newer_deployment(responses)
    # This job was created later and got a much later failure status, but its
    # successful publish step finished before the currently published job's step.
    job["steps"][0].update(started_at="2099-01-01T00:29:00Z", completed_at="2099-01-01T00:30:00Z")
    assert deployed_artifact(REPO) == 30


def add_newer_deployment(responses, *, outcome="failure", deploy_conclusion="success"):
    new_sha = "b" * 40
    responses[f"{BASE}/deployments?environment=github-pages&per_page=100"].insert(
        0, [{"id": 2, "sha": new_sha, "created_at": "2099-01-01T02:00:00Z"}]
    )
    responses[f"{BASE}/deployments/2/statuses?per_page=100"] = [
        [
            {
                "state": outcome,
                "created_at": "2099-01-01T03:00:00Z",
                "log_url": f"https://github.com/{REPO}/actions/runs/11/job/21",
            }
        ]
    ]
    run = copy.deepcopy(responses[f"{BASE}/actions/runs/10"])
    run.update(id=11, head_sha=new_sha)
    responses[f"{BASE}/actions/runs/11"] = run
    job = copy.deepcopy(responses[f"{BASE}/actions/jobs/20"])
    job.update(id=21, run_id=11, head_sha=new_sha, conclusion=outcome)
    job["steps"][0].update(
        started_at="2099-01-01T01:59:00Z",
        completed_at="2099-01-01T02:00:00Z",
        conclusion=deploy_conclusion,
    )
    job["steps"].append(
        {
            "name": "Save the map pool",
            "status": "completed",
            "conclusion": "failure",
            "completed_at": "2099-01-01T03:00:00Z",
        }
    )
    responses[f"{BASE}/actions/jobs/21"] = job
    responses[f"{BASE}/actions/jobs/21/logs"] = (
        responses[f"{BASE}/actions/jobs/20/logs"]
        .replace(SHA.encode(), new_sha.encode())
        .replace(b'"artifact_id": 30', b'"artifact_id": 31')
        .replace(b"00:59:", b"01:59:")
    )
    artifact = copy.deepcopy(responses[f"{BASE}/actions/artifacts/30"])
    artifact["id"] = 31
    artifact["workflow_run"].update(id=11, head_sha=new_sha)
    responses[f"{BASE}/actions/artifacts/31"] = artifact
    return job


@pytest.mark.parametrize("outcome", ["failure", "error", "inactive", "in_progress", "success"])
def test_later_published_map_remains_current_when_post_deploy_step_fails(github, outcome):
    responses, _ = github
    add_newer_deployment(responses, outcome=outcome)
    assert deployed_artifact(REPO) == 31


@pytest.mark.parametrize("conclusion", ["failure", "cancelled"])
def test_started_later_failed_deploy_refuses_stale_base(github, demo, tmp_path, conclusion):
    responses, calls = github
    add_newer_deployment(responses, deploy_conclusion=conclusion)
    # Pages can accept artifact31 and publish it before the action fails its next
    # status poll or is cancelled. Step failure cannot prove artifact30 is live.
    with pytest.raises(PublicationError, match="Unconfirmed Pages publication"):
        prepare_site(REPO, demo, tmp_path / "output")
    assert not (tmp_path / "output").exists()
    assert not any(call[2].endswith("/zip") for call in calls)


def test_skipped_later_deploy_did_not_publish(github):
    responses, _ = github
    add_newer_deployment(responses, deploy_conclusion="skipped")
    assert deployed_artifact(REPO) == 30


def test_newer_confirmed_success_recovers_from_historical_failed_step(github):
    responses, _ = github
    responses[f"{BASE}/actions/jobs/20"]["steps"][0]["conclusion"] = "failure"
    add_newer_deployment(responses)
    assert deployed_artifact(REPO) == 31


@pytest.mark.parametrize("end", [TIME, "2099-01-01T01:00:01Z", None])
def test_failed_step_overlapping_last_success_is_ambiguous(github, end):
    responses, _ = github
    job = add_newer_deployment(responses, deploy_conclusion="failure")
    job["steps"][0].update(started_at="2099-01-01T00:58:00Z", completed_at=end)
    with pytest.raises(PublicationError, match="Unconfirmed Pages publication"):
        deployed_artifact(REPO)


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


def test_repeated_statuses_for_same_job_are_deduplicated(github):
    responses, calls = github
    key = f"{BASE}/deployments/1/statuses?per_page=100"
    responses[key][0].append(dict(responses[key][0][0]))
    assert deployed_artifact(REPO) == 30
    assert sum(call[2] == f"{BASE}/actions/jobs/20" for call in calls) == 1


def test_tied_publish_steps_and_no_success_fail_closed(github):
    responses, _ = github
    job = add_newer_deployment(responses)
    job["steps"][0]["completed_at"] = TIME
    with pytest.raises(PublicationError, match="Ambiguous"):
        deployed_artifact(REPO)
    for job_id in (20, 21):
        responses[f"{BASE}/actions/jobs/{job_id}"]["steps"][0]["conclusion"] = "failure"
    with pytest.raises(PublicationError, match="No successful"):
        deployed_artifact(REPO)


def test_revision_cli_verifies_latest_publish_without_downloading_an_archive(
    github, monkeypatch, capsys
):
    responses, calls = github
    add_newer_deployment(responses)
    assert deployed_revision(REPO) == "b" * 40
    monkeypatch.setattr("sys.argv", ["demo_publication", "--repository", REPO, "--revision"])
    main()
    assert capsys.readouterr().out == "b" * 40 + "\n"
    assert not any("/artifacts/" in call[2] for call in calls)


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
    with pytest.raises(PublicationError, match="GitHub API request failed"):
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
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    python = bin_dir / "python3"
    python.write_text('#!/bin/sh\nprintf "%s\\n" "$DEPLOYED_SHA"\n')
    python.chmod(0o755)
    result = tmp_path / "route-output"
    subprocess.run(
        ["bash", "-c", script],
        cwd=tmp_path,
        check=True,
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "EVENT": event,
            "BEFORE": before,
            "FULL_SITE_ENABLED": "true",
            "GITHUB_REPOSITORY": REPO,
            "DEPLOYED_SHA": before,
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


def test_route_does_not_lose_cancelled_pending_source_push(tmp_path):
    workflow = Path(__file__).parents[1] / ".github/workflows/pages.yml"
    text = workflow.read_text()
    route = text.split("          set -euo pipefail\n", 1)[1].split("  # Changes to", 1)[0]
    script = "set -euo pipefail\n" + "\n".join(line[10:] for line in route.splitlines())

    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True).strip()

    def commit(message):
        git("-c", "user.name=Test", "-c", "user.email=test@example.org", "commit", "-qm", message)
        return git("rev-parse", "HEAD")

    git("init", "-q")
    (tmp_path / "site").mkdir()
    (tmp_path / "site/index.html").write_text("deployed study")
    git("add", "site/index.html")
    deployed = commit("deployed map R")
    (tmp_path / "site/index.html").write_text("pending study change A")
    git("add", "site/index.html")
    pending = commit("source push A, workflow cancelled while pending")
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo/embeddings.html").write_text("new demo B")
    git("add", "demo/embeddings.html")
    current = commit("demo push B replaces pending A workflow")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    python = bin_dir / "python3"
    python.write_text('#!/bin/sh\nprintf "%s\\n" "$DEPLOYED_SHA"\n')
    python.chmod(0o755)
    result = tmp_path / "route-output"
    subprocess.run(
        ["bash", "-c", script],
        cwd=tmp_path,
        check=True,
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "EVENT": "push",
            "BEFORE": pending,
            "AFTER": current,
            "DEPLOYED_SHA": deployed,
            "FULL_SITE_ENABLED": "true",
            "GITHUB_REPOSITORY": REPO,
            "GITHUB_OUTPUT": str(result),
        },
    )
    assert result.read_text() == "refresh=true\n"


def test_current_overlay_job_waiting_to_deploy_does_not_hide_live_site(github):
    responses, _ = github
    job = add_newer_deployment(responses, outcome="in_progress")
    job["steps"][0].update(status="pending", conclusion=None, started_at=None, completed_at=None)
    assert deployed_artifact(REPO) == 30


@pytest.mark.parametrize("response", ["exit 1", 'printf "%s\\n" unknown-revision'])
def test_route_unknown_deployed_revision_fails_without_selecting_a_publish(tmp_path, response):
    workflow = Path(__file__).parents[1] / ".github/workflows/pages.yml"
    text = workflow.read_text()
    route = text.split("          set -euo pipefail\n", 1)[1].split("  # Changes to", 1)[0]
    script = "set -euo pipefail\n" + "\n".join(line[10:] for line in route.splitlines())
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    python = bin_dir / "python3"
    python.write_text(f"#!/bin/sh\n{response}\n")
    python.chmod(0o755)
    output = tmp_path / "route-output"
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=tmp_path,
        capture_output=True,
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "EVENT": "push",
            "FULL_SITE_ENABLED": "true",
            "GITHUB_REPOSITORY": REPO,
            "AFTER": SHA,
            "GITHUB_OUTPUT": str(output),
        },
    )
    assert result.returncode != 0
    assert not output.exists()


@pytest.mark.parametrize("has_start", [True, False])
def test_running_deploy_step_cannot_establish_old_site_is_current(github, has_start):
    responses, _ = github
    job = add_newer_deployment(responses, outcome="in_progress")
    job["steps"][0].update(status="in_progress", conclusion=None, completed_at=None)
    if not has_start:
        job["steps"][0]["started_at"] = None
    with pytest.raises(PublicationError, match="Unconfirmed Pages publication"):
        deployed_artifact(REPO)


def test_job_log_http_failure_is_actionable_without_credentials(github, monkeypatch, capsys):
    responses, _ = github
    monkeypatch.setenv("GH_TOKEN", "workflow-secret-value")
    endpoint = f"{BASE}/actions/jobs/20/logs"
    responses[endpoint] = subprocess.CalledProcessError(
        1,
        ["gh", "api", endpoint],
        output=b"private response body",
        stderr=(
            b"gh: Resource not accessible by integration (HTTP 403)\n"
            b"Authorization: Bearer workflow-secret-value\n"
            b"GET https://logs.example.test/archive?sig=private-signature&token=workflow-secret-value\n"
            b"token github_pat_unset_secret and ghs_unset_secret\n"
        ),
    )
    monkeypatch.setattr("sys.argv", ["demo_publication", "--repository", REPO, "--revision"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    message = capsys.readouterr().err
    assert endpoint in message
    assert "HTTP 403" in message
    assert "Resource not accessible by integration" in message
    assert "logs.example.test/archive" in message
    assert "workflow-secret-value" not in message
    assert "private-signature" not in message
    assert "private response body" not in message
    assert "github_pat_unset_secret" not in message
    assert "ghs_unset_secret" not in message
    assert "The current live site is unchanged" in message


def test_empty_api_stderr_still_reports_failing_endpoint(github):
    responses, _ = github
    endpoint = f"{BASE}/actions/jobs/20/logs"
    responses[endpoint] = subprocess.CalledProcessError(1, ["gh", "api", endpoint])
    with pytest.raises(PublicationError, match="no HTTP diagnostics") as error:
        deployed_revision(REPO)
    assert endpoint in str(error.value)
