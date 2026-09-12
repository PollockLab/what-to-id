"""Build the blitz participants file that ``analysis --users`` reads.

Participants come from one of two sources: members of an iNaturalist project (identifiers who
joined the blitz project), or a list of logins collected through a sign-up form. Either way the
output is the plain user-id-per-line file ``analysis._users`` parses: a ``#`` comment line naming
the source and date, then sorted unique ids, one per line.
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import requests

from what_to_id.inat import TIMEOUT, make_session

API = "https://api.inaturalist.org/v1"
PER_PAGE = 100
SLEEP = 1.0


def _get(session: requests.Session, url: str, **params) -> dict:
    r = session.get(url, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def resolve_project_id(
    project: str,
    *,
    session: requests.Session | None = None,
) -> int:
    """A numeric id is returned as-is; a slug is resolved via ``/projects/{slug}``."""
    if project.strip().lstrip("-").isdigit():
        return int(project)
    session = session or make_session()
    data = _get(session, f"{API}/projects/{project}")
    results = data.get("results") or []
    if not results:
        raise ValueError(f"no iNaturalist project found for {project!r}")
    return int(results[0]["id"])


def fetch_project_members(
    project: str,
    *,
    session: requests.Session | None = None,
    per_page: int = PER_PAGE,
    sleep: float = SLEEP,
    log: Callable[[str], None] = print,
) -> list[int]:
    """User ids of every member of ``project`` (numeric id or slug), paginated."""
    if not 1 <= per_page <= PER_PAGE:
        raise ValueError(f"per_page must be between 1 and {PER_PAGE}, got {per_page}")
    session = session or make_session()
    project_id = resolve_project_id(project, session=session)
    ids: list[int] = []
    page = 1
    while True:
        data = _get(session, f"{API}/projects/{project_id}/members", page=page, per_page=per_page)
        results = data.get("results") or []
        if not results:
            break
        for row in results:
            uid = (row.get("user") or {}).get("id", row.get("user_id"))
            if uid is None:
                raise ValueError(f"member row without a user id: {row!r}")
            ids.append(int(uid))
        log(f"project {project_id} page {page}: {len(results)} members, total {len(ids)}")
        if len(results) < per_page:
            break
        page += 1
        if sleep:
            time.sleep(sleep)
    return ids


def fetch_user_ids_by_login(
    logins: Sequence[str],
    *,
    session: requests.Session | None = None,
    sleep: float = SLEEP,
    log: Callable[[str], None] = print,
) -> list[int]:
    """Resolve each login to a user id via ``/users/{login}``; raise naming any that fail."""
    session = session or make_session()
    ids: list[int] = []
    unresolved: list[str] = []
    for i, login in enumerate(logins):
        try:
            data = _get(session, f"{API}/users/{login}")
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            if status == 404:
                unresolved.append(login)
                continue
            raise
        results = data.get("results") or []
        if not results:
            unresolved.append(login)
            continue
        ids.append(int(results[0]["id"]))
        log(f"{login} -> {results[0]['id']}")
        if sleep and i + 1 < len(logins):
            time.sleep(sleep)
    if unresolved:
        raise ValueError(f"could not resolve iNaturalist login(s): {', '.join(unresolved)}")
    return ids


def read_logins(path: Path) -> list[str]:
    """One iNaturalist login per line; blank lines and ``#`` comments are skipped."""
    lines = [ln.strip() for ln in path.read_text().splitlines()]
    logins = [ln for ln in lines if ln and not ln.startswith("#")]
    if not logins:
        raise ValueError(f"{path}: no logins found")
    return logins


def write_participants(ids: Sequence[int], out: Path, *, source: str) -> None:
    """Write the ``analysis --users`` file: a comment line, then sorted unique ids."""
    unique = sorted({int(i) for i in ids})
    if not unique:
        raise ValueError(f"no participants to write for {source}")
    date = datetime.now(UTC).strftime("%Y-%m-%d")
    lines = [f"# participants from {source}, {date}", *(str(i) for i in unique)]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write the blitz participants file.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--project", help="iNaturalist project id or slug; members are participants")
    src.add_argument("--logins", type=Path, help="file of iNaturalist logins, one per line")
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    if a.project:
        ids = fetch_project_members(a.project)
        source = f"project {a.project}"
    else:
        logins = read_logins(a.logins)
        ids = fetch_user_ids_by_login(logins)
        source = f"logins {a.logins}"
    write_participants(ids, a.out, source=source)
    print(f"{len(set(ids))} participants -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
