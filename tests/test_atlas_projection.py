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


def _vectors(count=36, dimensions=8):
    vectors = np.random.default_rng(37).normal(size=(count, dimensions)).astype(np.float32)
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def _payload_inputs(tmp_path, vectors):
    import pandas as pd

    ids = np.arange(101, 101 + len(vectors))
    cache = tmp_path / "plants.npz"
    np.savez(cache, ids=ids, E=vectors, backbone="fixture")
    pool = pd.DataFrame(
        {
            "id": ids,
            "iconic_taxon": "Plantae",
            "lon": -123,
            "lat": 49,
            "taxon_name": "Recorded identification",
            "photo_url": "",
            "observed_on": "2026-09-11",
        }
    )
    return pool.iloc[::-1], cache


@pytest.fixture
def atlas_dependencies():
    sklearn = pytest.importorskip("sklearn", reason="install the optional atlas build dependencies")
    assert sklearn.__version__ == "1.9.1", "atlas tests require the pinned scikit-learn build"


@pytest.mark.atlas
@pytest.mark.parametrize("count", [3, 4, 15, 30, 31])
def test_real_tsne_handles_small_samples_with_an_explicit_actual_perplexity(
    count, atlas_dependencies
):
    from what_to_id.atlas_projection import display_projection
    from what_to_id.embedding_atlas import representation_projection

    vectors = _vectors(count)
    pca, *_ = representation_projection(vectors)
    coordinates, metadata = display_projection(vectors, pca, method="tsne")
    assert coordinates.shape == (count, 2)
    assert np.isfinite(coordinates).all()
    assert metadata["method"] == "t-SNE"
    assert metadata["fallback_reason"] is None
    assert metadata["parameters"]["perplexity"] == min(30, count - 1)
    assert metadata["small_sample_perplexity_adjusted"] is (count <= 30)


@pytest.mark.atlas
def test_real_tsne_payload_reproduces_the_fit_and_preserves_retrieval_and_linear_view(
    tmp_path, atlas_dependencies
):
    from sklearn.manifold import TSNE
    from threadpoolctl import threadpool_limits

    from what_to_id.embedding_atlas import group_payload

    vectors = _vectors()
    untouched = vectors.copy()
    pool, cache = _payload_inputs(tmp_path, vectors)
    baseline = group_payload(pool, cache, "Plantae", reference_path=cache, reference_pool=pool)
    actual = group_payload(
        pool, cache, "Plantae", reference_path=cache, reference_pool=pool, projection="tsne"
    )
    # Fit the evaluated public algorithm independently of the builder and compare its
    # emitted precision, instead of merely asserting that kwargs were forwarded.
    with threadpool_limits(limits=1):
        expected = TSNE(
            n_components=2,
            perplexity=30,
            learning_rate="auto",
            early_exaggeration=12,
            max_iter=1000,
            metric="euclidean",
            init="pca",
            method="barnes_hut",
            angle=0.5,
            n_jobs=1,
            random_state=0,
        ).fit_transform(vectors)
    np.testing.assert_array_equal(
        [record["xy"] for record in actual["records"]],
        np.round(expected.astype(np.float64), 6),
    )
    np.testing.assert_array_equal(vectors, untouched)
    assert actual["projection"] == "t-SNE"
    assert actual["reference"] == baseline["reference"]
    assert actual["representation_colors"] == baseline["representation_colors"]
    assert actual["variance_retained"] == baseline["variance_retained"]
    assert actual["pca_projection_quality"] == baseline["projection_quality"]
    for original, projected in zip(baseline["records"], actual["records"], strict=True):
        assert projected["pca_xy"] == original["xy"]
        assert projected["pca_projection_match_count"] == original["projection_match_count"]
        for key in original.keys() - {"xy", "projection_match_count"}:
            assert projected[key] == original[key]
    quality, matches = projection_fidelity(
        np.array([record["xy"] for record in actual["records"]]),
        np.array([[j for j, _ in record["neighbors"]] for record in actual["records"]]),
    )
    assert actual["projection_quality"] == quality
    assert [record["projection_match_count"] for record in actual["records"]] == matches.tolist()
    metadata = actual["projection_metadata"]
    assert metadata["sklearn_version"] == "1.9.1"
    assert metadata["source_vectors_dtype"] == "float32"
    assert metadata["source_vectors_renormalized"] is False
    assert metadata["display_only"] is True


