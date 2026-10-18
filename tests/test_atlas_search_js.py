"""The browser index reader reproduces `atlas_index.search` and `lookup_neighbors` over Range."""

import json
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from what_to_id.atlas_neighbors import lookup_neighbors, write_neighbor_records

from .atlas_index_fixture import write_fixture

ASSETS = Path(__file__).parents[1] / "src/what_to_id/atlas_search_assets"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")
pytest.importorskip("faiss")

# A file-backed fetch that honours Range like the real host and records every request.
HARNESS = """
const fs = require('fs'), path = require('path');
const IDX = require(%(index)r), META = require(%(meta)r), ENC = require(%(enc)r);
const DIR = %(dir)r, requests = [];
function fakeFetch(url, opts) {
  const name = url.replace('http://data.test/atlas/', ''), file = path.join(DIR, name);
  if (!fs.existsSync(file)) return Promise.resolve(new Response('', {status: 404}));
  const buf = fs.readFileSync(file), r = opts && opts.headers && opts.headers.Range;
  if (!r) { requests.push({name, bytes: buf.length}); return Promise.resolve(new Response(buf)); }
  const [a, b] = r.replace('bytes=', '').split('-').map(Number);
  requests.push({name, bytes: b - a + 1, start: a});
  return Promise.resolve(new Response(buf.subarray(a, b + 1), {status: 206}));
}
const out = (v) => console.log(JSON.stringify(v));
"""


