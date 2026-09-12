"""End-to-end: build -> deal batches to simulated participants -> readback -> analysis.

Proves the whole chain detects a planted per-identifier treatment effect (lift=0.5) and does
not invent one when there is none (lift=0.0), on a small synthetic pool with the rotation
design. Participants are dealt an equal number of batches from every arm, as the rotation page
does; a handful of non-participant users add identifications too, to check that ``--users``
excludes them from the test.
"""

from __future__ import annotations

import contextlib
import io
from pathlib import Path

import numpy as np
import pandas as pd

from what_to_id import analysis, readback
from what_to_id.cli import main as cli_main

from .conftest import make_pool, write_webapp

N_PARTICIPANTS = 30
BATCHES_PER_ARM = 4
P_CONTROL = 0.3
START = "2026-09-15T00:00:00Z"
CUTOFF = "2026-09-29T00:00:00Z"
CONTROL_ARM = "recency"
TREATMENT_ARM = "gap_first"
N_NOISE_USERS = 5
# Tried seeds 0, 1, 2 for the null (lift=0.0) case; all give Holm p far above 0.05. Seed 0 is
# used for both cases below.
SEED = 0


def _build(tmp_path: Path) -> tuple[Path, pd.DataFrame]:
    webapp_dir = write_webapp(tmp_path)
    pool = make_pool(220, seed=5, groups=["Aves"])
    pool_path = tmp_path / "pool.parquet"
    pool.to_parquet(pool_path, index=False)
    out = tmp_path / "out"
    rc = cli_main(
        [
            "build",
            "--pool",
            str(pool_path),
            "--freeze",
            "2026-09-01",
            "--d1",
            "2026-09-15",
            "--seed",
            "3",
            "--batch-size",
            "5",
            "--max-batches",
            "8",
            "--arms",
            f"{CONTROL_ARM},{TREATMENT_ARM}",
            "--webapp-dir",
            str(webapp_dir),
            "--design",
            "rotation",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    return out, pd.read_parquet(out / "batches.parquet")


def _deal(batches: pd.DataFrame) -> dict[tuple[int, str], list[str]]:
    """Round-robin each participant an equal share of batches from every arm, per rotation."""
    work: dict[tuple[int, str], list[str]] = {}
    for arm, sub in batches.groupby("arm"):
        bids = sorted(sub["batch_id"].unique())
        k = len(bids)
        for uid in range(1, N_PARTICIPANTS + 1):
            offset = (uid - 1) % k
            work[(uid, arm)] = [bids[(offset + j) % k] for j in range(BATCHES_PER_ARM)]
    return work


def _simulate(
    batches: pd.DataFrame, work: dict[tuple[int, str], list[str]], *, lift: float, rng
) -> tuple[dict[int, set[int]], dict[int, list[tuple[int, pd.Timestamp]]], list[int]]:
    """Per worked record: mark the worker reviewed, and add a species identification with
    probability p_control (control arm) or p_control * (1 + lift) (treatment arm)."""
    start = pd.Timestamp(START)
    cutoff = pd.Timestamp(CUTOFF)
    span = (cutoff - start).total_seconds()
    bid_records = batches.groupby("batch_id")["id"].apply(list)
    reviewed: dict[int, set[int]] = {int(rid): set() for rid in batches["id"]}
    idents: dict[int, list[tuple[int, pd.Timestamp]]] = {int(rid): [] for rid in batches["id"]}
    for (uid, arm), bids in work.items():
        p = P_CONTROL if arm == CONTROL_ARM else P_CONTROL * (1 + lift)
        for bid in bids:
            for rid in bid_records[bid]:
                reviewed[int(rid)].add(uid)
                if rng.random() < p:
                    ts = start + pd.Timedelta(seconds=rng.uniform(0, span))
                    idents[int(rid)].append((uid, ts))
    noise_users = list(range(9001, 9001 + N_NOISE_USERS))
    all_ids = batches["id"].unique()
    for nuid in noise_users:
        picks = rng.choice(all_ids, size=min(10, len(all_ids)), replace=False)
        for rid in picks:
            ts = start + pd.Timedelta(seconds=rng.uniform(0, span))
            idents[int(rid)].append((nuid, ts))
    return reviewed, idents, noise_users


def _fake_obs(
    batches: pd.DataFrame,
    reviewed: dict[int, set[int]],
    idents: dict[int, list[tuple[int, pd.Timestamp]]],
) -> list[dict]:
    """Raw iNaturalist-shaped observation dicts, matching test_readback.py's OBS/_ident shape."""
    obs = []
    for rid in batches["id"].unique():
        rid = int(rid)
        idn = idents[rid]
        obs.append(
            {
                "id": rid,
                "quality_grade": "needs_id",
                "community_taxon": None,
                "taxon": {"id": 1, "rank": "species"},
                "identifications_count": len(idn),
                "reviewed_by": sorted(reviewed[rid]),
                "identifications": [
                    {
                        "user": {"id": int(u)},
                        "created_at": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "taxon": {"id": 1, "rank": "species"},
                        "current": True,
                    }
                    for u, ts in idn
                ],
            }
        )
    return obs


def _rows_after_header(text: str, header_marker: str) -> list[dict[str, str]]:
    """Parse the pipe table whose header line contains ``header_marker`` into row dicts."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("|") and header_marker in line:
            headers = [h.strip() for h in line.strip("|").split("|")]
            rows = []
            j = i + 2  # skip the "|---|...|" divider
            while j < len(lines) and lines[j].startswith("|"):
                cells = [c.strip() for c in lines[j].strip("|").split("|")]
                rows.append(dict(zip(headers, cells, strict=True)))
                j += 1
            return rows
    raise AssertionError(f"header {header_marker!r} not found in:\n{text}")


def _run_chain(tmp_path: Path, out: Path, batches: pd.DataFrame, *, lift: float) -> str:
    work = _deal(batches)
    rng = np.random.default_rng(SEED)
    reviewed, idents, noise_users = _simulate(batches, work, lift=lift, rng=rng)
    obs_list = _fake_obs(batches, reviewed, idents)
    ids = [int(i) for i in batches["id"].unique()]
    obs_df, idents_df = readback.readback(ids, fetch=lambda ids_: obs_list)
    assert set(noise_users) <= set(idents_df["user_id"].unique())

    obs_path = tmp_path / f"obs_{lift}.parquet"
    idents_path = tmp_path / f"idents_{lift}.parquet"
    obs_df.to_parquet(obs_path, engine="pyarrow", index=False)
    idents_df.to_parquet(idents_path, engine="pyarrow", index=False)
    users_path = tmp_path / "users.txt"
    users_path.write_text("\n".join(str(u) for u in range(1, N_PARTICIPANTS + 1)))

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = analysis.main(
            [
                "--idents",
                str(idents_path),
                "--served",
                str(out / "batches.parquet"),
                "--control",
                CONTROL_ARM,
                "--start",
                START,
                "--cutoff",
                CUTOFF,
                "--users",
                str(users_path),
                "--obs",
                str(obs_path),
            ]
        )
    assert rc == 0
    return buf.getvalue()


def test_e2e_detects_planted_effect(tmp_path):
    out, batches = _build(tmp_path)
    text = _run_chain(tmp_path, out, batches, lift=0.5)
    row = next(r for r in _rows_after_header(text, "p_holm") if r["arm"] == TREATMENT_ARM)
    assert float(row["p_holm"]) < 0.05


def test_e2e_null_does_not_invent_effect(tmp_path):
    out, batches = _build(tmp_path)
    text = _run_chain(tmp_path, out, batches, lift=0.0)
    row = next(r for r in _rows_after_header(text, "p_holm") if r["arm"] == TREATMENT_ARM)
    assert float(row["p_holm"]) > 0.05
    assert int(row["n_identifiers"]) == N_PARTICIPANTS


def test_e2e_exposure_is_balanced_across_arms(tmp_path):
    out, batches = _build(tmp_path)
    text = _run_chain(tmp_path, out, batches, lift=0.0)
    expo_rows = _rows_after_header(text, "n_users")
    shares = {r["arm"]: float(r["share"]) for r in expo_rows}
    assert abs(shares[CONTROL_ARM] - shares[TREATMENT_ARM]) < 0.05
