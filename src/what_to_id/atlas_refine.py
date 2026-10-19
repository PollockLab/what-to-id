"""Scalar-quantised refine codes for the static atlas index: the stage-2 re-score.

Stage 1 (OPQ + PQ asymmetric distances) keeps a shortlist; stage 2 corrects each shortlisted
score with the quantised PQ reconstruction error of its row. The error e = r - decode(code) of
the rotated residual r is stored per dimension as a ``bits``-bit level of the affine grid
``lo[d] + step[d] * level``, so with the rotated query qr the refined score is
``s1 + <qr, lo> + sum_d level[d] * qr[d] * step[d]``. Levels are packed little-endian, dimension
d at bit ``d * bits``, so a row is ``dims * bits / 8`` bytes and a browser can Range-read it.
"""

from __future__ import annotations

import numpy as np

BITS = 3
FIT_ROWS = 65536
CLIP_SIGMAS = np.arange(1.2, 4.6, 0.2)


def row_bytes(dims: int, bits: int) -> int:
    if not 1 <= bits <= 8:
        raise ValueError(f"refine bits must be 1..8, got {bits}")
    if dims % 8:
        raise ValueError(f"dims {dims} not divisible by 8, needed to pack {bits}-bit refine codes")
    return dims * bits // 8


def fit(err: np.ndarray, bits: int = BITS, fit_rows: int = FIT_ROWS) -> np.ndarray:
    """Return float32 (2, dims) rows ``lo`` and ``step`` of the grid mean +- c*std per dimension.

    The clip width c is the one with the lowest squared error on the first ``fit_rows`` rows.
    """
    mu, sd = err.mean(0), err.std(0)
    top = (1 << bits) - 1
    sub = err[:fit_rows]
    best = None
    for c in CLIP_SIGMAS:
        params = _params(mu - c * sd, 2 * c * sd / top)
        mse = ((dequantize(quantize(sub, params, bits), params) - sub) ** 2).sum(1).mean()
        if best is None or mse < best[0]:
            best = (mse, params)
    return best[1]


def _params(lo, step) -> np.ndarray:
    # a constant dimension has no spread to code: step 1 keeps the division defined, level is 0
    step = np.where(np.asarray(step) > 0, step, 1.0)
    return np.stack([lo, step]).astype(np.float32)


def quantize(err: np.ndarray, params: np.ndarray, bits: int = BITS) -> np.ndarray:
    """Levels (n, dims) uint8 of ``err`` on the grid ``params``."""
    lo, step = params
    return np.clip(np.rint((err - lo) / step), 0, (1 << bits) - 1).astype(np.uint8)


def dequantize(levels: np.ndarray, params: np.ndarray) -> np.ndarray:
    lo, step = params
    return levels.astype(np.float32) * step + lo


def pack(levels: np.ndarray, bits: int = BITS) -> np.ndarray:
    """Pack (n, dims) levels into (n, dims * bits / 8) bytes."""
    row_bytes(levels.shape[1], bits)
    planes = (levels[:, :, None] >> np.arange(bits, dtype=np.uint8)) & 1
    return np.packbits(
        planes.reshape(len(levels), levels.shape[1] * bits), axis=1, bitorder="little"
    )


def unpack(packed: np.ndarray, dims: int, bits: int = BITS) -> np.ndarray:
    """Inverse of `pack`: (n, dims) uint8 levels."""
    planes = np.unpackbits(packed, axis=1, bitorder="little", count=dims * bits)
    planes = planes.reshape(len(packed), dims, bits)
    return (planes << np.arange(bits, dtype=np.uint8)).sum(2, dtype=np.uint8)


def encode(err: np.ndarray, params: np.ndarray, bits: int = BITS) -> np.ndarray:
    return pack(quantize(err, params, bits), bits)


def rescore(s1, qr: np.ndarray, packed: np.ndarray, params: np.ndarray, bits: int = BITS):
    """Refined scores of shortlisted rows from stage-1 scores ``s1`` and their packed codes."""
    lo, step = params
    levels = unpack(packed, len(qr), bits).astype(np.float32)
    return np.asarray(s1, dtype=np.float32) + np.float32(qr @ lo) + levels @ (qr * step)
