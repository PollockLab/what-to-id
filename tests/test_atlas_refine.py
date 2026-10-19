"""Refine codes: bit packing, the scalar grid and the stage-2 re-score."""

from __future__ import annotations

import numpy as np
import pytest

from what_to_id import atlas_refine as ar


@pytest.mark.parametrize("bits", range(1, 9))
def test_pack_unpack_roundtrip(bits):
    rng = np.random.default_rng(bits)
    levels = rng.integers(0, 1 << bits, (37, 64), dtype=np.uint8)
    packed = ar.pack(levels, bits)
    assert packed.shape == (37, ar.row_bytes(64, bits)) and packed.dtype == np.uint8
    np.testing.assert_array_equal(ar.unpack(packed, 64, bits), levels)


def test_pack_layout_is_little_endian_bits():
    levels = np.zeros((1, 8), dtype=np.uint8)
    levels[0, :3] = [5, 3, 7]  # 101, 011, 111 at bit offsets 0, 3, 6
    assert ar.pack(levels, 3)[0].tolist() == [0b11_011_101, 0b0000_0001, 0]


def test_row_bytes_and_errors():
    assert ar.row_bytes(1024, 3) == 384
    with pytest.raises(ValueError, match="not divisible by 8"):
        ar.row_bytes(60, 3)
    with pytest.raises(ValueError, match="bits must be 1..8"):
        ar.row_bytes(64, 9)
    empty = ar.pack(np.zeros((0, 64), dtype=np.uint8), 3)
    assert empty.shape == (0, 24) and ar.unpack(empty, 64, 3).shape == (0, 64)


def test_fit_quantize_reduces_error_and_handles_constant_dims():
    rng = np.random.default_rng(0)
    err = (rng.standard_normal((4000, 32)) * np.linspace(0.1, 1, 32)).astype(np.float32)
    err[:, 5] = 0.25  # no spread
    params = ar.fit(err, 3)
    assert params.shape == (2, 32) and params.dtype == np.float32 and np.all(params[1] > 0)
    levels = ar.quantize(err, params, 3)
    assert levels.max() <= 7
    back = ar.dequantize(levels, params)
    assert ((back - err) ** 2).mean() < 0.2 * (err**2).mean()
    np.testing.assert_allclose(back[:, 5], 0.25, atol=1e-6)


def test_rescore_adds_the_decoded_error_dot_query():
    rng = np.random.default_rng(1)
    err = rng.standard_normal((50, 64)).astype(np.float32) * 0.1
    params = ar.fit(err, 3)
    packed = ar.encode(err, params, 3)
    qr = rng.standard_normal(64).astype(np.float32)
    s1 = rng.standard_normal(50).astype(np.float32)
    want = s1 + ar.dequantize(ar.unpack(packed, 64, 3), params) @ qr
    np.testing.assert_allclose(ar.rescore(s1, qr, packed, params, 3), want, atol=1e-5)
    assert ar.rescore(s1[:0], qr, packed[:0], params, 3).shape == (0,)
