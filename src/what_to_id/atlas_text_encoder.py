"""Export the BioCLIP 2.5 text tower to a quantized ONNX model for in-browser free-text search.

The photo index holds L2-normalised float32 image vectors from the pinned snapshot, so the browser
embeds a query with the same text tower and ranks by dot product. This module builds the text tower
alone, exports ONNX, quantizes it, and measures parity against the torch fp32 tower.

    python -m what_to_id.atlas_text_encoder fetch --snapshot DIR
    python -m what_to_id.atlas_text_encoder export --snapshot DIR --out DIR
    python -m what_to_id.atlas_text_encoder verify --snapshot DIR --out DIR

Outputs in ``--out``: ``text_encoder.onnx`` (quantized), ``bpe_merges.txt`` (the merges
``clip_tokenizer.js`` consumes), ``text_encoder.json`` (hashes, sizes, revision, quantization,
parity).

Interface: input ``tokens`` int64 [batch, 77] from ``clip_tokenizer.js``; output ``embedding``
float32 [batch, 1024], L2-normalised.

Built and verified with torch 2.6.0, open_clip_torch 3.3.0, onnx 1.23.2, onnxruntime 1.31.0,
onnxscript 0.7.2 (``pip install 'what-to-id[text-encoder]'``).
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import tempfile
from importlib.util import find_spec
from pathlib import Path

REPO_ID = "imageomics/bioclip-2.5-vith14"
REVISION = "6e3d04e3d6522012c88181085c5ae666e14c45cd"
CONFIG_FILE = "open_clip_config.json"
WEIGHTS_FILE = "open_clip_model.safetensors"
CONTEXT_LENGTH = 77
INPUT_NAME = "tokens"
OUTPUT_NAME = "embedding"
ONNX_FILE = "text_encoder.onnx"
FP32_FILE = "text_encoder_fp32.onnx"
MERGES_FILE = "bpe_merges.txt"
META_FILE = "text_encoder.json"
OPSET = 17
MIN_COSINE = 0.99
# Merges open_clip keeps after its header line: 49152 - 256 - 2 + 1 lines, minus the header.
N_MERGES = 49152 - 256 - 2 + 1 - 1
EMBEDDING_NAME = "clip.token_embedding.weight"
EMBEDDING_QUANT = "int8, symmetric per-row scale (Gather, Cast, Mul)"
QUANT_MODES = ("int8", "int8-perchannel", "uint8")

# Scene and taxon phrases plus tokenizer edge cases (empty, accents, truncation, case, punctuation).
VERIFY_QUERIES = [
    "a photo of a bird eating a frog",
    "a photo of a caterpillar covered in parasitoid wasp cocoons",
    "a photo of Lobaria pulmonaria",
    "a photo of Pseudacris regilla",
    "a photo of a spider carrying an egg sac",
    "a photo of a dragonfly emerging from its larval skin",
    "a photo of Amanita muscaria",
    "a photo of a red fox in snow",
    "",
    "Épilobe",
    "a photo of Épilobe à feuilles étroites",
    "a photo of 蝶 on a flower",
    "A PHOTO OF A BALD EAGLE",
    "bald eagle, juvenile; (lateral view) - perched!",
    "it's a photo of a bird's nest",
    "  multiple   spaces\tand\ttabs  ",
    "a photo of a very long description " + "of a small green insect on a leaf " * 20,
]
# (query, expected gallery label) pairs for the cheap retrieval check.
RETRIEVAL = [
    ("a photo of a Pacific chorus frog", "a photo of Pseudacris regilla"),
    ("a photo of lungwort lichen", "a photo of Lobaria pulmonaria"),
    ("a photo of a fly agaric mushroom", "a photo of Amanita muscaria"),
    ("a photo of a bald eagle", "a photo of Haliaeetus leucocephalus"),
    ("a photo of a monarch butterfly", "a photo of Danaus plexippus"),
    ("a photo of a sea otter", "a photo of Enhydra lutris"),
    ("a photo of a western redcedar", "a photo of Thuja plicata"),
    ("a photo of a garry oak", "a photo of Quercus garryana"),
]
GALLERY = [e for _, e in RETRIEVAL] + [
    "a photo of Ursus arctos",
    "a photo of Rana catesbeiana",
    "a photo of Apis mellifera",
    "a photo of Sequoia sempervirens",
    "a photo of Turdus migratorius",
    "a photo of Cyanocitta stelleri",
    "a photo of Aquila chrysaetos",
    "a photo of Pisaster ochraceus",
]


def _require_deps():
    missing = [m for m in ("onnx", "onnxruntime", "open_clip", "torch") if find_spec(m) is None]
    if missing:
        raise SystemExit(
            f"missing {missing}: pip install 'what-to-id[text-encoder]' to export the text encoder"
        )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch(snapshot: Path) -> None:
    """Download the pinned config and weights into ``snapshot`` (kept outside the repo)."""
    from huggingface_hub import hf_hub_download

    for name in (CONFIG_FILE, WEIGHTS_FILE):
        hf_hub_download(REPO_ID, name, revision=REVISION, local_dir=snapshot)


def load_model(snapshot: Path):
    """Load the snapshot the same way ``embed.load_backbone`` does; returns (model, tokenizer)."""
    import open_clip

    config = json.loads((snapshot / CONFIG_FILE).read_text())
    with tempfile.TemporaryDirectory() as tmp:
        config_path = Path(tmp) / "what-to-id-frozen.json"
        config_path.write_text(json.dumps(config["model_cfg"]))
        open_clip.add_model_config(config_path)
        model, _, _ = open_clip.create_model_and_transforms(
            config_path.stem,
            pretrained=str(snapshot / WEIGHTS_FILE),
            pretrained_hf=False,
        )
        tokenizer = open_clip.get_tokenizer(config_path.stem)
    return model.eval(), tokenizer


def text_tower(model):
    """Module mapping int64 token ids [B, 77] to L2-normalised embeddings (image tower dropped)."""
    import torch

    class TextTower(torch.nn.Module):
        def __init__(self, clip):
            super().__init__()
            self.clip = clip

        def forward(self, tokens):
            return torch.nn.functional.normalize(self.clip.encode_text(tokens), dim=-1)

    del model.visual
    return TextTower(model).eval()


def export_fp32(tower, path: Path) -> None:
    import torch

    tokens = torch.zeros(2, CONTEXT_LENGTH, dtype=torch.int64)
    tokens[:, 0], tokens[:, 1], tokens[:, 2] = 49406, 320, 49407
    with torch.no_grad():
        torch.onnx.export(
            tower,
            (tokens,),
            str(path),
            input_names=[INPUT_NAME],
            output_names=[OUTPUT_NAME],
            dynamic_axes={INPUT_NAME: {0: "batch"}, OUTPUT_NAME: {0: "batch"}},
            opset_version=OPSET,
            dynamo=False,
        )


def quantize(src: Path, dst: Path, mode: str) -> dict:
    """Dynamic weight quantization of the MatMul layers, then the token embedding to int8 rows."""
    from onnxruntime.quantization import QuantType, quantize_dynamic

    if mode not in QUANT_MODES:
        raise SystemExit(f"unknown quantization {mode!r}; choose from {QUANT_MODES}")
    weight_type = QuantType.QUInt8 if mode == "uint8" else QuantType.QInt8
    per_channel = mode == "int8-perchannel"
    quantize_dynamic(
        str(src),
        str(dst),
        op_types_to_quantize=["MatMul"],
        weight_type=weight_type,
        per_channel=per_channel,
    )
    quantize_embedding(dst)
    return {
        "method": "onnxruntime.quantization.quantize_dynamic",
        "mode": mode,
        "weight_type": weight_type.name,
        "per_channel": per_channel,
        "op_types": ["MatMul"],
        "token_embedding": EMBEDDING_QUANT,
    }


def quantize_embedding(path: Path, name: str = EMBEDDING_NAME) -> None:
    """Rewrite ``path`` in place with the token embedding table as int8 plus a scale per row.

    quantize_dynamic skips Gather, leaving the [vocab, width] table (~200 MB) in fp32. The table
    initializer becomes int8 plus a [vocab, 1] fp32 scale, and the Gather becomes
    ``Cast(Gather(int8, ids)) * Gather(scale, ids)``, which uses only ops onnxruntime-web has.
    """
    import numpy as np
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    model = onnx.load(str(path))
    graph = model.graph
    table = next((i for i in graph.initializer if i.name == name), None)
    if table is None:
        raise SystemExit(f"initializer {name!r} not found in {path}")
    users = [n for n in graph.node if name in n.input]
    if len(users) != 1 or users[0].op_type != "Gather" or users[0].input[0] != name:
        raise SystemExit(f"{name!r} must feed exactly one Gather as its data input")
    gather = users[0]
    weights = numpy_helper.to_array(table).astype(np.float32)
    scale = np.abs(weights).max(axis=1, keepdims=True) / 127.0
    scale[scale == 0] = 1.0
    quant = np.clip(np.rint(weights / scale), -127, 127).astype(np.int8)
    graph.initializer.remove(table)
    graph.initializer.extend(
        [
            numpy_helper.from_array(quant, name=f"{name}_int8"),
            numpy_helper.from_array(scale.astype(np.float32), name=f"{name}_scale"),
        ]
    )
    out = gather.output[0]
    axis = next((a.i for a in gather.attribute if a.name == "axis"), 0)
    stem = gather.name or "token_embedding"
    nodes = [
        helper.make_node(
            "Gather", [f"{name}_int8", gather.input[1]], [f"{stem}_q"], f"{stem}_q", axis=axis
        ),
        helper.make_node(
            "Cast", [f"{stem}_q"], [f"{stem}_f"], f"{stem}_cast", to=TensorProto.FLOAT
        ),
        helper.make_node(
            "Gather", [f"{name}_scale", gather.input[1]], [f"{stem}_s"], f"{stem}_s", axis=axis
        ),
        helper.make_node("Mul", [f"{stem}_f", f"{stem}_s"], [out], f"{stem}_mul"),
    ]
    index = list(graph.node).index(gather)
    graph.node.remove(gather)
    for offset, node in enumerate(nodes):
        graph.node.insert(index + offset, node)
    onnx.save(model, str(path))


def write_merges(path: Path) -> None:
    """Write open_clip's merges file (header plus the merges it keeps) for ``clip_tokenizer.js``."""
    import open_clip

    bpe = Path(open_clip.__file__).parent / "bpe_simple_vocab_16e6.txt.gz"
    with gzip.open(bpe) as handle:
        lines = handle.read().decode("utf-8").split("\n")[: 1 + N_MERGES]
    path.write_text("\n".join(lines) + "\n")


