"""Browser text encoder: JS CLIP tokenizer parity with open_clip, and quantized ONNX parity."""

import json
import os
import random
import shutil
import subprocess
from pathlib import Path

import pytest

ASSETS = Path(__file__).parents[1] / "src/what_to_id/atlas_assets"
NODE = shutil.which("node")


def taxon_names(count=20, seed=7):
    rng = random.Random(seed)
    parts = ["pseud", "acris", "lob", "aria", "pulmon", "quer", "cus", "gar", "ryana", "thu", "ja"]
    names = []
    for _ in range(count):
        genus = rng.choice(parts).title() + rng.choice(parts)
        names.append(f"a photo of {genus} {rng.choice(parts)}{rng.choice(parts)}")
    return names


def tokenizer_strings():
    from what_to_id.atlas_text_encoder import VERIFY_QUERIES

    extra = [
        "a photo of a bird eating a frog",
        "it's a bird's nest, isn't it? we'll see; they'd go; I'm sure; you've; they're",
        "red-winged blackbird, black-capped chickadee, well-known--ish",
        "multiple     spaces   between\twords\nand\r\nnewlines",
        "emoji \U0001f438\U0001f426 and flags \U0001f1e8\U0001f1e6",
        "numbers 123 4567 3.14 2026-10-18 1st 2nd",
        "Épilobe, Crème brûlée, Zürich, naïve café, Ñandú, Øresund, façade",
        "Cyrillic птица and Greek πτηνό",
        "café vs café (combining accent)",
        "ＡＢＣ fullwidth １２３ and “curly” ‘quotes’",
        "ligature ﬁsh ﬂower",
        "AT&amp;T &lt;b&gt; caf&eacute; &#233; &#x1F438; &copy &unknown; & alone",
        "<start_of_text> literal <end_of_text> markers",
        "tabs\tand nbsp　ideographic em-space",
        "control\x00chars\x07and\x7fdel",
        "   leading and trailing   ",
        "  ",
        "!!!???...",
        "x" * 300,
        "word " * 100,
        "Lobaria pulmonaria, Pseudacris regilla, Amanita muscaria, Quercus garryana",
        "UPPER lower MiXeD ΣΑΣ İstanbul",
    ]
    return list(dict.fromkeys(VERIFY_QUERIES + extra + taxon_names()))


@pytest.fixture(scope="module")
def merges(tmp_path_factory):
    pytest.importorskip("open_clip", reason="open_clip is not installed")
    from what_to_id.atlas_text_encoder import write_merges

    path = tmp_path_factory.mktemp("clip") / "bpe_merges.txt"
    write_merges(path)
    return path


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_js_tokenizer_ids_equal_open_clip(merges):
    open_clip = pytest.importorskip("open_clip", reason="open_clip is not installed")
    pytest.importorskip("ftfy", reason="ftfy (open_clip dependency) is not installed")
    strings = tokenizer_strings()
    assert len(strings) >= 55
    script = (ASSETS / "clip_tokenizer.js").read_text() + (
        f"\nconst texts={json.dumps(strings)};"
        f"\nconst t=ClipTokenizer.create({json.dumps(merges.read_text())});"
        "\nconsole.log(JSON.stringify(texts.map(x=>t.tokenize(x))));"
    )
    result = subprocess.run([NODE], input=script, capture_output=True, text=True, check=True)
    actual = json.loads(result.stdout)
    expected = open_clip.SimpleTokenizer()(strings, context_length=77).tolist()
    bad = [(s, a, e) for s, a, e in zip(strings, actual, expected, strict=True) if a != e]
    assert not bad, f"{len(bad)} strings differ, first: {bad[0]}"


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_js_tokenizer_rejects_incomplete_merges():
    script = (ASSETS / "clip_tokenizer.js").read_text() + (
        "\ntry{ClipTokenizer.create('#version\\na b');}catch(e){console.log(e.message);}"
    )
    result = subprocess.run([NODE], input=script, capture_output=True, text=True, check=True)
    assert "incomplete" in result.stdout


def test_quantize_embedding_rewrites_gather_to_int8_rows(tmp_path):
    np = pytest.importorskip("numpy")
    onnx = pytest.importorskip("onnx")
    ort = pytest.importorskip("onnxruntime", reason="onnxruntime is not installed")
    from onnx import TensorProto, helper, numpy_helper

    from what_to_id.atlas_text_encoder import EMBEDDING_NAME, quantize_embedding

    rng = np.random.default_rng(0)
    table = rng.normal(size=(16, 8)).astype(np.float32)
    table[3] = 0.0  # an all-zero row must not divide by zero
    table[5] *= 100.0  # per-row scales: a large row must not coarsen the others
    graph = helper.make_graph(
        [helper.make_node("Gather", [EMBEDDING_NAME, "tokens"], ["embedding"], "g")],
        "g",
        [helper.make_tensor_value_info("tokens", TensorProto.INT64, ["b", 4])],
        [helper.make_tensor_value_info("embedding", TensorProto.FLOAT, ["b", 4, 8])],
        [numpy_helper.from_array(table, name=EMBEDDING_NAME)],
    )
    path = tmp_path / "m.onnx"
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 9  # older than any onnxruntime this repo supports
    onnx.save(model, str(path))
    quantize_embedding(path)

    model = onnx.load(str(path))
    assert {i.name: i.data_type for i in model.graph.initializer}[f"{EMBEDDING_NAME}_int8"] == (
        TensorProto.INT8
    )
    ids = np.array([[0, 3, 5, 15], [1, 2, 4, 5]], dtype=np.int64)
    got = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"]).run(
        None, {"tokens": ids}
    )[0]
    want = table[ids]
    assert got.shape == want.shape
    assert np.all(got[0, 1] == 0)
    row_max = np.abs(want).max(axis=-1, keepdims=True)
    assert np.all(np.abs(got - want) <= row_max / 127.0 / 2 + 1e-6)


