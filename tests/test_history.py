from datetime import UTC, datetime

from what_to_id.history import active, community_taxon, days_to_research, relation, state

# life > plants(1) > genus 10 > species 11, 12; genus 20 > species 21 (other branch)
RL = {1: 70, 10: 20, 11: 10, 12: 10, 20: 20, 21: 10}
ANC = {1: [], 10: [1], 11: [1, 10], 12: [1, 10], 20: [1], 21: [1, 20]}


def ident(user, taxon, when, own=False, current=True):
    return {
        "user": {"id": user},
        "taxon": {"id": taxon, "ancestor_ids": ANC[taxon]},
        "created_at": f"2025-09-{when:02d}T00:00:00+00:00",
        "own_observation": own,
        "current": current,
    }


def at(day):
    return datetime(2025, 9, day, tzinfo=UTC)


def test_two_agreeing_species_ids_make_research_grade():
    obs = {"identifications": [ident(1, 11, 1, own=True), ident(2, 11, 2)]}
    s = state(obs, None, RL)
    assert s["research"] and s["taxon"] == 11


def test_single_id_is_needs_id_with_observer_taxon():
    obs = {"identifications": [ident(1, 11, 1, own=True)]}
    s = state(obs, None, RL)
    assert not s["research"] and s["taxon"] == 11 and s["n_ids"] == 1


def test_species_disagreement_falls_back_to_genus():
    lins = [(1, 10, 11), (1, 10, 12)]
    assert community_taxon(lins, RL) == 10


def test_two_to_one_is_not_above_two_thirds():
    lins = [(1, 10, 11), (1, 10, 11), (1, 20, 21)]
    assert community_taxon(lins, RL) == 1
    lins.append((1, 10, 11))
    assert community_taxon(lins, RL) == 11


def test_active_keeps_each_persons_latest_id_before_t():
    idents = [ident(1, 10, 1, own=True, current=False), ident(1, 11, 5, own=True), ident(2, 21, 3)]
    got = {i["user"]["id"]: i["taxon"]["id"] for i in active(idents, at(4))}
    assert got == {1: 10, 2: 21}
    assert {i["taxon"]["id"] for i in active(idents, None)} == {11, 21}


def test_state_at_t_ignores_later_ids_and_days_to_research():
    obs = {"identifications": [ident(1, 11, 1, own=True), ident(2, 11, 10)]}
    assert not state(obs, at(5), RL)["research"]
    assert days_to_research(obs, at(5), RL) == 5.0


def test_relation():
    assert relation((1, 10), (1, 10, 11)) == "refined"
    assert relation((1, 10, 11), (1, 10)) == "coarsened"
    assert relation((1, 10, 11), (1, 20, 21)) == "corrected"
    assert relation((1, 10, 11), (1, 10, 11)) == "same"
    assert relation((), (1,)) == "none"
