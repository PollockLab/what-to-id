"""Overlay the frozen demo on the exact successfully deployed Pages artifact.

Uses only Python's standard library and authenticated, read-only ``gh api`` calls.
Refuses to guess a base artifact or modify an existing output on any failure.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import zipfile
from datetime import UTC, datetime
from functools import cache
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit, urlunsplit


class PublicationError(ValueError):
    """Publication cannot safely preserve the current full site."""


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _safe_api_error(stderr: bytes | str | None) -> str:
    message = (
        stderr.decode("utf-8", errors="replace") if isinstance(stderr, bytes) else stderr or ""
    )
    for name in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"):
        if value := os.environ.get(name):
            message = message.replace(value, "[redacted]")
    message = re.sub(
        r"\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)\b", "[redacted]", message
    )
    message = re.sub(r"(?im)^(\s*(?:[<>]\s*)?authorization\s*:).*", r"\1 [redacted]", message)

    def redact_url(match: re.Match) -> str:
        try:
            url = urlsplit(match.group())
            return urlunsplit(
                (
                    url.scheme,
                    url.netloc.rsplit("@", 1)[-1],
                    url.path,
                    "[redacted]" if url.query else "",
                    "",
                )
            )
        except ValueError:
            return "[redacted URL]"

    message = re.sub(r"https?://[^\s<>\"']+", redact_url, message)
    return message.strip()[:2000] or "gh returned no HTTP diagnostics"


@cache
def _raw_output_flags() -> tuple[str, ...]:
    # Newer gh refuses ANSI-bearing logs even when stdout is captured. Opt in
    # only for these internal byte downloads, never for terminal output. Older
    # local CLI versions predate both the guard and the flag.
    result = subprocess.run(["gh", "api", "--help"], check=True, capture_output=True)
    return ("--allow-escape-sequences",) if b"--allow-escape-sequences" in result.stdout else ()


def _api(endpoint: str, *, pages: bool = False, raw: bool = False):
    args = ["gh", "api", endpoint]
    if pages:
        args += ["--paginate", "--slurp"]
    try:
        if raw:
            args.extend(_raw_output_flags())
        result = subprocess.run(args, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        raise PublicationError(
            f"GitHub API request failed for {endpoint} (exit {exc.returncode}): "
            f"{_safe_api_error(exc.stderr)}"
        ) from None
    if raw:
        return result.stdout
    data = json.loads(result.stdout)
    return [item for page in data for item in page] if pages else data


def _deployed_request(repository: str) -> tuple[str, int, dict]:
    """Find the last successful publish step, regardless of its enclosing job outcome."""
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repository):
        raise PublicationError("Invalid repository name")
    base = f"repos/{repository}"
    deployments = _api(f"{base}/deployments?environment=github-pages&per_page=100", pages=True)
    candidates = {}
    unconfirmed = {}
    jobs = {}
    for deployment in deployments:
        statuses = _api(f"{base}/deployments/{deployment['id']}/statuses?per_page=100", pages=True)
        # Environment success/failure describes the entire job. A later state-save
        # failure does not undo a successful Pages deployment earlier in that job.
        for status in statuses:
            url = status.get("log_url", "")
            if not url and status["state"] in ("queued", "pending", "waiting"):
                continue
            match = re.fullmatch(
                rf"https://github\.com/{re.escape(repository)}/actions/runs/(\d+)/job/(\d+)",
                url,
                flags=re.IGNORECASE,
            )
            if not match:
                raise PublicationError("Deployment has no same-repository run/job log URL")
            run_id, job_id = map(int, match.groups())
            if job_id not in jobs:
                jobs[job_id] = _api(f"{base}/actions/jobs/{job_id}")
            job = jobs[job_id]
            if (
                job["id"] != job_id
                or job["run_id"] != run_id
                or job["head_sha"] != deployment["sha"]
            ):
                raise PublicationError("Deployment/job/SHA provenance mismatch")
            publish_steps = [
                step
                for step in job["steps"]
                if re.match(r"^Run actions/deploy-pages@", step["name"])
            ]
            deploy_steps = [
                step
                for step in publish_steps
                if step.get("status") == "completed" and step.get("conclusion") == "success"
            ]
            for number, attempted in enumerate(publish_steps):
                if attempted in deploy_steps or attempted.get("conclusion") == "skipped":
                    continue
                if attempted.get("status") in ("queued", "pending") and not attempted.get(
                    "started_at"
                ):
                    continue
                # The POST may have published before a polling failure/cancellation.
                # Only a later confirmed publish can supersede that uncertainty.
                unconfirmed[job_id, number] = attempted.get("completed_at")
            if len(deploy_steps) > 1:
                raise PublicationError("Ambiguous successful actions/deploy-pages steps")
            if deploy_steps:
                step = deploy_steps[0]
                candidates[job_id] = (
                    _time(step["completed_at"]),
                    deployment["sha"],
                    run_id,
                    job_id,
                    job,
                    step,
                )
    if not candidates:
        raise PublicationError("No successful actions/deploy-pages step; full map refresh required")
    latest = max(candidate[0] for candidate in candidates.values())
    if any(end is None or _time(end) >= latest for end in unconfirmed.values()):
        raise PublicationError(
            "Unconfirmed Pages publication after the last known success; full map refresh required"
        )
    selected = [candidate for candidate in candidates.values() if candidate[0] == latest]
    if len(selected) != 1:
        raise PublicationError("Ambiguous latest successful Pages deployment step")
    _, sha, run_id, job_id, job, step = selected[0]
    run = _api(f"{base}/actions/runs/{run_id}")
    if (
        run["id"] != run_id
        or run["repository"]["full_name"].lower() != repository.lower()
        or run["head_repository"]["id"] != run["repository"]["id"]
        or run["head_sha"] != sha
    ):
        raise PublicationError("Deployment, job, run, repository, or SHA provenance mismatch")
    if job.get("run_attempt") != run.get("run_attempt"):
        raise PublicationError("Run was rerun after the deployed job; refusing ambiguous artifact")
    start, end = _time(step["started_at"]), _time(step["completed_at"])
    logs = _api(f"{base}/actions/jobs/{job_id}/logs", raw=True).decode("utf-8")
    lines = []
    for line in logs.splitlines():
        timestamp, _, content = line.partition(" ")
        try:
            within_step = start <= _time(timestamp) <= end
        except ValueError:
            continue
        if within_step:
            lines.append(content)
    log = "\n".join(lines)
    payloads = []
    for match in re.finditer(r"Creating Pages deployment with payload:\s*", log):
        try:
            payload, _ = json.JSONDecoder().raw_decode(log[match.end() :])
        except json.JSONDecodeError as exc:
            raise PublicationError("Malformed deploy-pages request payload") from exc
        payloads.append(payload)
    if len(payloads) != 1 or payloads[0].get("pages_build_version") != sha:
        raise PublicationError("Missing or ambiguous deployed artifact request payload")
    artifact_id = payloads[0].get("artifact_id")
    if not isinstance(artifact_id, int) or isinstance(artifact_id, bool):
        raise PublicationError("Invalid deployed artifact ID")
    return sha, artifact_id, run


def deployed_revision(repository: str) -> str:
    """Return the proven deployed source SHA without downloading site archives."""
    sha, _, _ = _deployed_request(repository)
    return sha


def deployed_artifact(repository: str, *, now: datetime | None = None) -> int:
    """Prove artifact identity from the latest successful deploy-pages request."""
    sha, artifact_id, run = _deployed_request(repository)
    base = f"repos/{repository}"
    run_id = run["id"]
    artifact = _api(f"{base}/actions/artifacts/{artifact_id}")
    provenance = artifact.get("workflow_run", {})
    repository_id = run["repository"]["id"]
    if (
        artifact["id"] != artifact_id
        or artifact["name"] != "github-pages"
        or provenance.get("id") != run_id
        or provenance.get("head_sha") != sha
        or provenance.get("repository_id") != repository_id
        or provenance.get("head_repository_id") != repository_id
    ):
        raise PublicationError("Deployed artifact repository/run/SHA provenance mismatch")
    if artifact["expired"] or _time(artifact["expires_at"]) <= (now or datetime.now(UTC)):
        raise PublicationError("Deployed Pages artifact expired; full map refresh required")
    return artifact_id


def _path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if "\\" in name or path.is_absolute() or ".." in path.parts:
        raise PublicationError(f"Unsafe archive path: {name!r}")
    return path


def _extract(archive: bytes, destination: Path) -> None:
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        entries = zipped.infolist()
        for entry in entries:
            _path(entry.filename)
            mode = entry.external_attr >> 16
            if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG)):
                raise PublicationError("Pages ZIP contains a non-regular file")
        if len(entries) != 1 or entries[0].filename != "artifact.tar":
            raise PublicationError("Pages ZIP must contain exactly artifact.tar")
        with tarfile.open(fileobj=io.BytesIO(zipped.read(entries[0]))) as tar:
            members = tar.getmembers()
            seen = set()
            for member in members:
                path = _path(member.name)
                if not (member.isfile() or member.isdir()) or path in seen:
                    raise PublicationError(
                        "Pages TAR contains links, special files, or duplicate paths"
                    )
                seen.add(path)
                if path == PurePosixPath(".") and not member.isdir():
                    raise PublicationError("Invalid Pages TAR root")
            # Validate all members before writing even the first file.
            for member in members:
                target = destination / _path(member.name)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with tar.extractfile(member) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)


def _demo_owned(path: PurePosixPath) -> bool:
    return path.as_posix() in ("embeddings.html", "dinov3/embeddings.html") or (
        path.suffix == ".json"
        and path.parent.as_posix() in ("embeddings-data", "dinov3/embeddings-data")
    )


def _demo_files(demo: Path) -> dict[PurePosixPath, Path]:
    if demo.is_symlink() or not demo.is_dir():
        raise PublicationError("Demo must be a regular directory")
    files = {}
    for path in demo.rglob("*"):
        relative = PurePosixPath(path.relative_to(demo).as_posix())
        if path.is_symlink() or (not path.is_dir() and not path.is_file()):
            raise PublicationError(f"Non-regular demo path: {relative}")
        if path.is_dir():
            if relative.as_posix() not in ("dinov3", "embeddings-data", "dinov3/embeddings-data"):
                raise PublicationError(f"Unexpected demo directory: {relative}")
            continue
        if not _demo_owned(relative):
            raise PublicationError(f"Demo cannot replace non-demo path: {relative}")
        content = path.read_text(encoding="utf-8")
        if path.suffix == ".json":
            data = json.loads(content)
            if (
                not isinstance(data, dict)
                or data.get("group") != path.stem
                or not isinstance(data.get("records"), list)
                or not data["records"]
            ):
                raise PublicationError(f"Malformed demo group data: {relative}")
        elif "<html" not in content.lower() or "</html>" not in content.lower():
            raise PublicationError(f"Malformed demo HTML: {relative}")
        files[relative] = path
    for prefix in (PurePosixPath("."), PurePosixPath("dinov3")):
        if prefix / "embeddings.html" not in files or not any(
            path.parent == prefix / "embeddings-data" for path in files
        ):
            raise PublicationError(f"Missing demo page or group data: {prefix}")
    return files


def _preserved_files(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file() and not _demo_owned(PurePosixPath(path.relative_to(root).as_posix()))
    }


def prepare_site(repository: str, demo: Path, output: Path) -> int:
    """Build a new directory atomically, preserving every non-demo file byte for byte."""
    if output.exists() or output.is_symlink():
        raise PublicationError("Output already exists; refusing to replace it")
    files = _demo_files(demo)
    artifact_id = deployed_artifact(repository)
    archive = _api(f"repos/{repository}/actions/artifacts/{artifact_id}/zip", raw=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".pages-overlay-", dir=output.parent) as temporary:
        stage = Path(temporary) / "site"
        stage.mkdir()
        _extract(archive, stage)
        if not all(
            (stage / name).is_file() and (stage / name).stat().st_size
            for name in ("index.html", "map.html")
        ) or not any(path.stat().st_size for path in stage.glob("pool*.bin") if path.is_file()):
            raise PublicationError("Deployed artifact lacks the complete index/map/pool site")
        preserved = _preserved_files(stage)
        for path in stage.rglob("*"):
            if path.is_file() and _demo_owned(PurePosixPath(path.relative_to(stage).as_posix())):
                path.unlink()
        for relative, source in files.items():
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        if _preserved_files(stage) != preserved:
            raise PublicationError("Non-demo site contents changed; refusing publication")
        os.rename(stage, output)
    return artifact_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--demo", type=Path, default=Path("demo"))
    parser.add_argument("--out", type=Path, default=Path("full_site"))
    parser.add_argument(
        "--revision", action="store_true", help="Print the deployed source SHA only"
    )
    args = parser.parse_args()
    try:
        if args.revision:
            print(deployed_revision(args.repository))
            return
        artifact_id = prepare_site(args.repository, args.demo, args.out)
    except (
        PublicationError,
        subprocess.CalledProcessError,
        OSError,
        ValueError,
        KeyError,
        zipfile.BadZipFile,
        tarfile.TarError,
    ) as exc:
        parser.exit(1, f"Pages demo overlay refused: {exc}\nThe current live site is unchanged.\n")
    print(f"Prepared demo overlay from deployed artifact {artifact_id}: {args.out}")


if __name__ == "__main__":
    main()