def test_quantize_embedding_rejects_missing_table(tmp_path):
    onnx = pytest.importorskip("onnx")
    pytest.importorskip("onnxruntime", reason="onnxruntime is not installed")
    from onnx import TensorProto, helper

    from what_to_id.atlas_text_encoder import quantize_embedding

    graph = helper.make_graph(
        [helper.make_node("Identity", ["x"], ["y"])],
        "g",
        [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1])],
        [helper.make_tensor_value_info("y", TensorProto.FLOAT, [1])],
    )
    path = tmp_path / "m.onnx"
    onnx.save(helper.make_model(graph), str(path))
    with pytest.raises(SystemExit, match="not found"):
        quantize_embedding(path)


EXPORT_DIR = os.environ.get("WHAT_TO_ID_TEXT_ENCODER_DIR")
SNAPSHOT_DIR = os.environ.get(
    "WHAT_TO_ID_BIOCLIP_SNAPSHOT", str(Path.home() / ".cache/what-to-id/bioclip-2.5")
)


@pytest.mark.skipif(
    not EXPORT_DIR, reason="set WHAT_TO_ID_TEXT_ENCODER_DIR to an exported model dir"
)
def test_exported_onnx_matches_torch_and_manifest():
    pytest.importorskip("onnxruntime", reason="onnxruntime is not installed")
    pytest.importorskip("open_clip", reason="open_clip is not installed")
    from what_to_id import atlas_text_encoder as enc

    out = Path(EXPORT_DIR)
    meta = json.loads((out / enc.META_FILE).read_text())
    assert meta["revision"] == enc.REVISION
    for name, info in meta["files"].items():
        assert enc.sha256(out / name) == info["sha256"], name
    snapshot = Path(SNAPSHOT_DIR)
    if not (snapshot / enc.WEIGHTS_FILE).exists():
        pytest.skip(f"BioCLIP snapshot not found in {snapshot}; set WHAT_TO_ID_BIOCLIP_SNAPSHOT")
    model, tokenizer = enc.load_model(snapshot)
    result = enc.parity(out / enc.ONNX_FILE, enc.text_tower(model), tokenizer)
    assert result["min_cosine"] >= enc.MIN_COSINE, result["queries"]
    assert result["retrieval_top1_agreement"] >= 0.75


def fake_export(directory, passed=True):
    from what_to_id import atlas_text_encoder as enc

    directory.mkdir()
    (directory / enc.ONNX_FILE).write_bytes(b"onnx bytes")
    (directory / enc.MERGES_FILE).write_text("#version\na b\n")
    meta = {
        "model": enc.REPO_ID,
        "revision": enc.REVISION,
        "embed_dim": 1024,
        "input": {"name": "tokens"},
        "output": {"name": "embedding"},
        "files": {
            n: {"sha256": enc.sha256(directory / n), "bytes": (directory / n).stat().st_size}
            for n in (enc.ONNX_FILE, enc.MERGES_FILE)
        },
        "parity": {"passed": passed},
    }
    (directory / enc.META_FILE).write_text(json.dumps(meta))
    return meta


def test_attach_names_hashed_files_in_the_manifest(tmp_path):
    from what_to_id import atlas_text_encoder as enc

    meta = fake_export(tmp_path / "export")
    index = tmp_path / "index"
    index.mkdir()
    (index / "manifest.json").write_text(json.dumps({"version": 1, "dims": 1024, "parts": []}))
    spec = enc.attach(tmp_path / "export", index)
    sha = meta["files"][enc.ONNX_FILE]["sha256"]
    assert spec["onnx"] == f"model/text_encoder-{sha[:12]}.onnx"
    assert spec["vocab"].startswith("model/bpe_merges-") and spec["vocab"].endswith(".txt")
    assert spec["bytes"] == len(b"onnx bytes") and spec["input_name"] == "tokens"
    assert (index / spec["onnx"]).read_bytes() == b"onnx bytes"
    manifest = json.loads((index / "manifest.json").read_text())
    assert manifest["text_encoder"] == spec and manifest["parts"] == []


def test_attach_refuses_failed_parity_tampered_files_and_wrong_dims(tmp_path):
    from what_to_id import atlas_text_encoder as enc

    index = tmp_path / "index"
    index.mkdir()
    (index / "manifest.json").write_text(json.dumps({"version": 1, "dims": 1024}))
    fake_export(tmp_path / "failed", passed=False)
    with pytest.raises(SystemExit, match="parity"):
        enc.attach(tmp_path / "failed", index)
    fake_export(tmp_path / "tampered")
    (tmp_path / "tampered" / enc.ONNX_FILE).write_bytes(b"other")
    with pytest.raises(SystemExit, match="sha256"):
        enc.attach(tmp_path / "tampered", index)
    fake_export(tmp_path / "ok")
    (index / "manifest.json").write_text(json.dumps({"version": 1, "dims": 512}))
    with pytest.raises(SystemExit, match="dims"):
        enc.attach(tmp_path / "ok", index)
    assert not (index / "model").exists()
