"""The photo-space readers decode the layout parts and map shards and join them by id."""

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from what_to_id.page_map import decode_points, encode_points, render_map

from .embeddings_fixture import BBOX, layout_part_bytes, pool_frame

ASSET = Path(__file__).parents[1] / "src/what_to_id/embeddings_assets/embeddings_layout.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def node(script):
    pre = f"const L = require({str(ASSET)!r}), fs = require('fs');\n"
    pre += "const ab = (f) => { const b = fs.readFileSync(f); return b.buffer.slice(b.byteOffset, "
    pre += "b.byteOffset + b.byteLength); };\n"
    done = subprocess.run([NODE], input=pre + script, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    """Pool of 500 ids, a base layout missing some of them, and a delta that moves and adds some."""
    d = tmp_path_factory.mktemp("layout-js")
    rng = np.random.default_rng(7)
    ids = np.sort(rng.choice(2**32 - 2, 530, replace=False) + 1)  # ids above 2**31 on purpose
    pool_ids, outside = ids[:500], ids[500:]  # `outside` is in the layout only: left Needs ID
    base_ids = np.concatenate([pool_ids[:420], outside])
    base_xy = np.column_stack(
        [rng.uniform(BBOX[0], BBOX[2], len(base_ids)), rng.uniform(BBOX[1], BBOX[3], len(base_ids))]
    )
    moved = pool_ids[:20]  # in the base too: the delta wins
    fresh = pool_ids[460:480]  # not in the base
    delta_ids = np.concatenate([moved, fresh])
    delta_xy = np.column_stack(
        [rng.uniform(BBOX[0], BBOX[2], 40), rng.uniform(BBOX[1], BBOX[3], 40)]
    )
    (d / "base.bin").write_bytes(layout_part_bytes(base_ids, base_xy))
    (d / "delta.bin").write_bytes(layout_part_bytes(delta_ids, delta_xy))
    pool = pool_frame(pool_ids)
    blobs, meta = encode_points(pool)
    for name, blob in blobs.items():
        (d / name).write_bytes(blob)
    (d / "map.html").write_text(render_map(meta, freeze=None))
    expected = {}
    for part_ids, xy in ((base_ids, base_xy), (delta_ids, delta_xy)):
        for i, x, y in zip(part_ids.tolist(), *xy.T.tolist(), strict=True):
            if i in set(pool_ids.tolist()):
                expected[i] = (x, y)
    return d, meta, pool, expected, (base_ids, delta_ids)


def test_decode_part_round_trips_ids_and_coordinates(world):
    d, _, _, _, (base_ids, _) = world
    got = node(
        f"""
(async () => {{
  const p = L.decodePart(await L.gunzip(ab({str(d / "base.bin")!r})), {len(base_ids)});
  console.log(JSON.stringify({{id: Array.from(p.id), qx: Array.from(p.qx), qy: Array.from(p.qy)}}));
}})();"""
    )
    assert got["id"] == base_ids.tolist()
    assert max(got["qx"]) <= 65535 and len(got["qy"]) == len(base_ids)


def test_decode_part_rejects_a_wrong_size(world):
    d, *_ = world
    script = f"""
(async () => {{
  try {{ L.decodePart(await L.gunzip(ab({str(d / "base.bin")!r})), 5); console.log('"no"'); }}
  catch (e) {{ console.log(JSON.stringify(e.message)); }}
}})();"""
    assert "expected 40" in node(script)


def test_join_places_pool_records_by_id_and_later_parts_win(world):
    d, meta, pool, expected, (base_ids, delta_ids) = world
    shards = ", ".join(
        f"L.decodeShard(await L.gunzip(ab({str(d / s['file'])!r})), {s['n']})"
        for s in meta["shards"]
    )
    got = node(
        f"""
(async () => {{
  const shards = [{shards}];
  const parts = [
    L.decodePart(await L.gunzip(ab({str(d / "base.bin")!r})), {len(base_ids)}),
    L.decodePart(await L.gunzip(ab({str(d / "delta.bin")!r})), {len(delta_ids)})];
  const P = L.join(shards, parts, {BBOX}, {meta["bbox"]});
  console.log(JSON.stringify({{n: P.n, id: Array.from(P.id), pos: Array.from(P.pos),
    lonlat: Array.from(P.lonlat), grp: Array.from(P.grp), start: P.start,
    found: Array.from(P.id).map((i) => L.find(P, i)), missing: L.find(P, 1)}}));
}})();"""
    )
    assert got["n"] == len(expected) == 440  # 420 base + 20 fresh delta, moved ones counted once
    assert sorted(got["id"]) == sorted(expected)
    assert got["found"] == list(range(got["n"])) and got["missing"] == -1
    assert got["start"][0] == 0 and got["start"][-1] == got["n"]
    truth = decode_points(
        {n: (d / n).read_bytes() for n in (*(s["file"] for s in meta["shards"]), meta["taxa"])},
        meta,
    ).set_index("id")
    for k, i in enumerate(got["id"]):
        x, y = expected[i]
        assert got["pos"][2 * k] == pytest.approx(x, abs=100 / 65535)
        assert got["pos"][2 * k + 1] == pytest.approx(y, abs=60 / 65535)
        assert got["lonlat"][2 * k] == pytest.approx(truth.lon[i], abs=1e-4)
        assert got["lonlat"][2 * k + 1] == pytest.approx(truth.lat[i], abs=1e-4)
        assert meta["groups"][got["grp"][k]] == truth.iconic_taxon[i]


def test_join_with_no_parts_or_no_overlap_is_empty(world):
    d, meta, *_ = world
    s = meta["shards"][0]
    got = node(
        f"""
(async () => {{
  const sh = L.decodeShard(await L.gunzip(ab({str(d / s["file"])!r})), {s["n"]});
  const none = L.join([sh], [], {BBOX}, {meta["bbox"]});
  const one = {{n: 1, id: Uint32Array.of(1), qx: Uint16Array.of(0), qy: Uint16Array.of(0)}};
  const far = L.join([sh], [one], {BBOX}, {meta["bbox"]});
  console.log(JSON.stringify([none.n, far.n, L.find(none, 5)]));
}})();"""
    )
    assert got == [0, 0, -1]


def test_map_meta_is_read_from_the_rendered_map_page(world):
    d, meta, *_ = world
    got = node(
        f"""
const m = L.parseMapMeta(fs.readFileSync({str(d / "map.html")!r}, 'utf8'));
let err = '';
try {{ L.parseMapMeta('<html></html>'); }} catch (e) {{ err = e.message; }}
console.log(JSON.stringify({{n: m.n, shards: m.shards, taxa: m.taxa, bbox: m.bbox, err}}));"""
    )
    assert got["n"] == meta["n"] and got["bbox"] == meta["bbox"]
    assert got["shards"][0]["file"].startswith("pool-0.bin?v=") and got["taxa"].startswith(
        "pool-taxa"
    )
    assert "map data" in got["err"]


def test_fidelity_reads_the_recall_or_any_fraction():
    got = node(
        """
console.log(JSON.stringify([
  L.fidelity({k: 12, mean_neighbor_recall: 0.61}), L.fidelity({top12: 0.4}), L.fidelity(0.5),
  L.fidelity({metric: 'x'}), L.fidelity(null)]));"""
    )
    assert got == [
        {"value": 0.61, "k": 12},
        {"value": 0.4, "k": 12},
        {"value": 0.5, "k": 12},
        None,
        None,
    ]