def _normalize(rows):
    import numpy as np

    rows = np.asarray(rows, dtype=np.float64)
    return rows / np.linalg.norm(rows, axis=1, keepdims=True)


def embed_onnx(session, tokens):
    import numpy as np

    return session.run([OUTPUT_NAME], {INPUT_NAME: np.asarray(tokens, dtype=np.int64)})[0]


def parity(model_path: Path, tower, tokenizer) -> dict:
    """Compare torch fp32 against the ONNX model on the fixed queries and the retrieval check."""
    import numpy as np
    import onnxruntime as ort
    import torch

    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])

    def both(texts):
        tokens = tokenizer(texts)
        with torch.no_grad():
            ref = tower(tokens).numpy()
        return _normalize(ref), _normalize(embed_onnx(session, tokens.numpy()))

    ref, got = both(VERIFY_QUERIES)
    cosine = (ref * got).sum(axis=1)
    queries = [
        {"query": q if len(q) < 60 else q[:57] + "...", "cosine": round(float(c), 5)}
        for q, c in zip(VERIFY_QUERIES, cosine, strict=True)
    ]
    ref_g, _ = both(GALLERY)
    ref_q, got_q = both([q for q, _ in RETRIEVAL])
    torch_top = (ref_q @ ref_g.T).argmax(axis=1)
    onnx_top = (got_q @ ref_g.T).argmax(axis=1)
    expected = [GALLERY.index(e) for _, e in RETRIEVAL]
    out_norm = np.linalg.norm(embed_onnx(session, tokenizer(VERIFY_QUERIES).numpy()), axis=1)
    return {
        "min_cosine": round(float(cosine.min()), 5),
        "mean_cosine": round(float(cosine.mean()), 5),
        "gate": MIN_COSINE,
        "passed": bool(cosine.min() >= MIN_COSINE),
        "n_queries": len(VERIFY_QUERIES),
        "queries": queries,
        "retrieval_top1_agreement": float((torch_top == onnx_top).mean()),
        "retrieval_torch_correct": float((torch_top == expected).mean()),
        "retrieval_onnx_correct": float((onnx_top == expected).mean()),
        "retrieval_n": len(RETRIEVAL),
        "onnx_output_norm_range": [
            round(float(out_norm.min()), 5),
            round(float(out_norm.max()), 5),
        ],
    }


