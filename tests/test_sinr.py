import numpy as np
import pandas as pd
import pytest

from what_to_id.sinr import features, load, main, sinr_scores

# Taxa: genus 10 with species 11 (and its subspecies 12) and species 13; species 14 is not in
# the model.
TAXA = pd.DataFrame(
    {
        "taxon_id": [10, 11, 12, 13, 14],
        "ancestry": ["1", "1/10", "1/10/11", "1/10", "1/10"],
        "rank_level": [20, 10, 5, 10, 10],
    }
)


def _weights(depth: int = 1, filts: int = 3) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(0)
    z = {
        "feats__0__weight": rng.normal(size=(filts, 4)).astype(np.float32),
        "feats__0__bias": rng.normal(size=filts).astype(np.float32),
        "class_emb__weight": rng.normal(size=(2, filts)).astype(np.float32),
        "class_to_taxa": np.array([11, 13]),
        "depth": np.array(depth),
    }
    for i in range(2, 2 + depth):
        for w in ("w1", "w2"):
            z[f"feats__{i}__{w}__weight"] = rng.normal(size=(filts, filts)).astype(np.float32)
            z[f"feats__{i}__{w}__bias"] = rng.normal(size=filts).astype(np.float32)
    return z


def test_features_match_the_residual_net_by_hand():
    z = _weights()
    loc = np.array([[-123.1, 49.3]])
    x = np.array([[-123.1 / 180, 49.3 / 90]])
    x = np.concatenate([np.sin(np.pi * x), np.cos(np.pi * x)], axis=1)
    h = np.maximum(x @ z["feats__0__weight"].T + z["feats__0__bias"], 0)
    y = np.maximum(h @ z["feats__2__w1__weight"].T + z["feats__2__w1__bias"], 0)
    h = h + np.maximum(y @ z["feats__2__w2__weight"].T + z["feats__2__w2__bias"], 0)
    np.testing.assert_allclose(features(z, loc), h, rtol=1e-5)


def test_scores_species_in_the_model_and_climbs_subspecies():
    pool = pd.DataFrame(
        {
            "id": [1, 2, 3, 4, 5, 6],
            "lat": [49.3, 49.3, 49.3, 49.3, 49.3, np.nan],
            "lon": [-123.1, -123.1, -123.1, -123.1, -123.1, -123.1],
            "taxon_id": [11, 12, 13, 14, 10, 11],
        }
    )
    s = sinr_scores(pool, TAXA, _weights())
    assert s["id"].tolist() == [1, 2, 3]
    assert s.loc[0, "sinr_rel"] == pytest.approx(s.loc[1, "sinr_rel"])
    assert ((s["sinr_rel"] > 0) & (s["sinr_rel"] <= 1.05)).all()


def test_peak_location_scores_one():
    z = _weights()
    pool = pd.DataFrame({"id": [1], "lat": [0.0], "lon": [0.0], "taxon_id": [11]})
    lon, lat = np.meshgrid(np.arange(-180.0, 180.0, 0.5), np.arange(-90.0, 90.25, 0.5))
    grid = np.column_stack([lon.ravel(), lat.ravel()])
    best = grid[np.argmax(features(z, grid) @ z["class_emb__weight"][0])]
    pool[["lon", "lat"]] = [best]
    assert sinr_scores(pool, TAXA, z)["sinr_rel"].iloc[0] == pytest.approx(1.0, rel=1e-5)


def test_empty_pool_gives_empty_scores():
    pool = pd.DataFrame({"id": [1], "lat": [49.0], "lon": [-123.0], "taxon_id": [14]})
    assert sinr_scores(pool, TAXA, _weights()).empty


def test_load_rejects_an_npz_without_the_residual_layers(tmp_path):
    z = _weights(depth=2)
    del z["feats__3__w2__bias"]
    np.savez(tmp_path / "bad.npz", **z)
    with pytest.raises(ValueError, match="not a SINR residual-net export"):
        load(str(tmp_path / "bad.npz"))


def test_main_writes_id_and_sinr_rel(tmp_path):
    np.savez(tmp_path / "w.npz", **_weights())
    pool = pd.DataFrame(
        {"id": [1, 2], "lat": [49.3, 49.3], "lon": [-123.1, -123.1], "taxon_id": [11, 14]}
    )
    pool.to_parquet(tmp_path / "pool.parquet", index=False)
    TAXA.to_csv(tmp_path / "taxa.csv.gz", sep="\t", index=False)
    args = [str(tmp_path / "pool.parquet"), "--weights", str(tmp_path / "w.npz")]
    args += ["--taxa", str(tmp_path / "taxa.csv.gz"), "--out", str(tmp_path / "s.parquet")]
    assert main(args) == 0
    out = pd.read_parquet(tmp_path / "s.parquet")
    assert out.columns.tolist() == ["id", "sinr_rel"] and out["id"].tolist() == [1]
