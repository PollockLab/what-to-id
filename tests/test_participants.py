import re

import pytest

from what_to_id import analysis, participants


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            err = requests.HTTPError(f"{self.status_code}")
            err.response = self
            raise err

    def json(self):
        return self._payload


class FakeSession:
    """Maps a URL to a queue of responses; each ``get`` pops the next one for that URL."""

    def __init__(self, routes):
        self.routes = {url: list(pages) for url, pages in routes.items()}
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        queue = self.routes.get(url)
        if not queue:
            raise AssertionError(f"no fake response queued for {url}")
        return queue.pop(0)


def _members_page(user_ids):
    return FakeResponse({"results": [{"user_id": u, "user": {"id": u}} for u in user_ids]})


def test_resolve_project_id_numeric_skips_fetch():
    sess = FakeSession({})
    assert participants.resolve_project_id("123", session=sess) == 123
    assert sess.calls == []


def test_resolve_project_id_slug_resolves():
    sess = FakeSession(
        {
            f"{participants.API}/projects/my-bioblitz": [
                FakeResponse({"results": [{"id": 999, "slug": "my-bioblitz"}]})
            ]
        }
    )
    assert participants.resolve_project_id("my-bioblitz", session=sess) == 999


def test_resolve_project_id_slug_not_found():
    sess = FakeSession({f"{participants.API}/projects/nope": [FakeResponse({"results": []})]})
    with pytest.raises(ValueError, match="no iNaturalist project"):
        participants.resolve_project_id("nope", session=sess)


def test_fetch_project_members_paginates_by_numeric_id():
    url = f"{participants.API}/projects/42/members"
    sess = FakeSession({url: [_members_page([1, 2]), _members_page([3])]})
    ids = participants.fetch_project_members("42", session=sess, per_page=2, sleep=0)
    assert ids == [1, 2, 3]
    assert [c[1]["page"] for c in sess.calls] == [1, 2]


def test_fetch_project_members_resolves_slug_first():
    slug_url = f"{participants.API}/projects/my-bioblitz"
    members_url = f"{participants.API}/projects/999/members"
    sess = FakeSession(
        {
            slug_url: [FakeResponse({"results": [{"id": 999}]})],
            members_url: [_members_page([5])],
        }
    )
    ids = participants.fetch_project_members("my-bioblitz", session=sess, sleep=0)
    assert ids == [5]


def test_fetch_project_members_stops_on_short_page():
    url = f"{participants.API}/projects/1/members"
    sess = FakeSession({url: [_members_page([1, 2])]})
    ids = participants.fetch_project_members("1", session=sess, per_page=10, sleep=0)
    assert ids == [1, 2]


def test_fetch_project_members_bad_per_page():
    with pytest.raises(ValueError, match="per_page"):
        participants.fetch_project_members("1", session=FakeSession({}), per_page=0)
    with pytest.raises(ValueError, match="per_page"):
        participants.fetch_project_members("1", session=FakeSession({}), per_page=101)


def test_fetch_project_members_row_without_user_id_raises():
    url = f"{participants.API}/projects/1/members"
    sess = FakeSession({url: [FakeResponse({"results": [{"role": "curator"}]})]})
    with pytest.raises(ValueError, match="user id"):
        participants.fetch_project_members("1", session=sess, sleep=0)


def test_fetch_user_ids_by_login_resolves_each():
    sess = FakeSession(
        {
            f"{participants.API}/users/alice": [FakeResponse({"results": [{"id": 11}]})],
            f"{participants.API}/users/bob": [FakeResponse({"results": [{"id": 22}]})],
        }
    )
    ids = participants.fetch_user_ids_by_login(["alice", "bob"], session=sess, sleep=0)
    assert ids == [11, 22]


def test_fetch_user_ids_by_login_names_unresolved():
    sess = FakeSession(
        {
            f"{participants.API}/users/alice": [FakeResponse({"results": [{"id": 11}]})],
            f"{participants.API}/users/ghost": [FakeResponse({"error": "not found"}, status=404)],
            f"{participants.API}/users/void": [FakeResponse({"results": []})],
        }
    )
    with pytest.raises(ValueError, match=re.escape("ghost, void")):
        participants.fetch_user_ids_by_login(["alice", "ghost", "void"], session=sess, sleep=0)


def test_read_logins_skips_blank_and_comments(tmp_path):
    p = tmp_path / "logins.txt"
    p.write_text("# sign-up form\nalice\n\n  bob  \n# trailing\n")
    assert participants.read_logins(p) == ["alice", "bob"]


def test_read_logins_empty_raises(tmp_path):
    p = tmp_path / "empty.txt"
    p.write_text("# only a comment\n")
    with pytest.raises(ValueError, match="no logins"):
        participants.read_logins(p)


def test_write_participants_sorts_and_dedupes(tmp_path):
    out = tmp_path / "participants.txt"
    participants.write_participants([30, 10, 10, 20], out, source="project 1")
    text = out.read_text()
    lines = text.splitlines()
    assert lines[0].startswith("# participants from project 1, ")
    assert lines[1:] == ["10", "20", "30"]


def test_write_participants_empty_raises(tmp_path):
    with pytest.raises(ValueError, match="no participants"):
        participants.write_participants([], tmp_path / "out.txt", source="project 1")


def test_write_participants_round_trips_through_analysis_users(tmp_path):
    out = tmp_path / "participants.txt"
    participants.write_participants([30, 10, 20], out, source="project 1")
    assert analysis._users(out) == [10, 20, 30]


def test_main_project_writes_file(tmp_path, monkeypatch, capsys):
    out = tmp_path / "participants.txt"
    monkeypatch.setattr(participants, "fetch_project_members", lambda project: [2, 1, 1])
    rc = participants.main(["--project", "42", "--out", str(out)])
    assert rc == 0
    assert analysis._users(out) == [1, 2]
    assert "2 participants" in capsys.readouterr().out


def test_main_logins_writes_file(tmp_path, monkeypatch):
    logins_path = tmp_path / "logins.txt"
    logins_path.write_text("alice\nbob\n")
    out = tmp_path / "participants.txt"
    monkeypatch.setattr(participants, "fetch_user_ids_by_login", lambda logins: [11, 22])
    rc = participants.main(["--logins", str(logins_path), "--out", str(out)])
    assert rc == 0
    assert analysis._users(out) == [11, 22]


def test_main_requires_exactly_one_source(tmp_path):
    out = tmp_path / "participants.txt"
    with pytest.raises(SystemExit):
        participants.main(["--out", str(out)])
    with pytest.raises(SystemExit):
        participants.main(["--project", "1", "--logins", "x.txt", "--out", str(out)])


@pytest.mark.network
def test_fetch_project_members_live_project():
    ids = participants.fetch_project_members("167912", sleep=0)
    assert len(ids) >= 1
    assert all(isinstance(i, int) for i in ids)


@pytest.mark.network
def test_resolve_project_id_live_slug():
    assert (
        participants.resolve_project_id("city-nature-challenge-2024-south-florida-cncsoflo")
        == 167912
    )