def _meta(out: Path) -> dict:
    path = out / META_FILE
    return json.loads(path.read_text()) if path.exists() else {}


def _write_meta(out: Path, meta: dict) -> None:
    (out / META_FILE).write_text(json.dumps(meta, indent=2) + "\n")


def _versions() -> dict:
    import importlib.metadata as md

    names = ["torch", "open_clip_torch", "onnx", "onnxruntime", "onnxscript"]
    return {name: md.version(name) for name in names}


def cmd_export(args) -> int:
    _require_deps()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    model, tokenizer = load_model(args.snapshot)
    tower = text_tower(model)
    fp32 = out / FP32_FILE
    export_fp32(tower, fp32)
    quant = quantize(fp32, out / ONNX_FILE, args.quant)
    write_merges(out / MERGES_FILE)
    meta = {
        "model": REPO_ID,
        "revision": REVISION,
        "context_length": CONTEXT_LENGTH,
        "embed_dim": int(tower.clip.text_projection.shape[1]),
        "input": {"name": INPUT_NAME, "dtype": "int64", "shape": ["batch", CONTEXT_LENGTH]},
        "output": {"name": OUTPUT_NAME, "dtype": "float32", "l2_normalized": True},
        "opset": OPSET,
        "quantization": quant,
        "versions": _versions(),
        "files": {
            name: {"sha256": sha256(out / name), "bytes": (out / name).stat().st_size}
            for name in (ONNX_FILE, MERGES_FILE)
        },
        "fp32_onnx_bytes": fp32.stat().st_size,
    }
    meta["parity"] = parity(out / ONNX_FILE, tower, tokenizer)
    _write_meta(out, meta)
    report(meta)
    if not args.keep_fp32:
        fp32.unlink()
    return 0 if meta["parity"]["passed"] else 1