@pytest.mark.parametrize(
    ("vectors", "reason"),
    [
        (np.ones((5, 1), dtype=np.float32), "fewer than two source features"),
        (np.tile([1, 0, 0], (5, 1)).astype(np.float32), "constant source vectors"),
        (
            np.array([[1, 0, 0], [-1, 0, 0], [1, 0, 0], [-1, 0, 0]], dtype=np.float32),
            "fewer than two varying PCA axes",
        ),
    ],
)
def test_degenerate_cohorts_explicitly_fall_back_to_padded_pca(tmp_path, vectors, reason):
    from what_to_id.embedding_atlas import group_payload

    pool, cache = _payload_inputs(tmp_path, vectors)
    baseline = group_payload(pool, cache, "Plantae")
    actual = group_payload(pool, cache, "Plantae", projection="tsne")
    assert actual["projection"] == "PCA"
    assert actual["projection_metadata"]["requested_method"] == "t-SNE"
    assert actual["projection_metadata"]["fallback_reason"] == reason
    assert actual["projection_metadata"]["sklearn_version"] is None
    assert actual["projection_quality"] == actual["pca_projection_quality"]
    assert [r["xy"] for r in actual["records"]] == [r["xy"] for r in baseline["records"]]
    assert all(r["xy"] == r["pca_xy"] for r in actual["records"])
    assert all(len(r["xy"]) == 2 and np.isfinite(r["xy"]).all() for r in actual["records"])


def test_pca_stays_available_without_the_optional_dependency(monkeypatch):
    import sys

    from what_to_id.atlas_projection import display_projection
    from what_to_id.embedding_atlas import representation_projection

    vectors = _vectors()
    pca, *_ = representation_projection(vectors)
    monkeypatch.setitem(sys.modules, "sklearn", None)
    coordinates, metadata = display_projection(vectors, pca)
    np.testing.assert_array_equal(coordinates, pca)
    assert metadata["method"] == "PCA"
    with pytest.raises(RuntimeError, match="optional atlas build dependencies"):
        display_projection(vectors, pca, method="tsne")


@pytest.mark.atlas
def test_an_unverified_sklearn_version_fails_explicitly(monkeypatch, atlas_dependencies):
    import sklearn

    from what_to_id.atlas_projection import display_projection
    from what_to_id.embedding_atlas import representation_projection

    vectors = _vectors()
    pca, *_ = representation_projection(vectors)
    monkeypatch.setattr(sklearn, "__version__", "0.0.0")
    with pytest.raises(RuntimeError, match="requires scikit-learn==1.9.1"):
        display_projection(vectors, pca, method="tsne")


@pytest.mark.parametrize(
    ("vectors", "pca", "method", "message"),
    [
        (_vectors(2), np.zeros((2, 2)), "tsne", "three rows"),
        (_vectors().astype(np.float64), np.zeros((36, 2)), "tsne", "float32"),
        (np.full((3, 2), np.nan, dtype=np.float32), np.zeros((3, 2)), "tsne", "finite"),
        (_vectors(), np.zeros((36, 1)), "tsne", "PCA coordinates"),
        (_vectors(), np.full((36, 2), np.inf), "tsne", "PCA coordinates"),
        (_vectors(), np.zeros((36, 2)), "unknown", "method"),
    ],
)
def test_projection_rejects_invalid_inputs(vectors, pca, method, message):
    from what_to_id.atlas_projection import display_projection

    with pytest.raises(ValueError, match=message):
        display_projection(vectors, pca, method=method)


@pytest.mark.atlas
def test_duplicate_vectors_keep_all_observations_and_exact_tie_rankings(
    tmp_path, atlas_dependencies
):
    from what_to_id.embedding_atlas import group_payload

    vectors = np.repeat(_vectors(4), 2, axis=0)
    pool, cache = _payload_inputs(tmp_path, vectors)
    actual = group_payload(pool, cache, "Plantae", projection="tsne")
    baseline = group_payload(pool, cache, "Plantae")
    assert len(actual["records"]) == len(vectors)
    assert actual["projection"] == "t-SNE"
    assert np.isfinite([r["xy"] for r in actual["records"]]).all()
    assert [r["neighbors"] for r in actual["records"]] == [
        r["neighbors"] for r in baseline["records"]
    ]


@pytest.mark.atlas
def test_cli_explicit_projection_writes_a_real_tsne_payload(
    tmp_path, monkeypatch, atlas_dependencies
):
    import json
    import sys

    from what_to_id.embedding_atlas import main

    pool, cache = _payload_inputs(tmp_path, _vectors(15))
    pool_path = tmp_path / "pool.parquet"
    pool.to_parquet(pool_path)
    destination = tmp_path / "site"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "atlas",
            "--pool",
            str(pool_path),
            "--embeddings",
            str(cache),
            "--out",
            str(destination),
            "--snapshot-date",
            "2026-09-11",
            "--projection",
            "tsne",
        ],
    )
    main()
    payload = json.loads((destination / "embeddings-data/Plantae.json").read_text())
    assert payload["projection"] == "t-SNE"
    assert payload["projection_metadata"]["parameters"]["perplexity"] == 14
    assert all("pca_xy" in row for row in payload["records"])
