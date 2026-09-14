import numpy as np
import pandas as pd
import pytest

from what_to_id.served_log import COLUMNS, append_served, served_rows

LABELS = {"recency": "B", "gap_first": "A"}


def _batches(ids_by_arm):
    rows = []
    for arm, ids in ids_by_arm.items():
        for i, rid in enumerate(ids):
            rows.append(
                {
                    "batch_id": f"{arm}-Aves-{i // 2:03d}",
                    "arm": arm,
                    "group": "Aves",
                    "position": i % 2,
                    "id": rid,
                }
            )
    return pd.DataFrame(rows)


def _pool(ids, scores):
    return pd.DataFrame({"id": ids, "cell_score": scores})


def test_served_rows_labels_only_and_scores():
    b = _batches({"recency": [1, 2, 3], "gap_first": [4]})
    rows = served_rows(b, LABELS, _pool([1, 2, 3, 4], [0.1, np.nan, 0.3, 0.9]), "2026-11-03")
    assert list(rows.columns) == COLUMNS
    assert "arm" not in rows.columns
    assert not rows.astype(str).apply(lambda c: c.str.contains("recency|gap_first")).any().any()
    assert rows["label"].tolist() == ["B", "B", "B", "A"]
    assert rows["batch_index"].tolist() == [0, 0, 1, 0]
    assert rows["cell_score"].iloc[0] == 0.1 and np.isnan(rows["cell_score"].iloc[1])
    assert (rows["build_date"] == "2026-11-03").all()


def test_served_rows_missing_label_raises():
    b = _batches({"recency": [1], "novelty": [2]})
    with pytest.raises(ValueError, match="no list letter"):
        served_rows(b, LABELS, _pool([1, 2], [0.1, 0.2]), "2026-11-03")


def test_served_rows_without_cell_score_column():
    b = _batches({"recency": [1]})
    rows = served_rows(b, LABELS, pd.DataFrame({"id": [1]}), "2026-11-03")
    assert np.isnan(rows["cell_score"].iloc[0])


def test_append_accumulates_and_replaces_same_day(tmp_path):
    p = tmp_path / "state" / "served.parquet"
    pool = _pool([1, 2, 3], [0.1, 0.2, 0.3])
    append_served(p, served_rows(_batches({"recency": [1, 2]}), LABELS, pool, "2026-11-03"))
    append_served(p, served_rows(_batches({"recency": [2, 3]}), LABELS, pool, "2026-11-04"))
    # a rerun of 11-04 replaces that day's rows instead of doubling them
    log = append_served(p, served_rows(_batches({"recency": [3]}), LABELS, pool, "2026-11-04"))
    assert log.groupby("build_date")["id"].apply(list).to_dict() == {
        "2026-11-03": [1, 2],
        "2026-11-04": [3],
    }
    assert pd.read_parquet(p).equals(log)
    assert not (tmp_path / "state" / "served.parquet.tmp").exists()


def test_append_refuses_record_changing_letter(tmp_path):
    p = tmp_path / "served.parquet"
    pool = _pool([1, 2], [0.1, 0.2])
    append_served(p, served_rows(_batches({"recency": [1]}), LABELS, pool, "2026-11-03"))
    moved = served_rows(_batches({"gap_first": [1]}), LABELS, pool, "2026-11-04")
    with pytest.raises(ValueError, match="changed list letter"):
        append_served(p, moved)


def test_append_rejects_wrong_columns(tmp_path):
    with pytest.raises(ValueError, match="columns"):
        append_served(tmp_path / "s.parquet", pd.DataFrame({"id": [1]}))
