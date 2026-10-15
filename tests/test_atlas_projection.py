"""Measure display distortion without treating visual proximity as identification."""

import numpy as np
import pytest

from what_to_id.atlas_projection import projection_fidelity


def test_reports_the_actual_loss_in_a_distorted_display():
    neighbors = np.array([[1], [0], [3], [2]])
    quality, counts = projection_fidelity(np.array([[0, 0], [1, 0], [2, 0], [3, 0]]), neighbors)
    assert counts.tolist() == [1, 1, 0, 1]
    assert quality["mean_neighbor_recall"] == 0.75
    distorted, counts = projection_fidelity(np.array([[0, 0], [3, 0], [1, 0], [2, 0]]), neighbors)
    assert counts.tolist() == [0, 0, 0, 0]
    assert distorted["mean_neighbor_recall"] == 0


def test_coincident_points_use_a_reproducible_tie_rule_and_exclude_self():
    coordinates = np.zeros((4, 2))
    neighbors = np.array([[1, 2], [0, 2], [0, 1], [0, 1]])
    quality, counts = projection_fidelity(coordinates, neighbors)
    assert counts.tolist() == [2, 2, 2, 2]
    assert quality["k"] == 2
    assert quality["mean_neighbor_recall"] == 1


def test_matches_an_independent_scalar_ranking_across_blocks():
    rng = np.random.default_rng(42)
    coordinates = np.round(rng.normal(size=(137, 2)), 1)
    neighbors = np.array(
        [rng.choice([j for j in range(137) if j != i], 12, replace=False) for i in range(137)]
    )
    expected = []
    for i, point in enumerate(coordinates):
        ordered = sorted(
            (sum((float(a) - float(b)) ** 2 for a, b in zip(point, other, strict=True)), j)
            for j, other in enumerate(coordinates)
            if j != i
        )
        local = {j for _, j in ordered[:12]}
        expected.append(len(local.intersection(neighbors[i])))
    quality, actual = projection_fidelity(coordinates, neighbors)
    assert actual.tolist() == expected
    assert quality["mean_neighbor_recall"] == pytest.approx(sum(expected) / (137 * 12))


def test_payload_diagnoses_the_emitted_coordinates_and_exact_ranked_matches(tmp_path):
    import pandas as pd

    from what_to_id.embedding_atlas import group_payload

    rng = np.random.default_rng(7)
    vectors = rng.normal(size=(15, 8)).astype("f4")
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    ids = np.arange(1, 16)
    cache = tmp_path / "plants.npz"
    np.savez(cache, ids=ids, E=vectors, backbone="fixture")
    pool = pd.DataFrame(
        {
            "id": ids,
            "iconic_taxon": "Plantae",
            "lon": -123,
            "lat": 49,
            "taxon_name": "Recorded plant",
            "photo_url": "",
            "observed_on": "2026-09-11",
        }
    )
    payload = group_payload(pool, cache, "Plantae")
    records = payload["records"]
    expected = []
    for i, row in enumerate(records):
        ordered = sorted(
            (sum((a - b) ** 2 for a, b in zip(row["xy"], other["xy"], strict=True)), j)
            for j, other in enumerate(records)
            if j != i
        )
        actual_matches = {j for j, _ in row["neighbors"]}
        expected.append(len(actual_matches.intersection(j for _, j in ordered[:12])))
    assert [row["projection_match_count"] for row in records] == expected
    assert payload["projection_quality"]["k"] == 12
    assert payload["projection_quality"]["mean_neighbor_recall"] == pytest.approx(
        sum(expected) / (15 * 12)
    )


@pytest.mark.parametrize(
    ("coordinates", "neighbors", "message"),
    [
        (np.zeros((1, 2)), [[0]], "shape"),
        (np.zeros((3, 3)), [[1], [0], [0]], "shape"),
        ([[0, 0], [1, float("nan")], [2, 2]], [[1], [0], [0]], "finite"),
        (np.zeros((3, 2)), [[1.0], [0.0], [0.0]], "integer"),
        (np.zeros((3, 2)), [[3], [0], [0]], "existing"),
        (np.zeros((3, 2)), [[-1], [0], [0]], "existing"),
        (np.zeros((3, 2)), [[0], [0], [0]], "own"),
        (np.zeros((3, 2)), [[1, 1], [0, 2], [0, 1]], "unique"),
        (np.zeros((3, 2)), np.zeros((3, 0), dtype=int), "integer"),
    ],
)
def test_rejects_missing_or_invalid_evidence(coordinates, neighbors, message):
    with pytest.raises(ValueError, match=message):
        projection_fidelity(coordinates, neighbors)