def node(script, directory=None, timeout=120):
    pre = HARNESS % {
        "index": str(ASSETS / "atlas_search_index.js"),
        "meta": str(ASSETS / "atlas_search_meta.js"),
        "enc": str(ASSETS / "atlas_search_encoder.js"),
        "dir": str(directory or "."),
    }
    done = subprocess.run(
        [NODE], input=pre + script, capture_output=True, text=True, check=False, timeout=timeout
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.fixture(scope="module")
def fixture(tmp_path_factory):
    directory = tmp_path_factory.mktemp("atlas-fixture")
    return directory, write_fixture(directory)


def probed_bytes(directory, query, nprobe):
    """Expected id+code bytes for the probed lists of every part, from the files themselves."""
    mf = json.loads((directory / "manifest.json").read_text())
    c = np.fromfile(directory / "centroids.f16", dtype="<f2").reshape(mf["nlist"], mf["dims"])
    coarse = c.astype(np.float32) @ np.asarray(query, dtype=np.float32)
    probe = np.argsort(-coarse, kind="stable")[:nprobe]
    total = 0
    for part in mf["parts"]:
        off = np.fromfile(directory / f"{part['name']}.offsets.u32", dtype="<u4").astype(np.int64)
        total += int((off[probe + 1] - off[probe]).sum()) * (4 + mf["m"])
    return total


def test_search_matches_python_reference_exactly(fixture):
    directory, ref = fixture
    script = f"""(async () => {{
      const ref = {json.dumps({"q": ref["queries"], "s": ref["searches"], "k": ref["k"]})};
      const res = [];
      for (const s of ref.s) {{
        const idx = await IDX.open('http://data.test/atlas/', {{fetch: fakeFetch}});
        const per = [];
        for (const q of ref.q)
          per.push(await idx.search(Float32Array.from(q), {{k: ref.k, nprobe: s.nprobe}}));
        res.push(per);
      }}
      out(res);
    }})()"""
    got = node(script, directory)
    for per, expected in zip(got, ref["searches"], strict=True):
        for hits, ids, scores in zip(per, expected["ids"], expected["scores"], strict=True):
            n = sum(1 for i in ids if i != -1)
            assert [h["id"] for h in hits] == ids[:n]
            assert max(ids) > 2**31, "fixture should exercise ids above int32"
            np.testing.assert_allclose([h["score"] for h in hits], scores[:n], atol=1e-4)
    assert any(h["id"] > 2**31 for per in got for hits in per for h in hits)


def test_range_reads_fetch_only_probed_lists(fixture):
    directory, ref = fixture
    mf = json.loads((directory / "manifest.json").read_text())
    data_total = sum(
        (directory / f"{p['name']}.{ext}").stat().st_size
        for p in mf["parts"]
        for ext in ("ids.u32", "codes.u8")
    )
    query = ref["queries"][0]
    script = f"""(async () => {{
      const idx = await IDX.open('http://data.test/atlas/', {{fetch: fakeFetch}});
      const q = Float32Array.from({json.dumps(query)});
      const report = [];
      for (const nprobe of [1, 4, 16]) {{
        requests.length = 0;
        const fresh = await IDX.open('http://data.test/atlas/', {{fetch: fakeFetch}});
        await fresh.search(q, {{k: 10, nprobe}});
        const first = requests.filter(r => r.name.includes('.ids.') || r.name.includes('.codes.'));
        const again = requests.length;
        await fresh.search(q, {{k: 10, nprobe}});
        report.push({{nprobe, data: first.reduce((a, r) => a + r.bytes, 0), n: first.length,
                     cachedExtra: requests.length - again}});
      }}
      out(report);
    }})()"""
    for row in node(script, directory):
        assert row["data"] == probed_bytes(directory, query, row["nprobe"])
        assert row["cachedExtra"] == 0, "repeat query must hit the list cache"
        if row["nprobe"] == 16:  # every list: all ranges are adjacent, one per file per part
            assert row["n"] == 2 * len(mf["parts"]) and row["data"] == data_total
        else:
            assert row["data"] < data_total


def test_neighbors_match_python_reference(fixture):
    directory, ref = fixture
    script = f"""(async () => {{
      const idx = await IDX.open('http://data.test/atlas/', {{fetch: fakeFetch}});
      const res = [];
      for (const id of {json.dumps([r["id"] for r in ref["lookups"]])}) {{
        requests.length = 0;
        const got = await idx.neighbors(id);
        res.push({{got, bytes: requests.reduce((a, r) => a + r.bytes, 0)}});
      }}
      out(res);
    }})()"""
    got = node(script, directory)
    size = 4 + 6 * 12
    for g, expected in zip(got, ref["lookups"], strict=True):
        if expected["neighbors"] is None:
            assert g["got"] is None
            continue
        ids, cos = expected["neighbors"]
        assert [n["id"] for n in g["got"]] == ids
        np.testing.assert_allclose([n["score"] for n in g["got"]], cos, atol=1e-6)
        assert g["bytes"] <= 256 * size + 4 * 16, "one block (plus the directory once)"


def test_neighbors_newest_set_wins(fixture, tmp_path):
    # a daily delta set overrides the base set for ids it holds, as lookup_neighbors does
    directory = tmp_path / "atlas"
    shutil.copytree(fixture[0], directory)
    base_id = fixture[1]["lookups"][0]["id"]
    new_id = 2**32 - 5
    write_neighbor_records(
        directory, "delta", [base_id, new_id], np.full((2, 12), 7), np.full((2, 12), 0.5), 2
    )
    ids = [base_id, new_id, fixture[1]["lookups"][1]["id"]]
    got = node(
        f"""(async () => {{
      const idx = await IDX.open('http://data.test/atlas/', {{fetch: fakeFetch}});
      const res = [];
      for (const id of {json.dumps(ids)}) res.push(await idx.neighbors(id));
      out(res);
    }})()""",
        directory,
    )
    for g, obs in zip(got, ids, strict=True):
        found = lookup_neighbors(directory, obs)
        assert (g is None) == (found is None)
        if found is not None:
            assert [n["id"] for n in g] == found[0].tolist()
    assert got[0][0]["id"] == 7 and got[1][0]["id"] == 7


def test_pure_functions():
    got = node("""(() => {
      const bits = [0, 1, 0x3ff, 0x400, 0x3c00, 0x7bff, 0x7c00, 0xfc00, 0x7e00,
        0x8000, 0xc000, 0x0001];
      const f16 = bits.map(b => String(IDX.f16ToF32(b)));
      const tk = IDX.topk([1, 3, 3, 2, 3], [10, 11, 12, 13, 14], 3);
      const co = IDX.coalesce([[10, 20], [0, 5], [5, 8], [20, 30], [40, 40], [50, 60]], 0);
      const pq = new Float32Array(2 * 256 * 2).fill(1);
      const lut = IDX.buildLut(Float32Array.from([1, 2, 3, 4]), pq, 2);
      const codes = Uint8Array.from([0, 1, 255, 0]), s = new Float32Array(2);
      IDX.adc(0.5, lut, codes, 2, s, 0);
      out({f16, tk, co, lut: [lut[0], lut[256]], s: Array.from(s)});
    })()""")
    expect = np.array(
        [0, 1, 0x3FF, 0x400, 0x3C00, 0x7BFF, 0x7C00, 0xFC00, 0x7E00, 0x8000, 0xC000, 1]
    )
    for text, want in zip(got["f16"], expect.astype("<u2").view("<f2").astype(float), strict=True):
        have = float({"Infinity": "inf", "-Infinity": "-inf"}.get(text, text))
        assert (math.isnan(want) and math.isnan(have)) or have == want
    assert got["tk"] == [{"id": 11, "score": 3}, {"id": 12, "score": 3}, {"id": 14, "score": 3}]
    assert got["co"] == [[0, 8], [10, 30], [50, 60]]
    assert got["lut"] == [3, 7] and got["s"] == [10.5, 10.5]


def test_meta_parsing_and_filtering():
    got = node("""(() => {
      const P = META.parseInput, H = META.parseHash;
      const obs = (id, grade, anc) => ({id, quality_grade: grade, observed_on: '2026-01-01',
        place_guess: 'BC', photos: [{url: 'https://x/photos/1/square.jpg'}],
        taxon: anc && {name: 'T' + id, ancestor_ids: anc}});
      const cache = new Map([[1, obs(1, 'needs_id', [1, 47170])], [2, obs(2, 'research', [2])],
        [3, obs(3, 'needs_id', [3, 54743])], [5, obs(5, 'needs_id', null)], [4, null]]);
      const hits = [1, 2, 3, 4, 5, 6].map(id => ({id, score: 0.5}));
      const b = (f) => META.build(hits, cache, f);
      out({
        parse: [P('  4294967295 '), P('https://www.inaturalist.org/observations/123?x=1'), P('0'),
          P('a bird eating a frog'), P('4294967296'), P('  '), P('#77')],
        hash: [H('#id=5'), H('#q=a+bird%20eating'), H('#id=x&q=y'), H(''),
          META.toHash({kind: 'text', text: 'a b&c'}),
          META.toHash({kind: 'id', id: 9})],
        small: META.smallPhoto('https://x/photos/1/square.jpg'),
        all: (({cards, ...r}) => [cards.map(c => c.id), c0(cards), r])(b()),
        inc: b({include: [47170]}).cards.map(c => c.id),
        exc: b({exclude: [47170]}).cards.map(c => c.id),
        both: b({include: [47170, 54743], exclude: [54743]}).cards.map(c => c.id),
      });
      function c0(cards) { return cards[0].photo; }
    })()""")
    assert got["parse"] == [
        {"kind": "id", "id": 4294967295},
        {"kind": "id", "id": 123},
        {"kind": "text", "text": "0"},
        {"kind": "text", "text": "a bird eating a frog"},
        {"kind": "text", "text": "4294967296"},
        None,
        {"kind": "id", "id": 77},
    ]
    assert got["hash"] == [
        {"kind": "id", "id": 5},
        {"kind": "text", "text": "a bird eating"},
        {"kind": "text", "text": "y"},
        None,
        "#q=a+b%26c",
        "#id=9",
    ]
    assert got["small"] == "https://x/photos/1/small.jpg"
    ids, photo, rest = got["all"]
    assert ids == [1, 3, 5] and photo.endswith("/small.jpg")
    assert rest == {"notNeedsId": 1, "missing": 2, "filtered": 0}
    assert got["inc"] == [1] and got["exc"] == [3, 5] and got["both"] == [1]


def test_text_encoder_wraps_tokens_and_normalizes():
    got = node("""(async () => {
      const seen = {};
      const ort = {Tensor: class {
        constructor(t, d, s) { this.type = t; this.data = d; this.dims = s; }
      }};
      const session = {run: async (feeds) => {
        const t = feeds.tok; seen.type = t.type; seen.dims = t.dims; seen.big = typeof t.data[0];
        seen.head = Array.from(t.data.slice(0, 3), String);
        return {emb: {data: new Float32Array([3, 0, 4, 0])}};
      }};
      const tokenizer = {tokenize: (s) => {
        seen.text = s;
        return [49406, 5, 49407, ...Array(74).fill(0)];
      }};
      const enc = ENC.make(ort, session, tokenizer, {input_name: 'tok', output_name: 'emb'});
      let err = null;
      try { await ENC.load({}, 'http://x/', {}); } catch (e) { err = e.message; }
      const v = Array.from(await enc.encode('hi'));
      out({v, seen, mb: ENC.megabytes({bytes: 508673577}), err});
    })()""")
    assert got["v"] == pytest.approx([0.6, 0, 0.8, 0])
    assert got["seen"] == {
        "type": "int64",
        "dims": [1, 77],
        "big": "bigint",
        "head": ["49406", "5", "49407"],
        "text": "hi",
    }
    assert got["mb"] == 485 and "no text search model" in got["err"]


def test_text_encoder_load_finds_page_globals():
    # the real page passes no tokenizer, so load must read ClipTokenizer from the page's globals
    got = node("""(async () => {
      globalThis.ClipTokenizer = {create: (v) => ({tokenize: () => [49406, 49407], vocab: v})};
      const ort = {Tensor: class { constructor(t, d, s) { this.data = d; } },
        InferenceSession: {create: async () => ({run: async () => ({embedding: {data: [0, 2]}})})}};
      const fetch = async () => new Response('merges');
      const manifest = {text_encoder: {onnx: 'm.onnx', vocab: 'v.txt'}};
      const enc = await ENC.load(manifest, 'http://x/', {ort, fetch});
      out(Array.from(await enc.encode('moss')));
    })()""")
    assert got == [0, 1]