def cmd_verify(args) -> int:
    _require_deps()
    model, tokenizer = load_model(args.snapshot)
    tower = text_tower(model)
    meta = _meta(args.out)
    meta["parity"] = parity(args.out / ONNX_FILE, tower, tokenizer)
    _write_meta(args.out, meta)
    report(meta)
    return 0 if meta["parity"]["passed"] else 1


def report(meta: dict) -> None:
    p = meta["parity"]
    for row in p["queries"]:
        print(f"  {row['cosine']:.5f}  {row['query']!r}")
    print(
        f"cosine min={p['min_cosine']} mean={p['mean_cosine']} gate>={p['gate']} "
        f"{'PASS' if p['passed'] else 'FAIL'}"
    )
    print(
        f"retrieval top-1 torch-vs-onnx agreement={p['retrieval_top1_agreement']:.2f} "
        f"(torch correct {p['retrieval_torch_correct']:.2f}, onnx correct "
        f"{p['retrieval_onnx_correct']:.2f}, n={p['retrieval_n']})"
    )
    sizes = {n: f["bytes"] for n, f in meta["files"].items()}
    print(f"sizes: fp32 onnx={meta['fp32_onnx_bytes']} files={sizes}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m what_to_id.atlas_text_encoder", description=__doc__
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name, helptext in (
        ("fetch", "download the pinned snapshot files"),
        ("export", "export and quantize the text tower"),
        ("verify", "compare torch fp32 with the exported ONNX"),
    ):
        p = sub.add_parser(name, help=helptext)
        p.add_argument(
            "--snapshot", type=Path, required=True, help="dir with the pinned snapshot files"
        )
        if name != "fetch":
            p.add_argument("--out", type=Path, required=True, help="export directory")
        if name == "export":
            p.add_argument("--quant", choices=QUANT_MODES, default="int8")
            p.add_argument("--keep-fp32", action="store_true", help="keep the unquantized ONNX")
    args = parser.parse_args(argv)
    if args.command == "fetch":
        fetch(args.snapshot)
        return 0
    return {"export": cmd_export, "verify": cmd_verify}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
