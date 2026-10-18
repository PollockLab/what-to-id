"""The photo encoder behind `atlas_update encode`: BioCLIP 2.5 on CPU through `embed`.

`Encoder.encode(ids, urls)` takes one chunk of observations and returns the ids it embedded, their
L2-normalised float32 vectors and the (id, error) pairs that failed to download or decode. Tests
pass a fake `Encoder`; only `load_encoder` imports torch, so everything else runs without it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

DIMS = 1024


@dataclass
class Encoder:
    encode: Callable[[list[int], list[str]], tuple[list[int], np.ndarray, list[tuple[int, str]]]]
    info: dict  # {"id", "revision"}, stored with the vectors and checked against the manifest
    dims: int = DIMS


def load_encoder(work: Path, threads: int = 4, batch: int = 8) -> Encoder:
    """Download and verify the pinned BioCLIP 2.5 snapshot, then wrap `embed` for one chunk."""
    import pandas as pd
    import torch
    from huggingface_hub import snapshot_download

    from what_to_id import embed
    from what_to_id.atlas_text_encoder import REPO_ID, REVISION
    from what_to_id.manifest import sha256_file
    from what_to_id.prepare_embeddings import MODEL_HASHES

    work = Path(work)
    torch.set_num_threads(threads)
    snapshot = Path(
        snapshot_download(
            repo_id=REPO_ID,
            revision=REVISION,
            allow_patterns=list(MODEL_HASHES),
            cache_dir=work / "model-cache",
        )
    )
    if {name: sha256_file(snapshot / name) for name in MODEL_HASHES} != MODEL_HASHES:
        raise ValueError("model snapshot differs from the frozen BioCLIP 2.5 checkpoint")
    model, preprocess = embed.load_backbone("bioclip25", "cpu", model_snapshot=snapshot)
    batch_fn = embed._torch_batch_fn(model, "cpu")

    def quiet(_msg: str) -> None:
        pass

    def encode(ids, urls):
        staged = embed.stage_images(
            pd.DataFrame({"id": ids, "photo_url": urls}),
            work,
            workers=4,
            timeout=20,
            retries=2,
            log=quiet,
        )
        failed = [(int(i), str(err)) for i, err in staged.attrs.get("failed", [])]
        bad = {i for i, _ in failed}
        ok = staged[~staged["id"].isin(bad)]
        paths = ok["local_path"].tolist()
        try:
            E, kept, bad_rows = embed._embed_paths(paths, batch_fn, preprocess, batch, log=quiet)
        finally:  # the photos are not kept; the runner disk is small
            for path in paths:
                Path(path).unlink(missing_ok=True)
        ok_ids = ok["id"].tolist()
        failed += [(int(ok_ids[i]), err) for i, err in bad_rows]
        return [int(ok_ids[i]) for i in kept], E.reshape(len(kept), DIMS), failed

    return Encoder(encode, {"id": REPO_ID, "revision": REVISION}, DIMS)
