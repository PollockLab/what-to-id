import numpy as np
import pandas as pd

from what_to_id.confusion import confused_pairs, confusion_scores, prototype_scores


def _unit(v):
    v = np.asarray(v, dtype=np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def test_mislabelled_row_sits_closer_to_the_other_prototype():
    rng = np.random.default_rng(0)
    a = _unit(rng.normal(size=(5, 8)) + np.r_[10, 0, 0, 0, 0, 0, 0, 0])
    b = _unit(rng.normal(size=(5, 8)) + np.r_[0, 10, 0, 0, 0, 0, 0, 0])
    E = np.vstack([a, b])
    labels = np.array([1] * 5 + [2] * 4 + [1])  # the last b-row is labelled as a
    n_class, own, other, other_label = prototype_scores(E, labels)
    assert n_class.tolist() == [6] * 5 + [4] * 4 + [6]
    assert (own[:5] > other[:5]).all()
    assert own[9] < other[9] and other_label[9] == 2
    assert other_label[0] == 2


def test_small_classes_and_singletons_score_nan():
    E = _unit(np.eye(4))
    n_class, own, other, other_label = prototype_scores(E, np.array([1, 1, 1, 2]), min_per_class=3)
    assert np.isnan(own[3]) and n_class[3] == 1
    # The only prototype has no other to compare with.
    assert np.isnan(other[:3]).all() and (other_label[:3] == -1).all()
    assert np.isfinite(own[:3]).all()


def test_confusion_scores_joins_species_rows_to_embeddings():
    E = _unit(np.eye(7))
    ids = np.array([10, 11, 12, 13, 14, 15, 16])
    pool = pd.DataFrame(
        {
            "id": [10, 11, 12, 13, 14, 15, 16],
            "taxon_id": [1, 1, 1, 1, 2, 2, 2],
            "rank": ["species"] * 4 + ["genus", "species", "species"],
        }
    )
    out = confusion_scores(pool, E, ids, min_per_class=2)
    assert out["id"].tolist() == [10, 11, 12, 13, 15, 16]
    assert out.loc[out.taxon_id == 1, "other_taxon_id"].eq(2).all()
    assert out.loc[out.taxon_id == 2, "other_taxon_id"].eq(1).all()
    assert out["margin"].notna().all()


def test_confused_pairs_counts_negative_margins_per_pair():
    scores = pd.DataFrame(
        {
            "taxon_id": [1, 1, 2, 1],
            "other_taxon_id": [2, 2, 1, 3],
            "margin": [-0.1, -0.2, -0.3, 0.1],
        }
    )
    out = confused_pairs(scores, pd.Series({1: "a", 2: "b", 3: "c"}))
    assert out[["taxon", "looks_like", "n"]].values.tolist() == [["a", "b", 2], ["b", "a", 1]]
