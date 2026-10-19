"""faiss training for the static atlas index: coarse centroids, OPQ rotation, PQ and refine grid.

Everything is trained on residuals to the (float16-rounded) coarse centroid, the space the
encoder in `atlas_index_io` works in. The rotation is rounded to float16 before the PQ is
trained on it, so the codebooks match what the browser reconstructs.
"""

from __future__ import annotations

import numpy as np

from what_to_id import atlas_refine
from what_to_id.atlas_index_io import CHUNK, KSUB, NBITS, Core

OPQ_ITER = 20
OPQ_ROWS = 65536


def train(
    sample: np.ndarray, nlist: int, m: int, seed: int, opq_iter: int = OPQ_ITER
) -> tuple[Core, np.ndarray]:
    """Train on unit-norm ``sample`` rows; return the `Core` and the float16 centroids to store."""
    try:
        import faiss
    except ImportError as exc:
        raise ImportError(
            "build needs faiss; install the optional extra: pip install 'what-to-id[index]'"
        ) from exc
    d = sample.shape[1]
    sample = np.ascontiguousarray(sample)
    quantizer = faiss.IndexFlatIP(d)
    coarse = faiss.IndexIVFFlat(quantizer, d, nlist, faiss.METRIC_INNER_PRODUCT)
    coarse.cp.seed = seed
    coarse.train(sample)
    c16 = quantizer.reconstruct_n(0, nlist).astype("<f2")
    centroids = c16.astype(np.float32)
    lists = np.concatenate(
        [
            np.argmax(sample[lo : lo + CHUNK] @ centroids.T, axis=1)
            for lo in range(0, len(sample), CHUNK)
        ]
    )
    resid = sample - centroids[lists]

    opq = faiss.OPQMatrix(d, m)
    opq.niter = opq_iter
    opq.train(np.ascontiguousarray(resid[:OPQ_ROWS]))
    rot = faiss.vector_to_array(opq.A).reshape(d, d).astype("<f2").astype(np.float32)
    rotated = np.ascontiguousarray(resid @ rot.T)
    del resid

    pq = faiss.ProductQuantizer(d, m, NBITS)
    pq.cp.seed = seed
    pq.train(rotated)
    books = faiss.vector_to_array(pq.centroids).reshape(m, KSUB, d // m)
    err = rotated - pq.decode(pq.compute_codes(rotated))
    sq = atlas_refine.fit(err)
    return Core(centroids, rot, books.astype(np.float32), sq, atlas_refine.BITS), c16
