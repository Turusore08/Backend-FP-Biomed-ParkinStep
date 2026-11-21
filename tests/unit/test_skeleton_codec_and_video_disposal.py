import zlib
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from src.domain.exceptions import DomainValidationError, PayloadTooLargeError
from src.infrastructure.persistence.codecs.skeleton_codec import ZlibSkeletonCodec
from src.infrastructure.security.video_disposal import SecureTempVideoDisposer


def test_zlib_skeleton_codec_roundtrip_and_corruption_guards() -> None:
    codec = ZlibSkeletonCodec()
    timestamps = [0, 67, 133]
    frames = [
        [[float(t * 10 + j), float(t * 20 + j), 0.9 - j * 0.05] for j in range(6)]
        for t in range(3)
    ]

    blob = codec.pack(timestamps, frames)
    decoded_ts, decoded_frames = codec.unpack(blob)
    assert decoded_ts == timestamps
    assert len(decoded_frames) == 3
    assert len(decoded_frames[0]) == 6
    assert decoded_frames[1][2][2] == pytest.approx(frames[1][2][2], abs=1e-5)

    with pytest.raises(DomainValidationError):
        codec.pack([0, 67], frames)
    with pytest.raises(DomainValidationError):
        codec.unpack(b"not-zlib")
    with pytest.raises(DomainValidationError):
        codec.unpack(zlib.compress(b"BAD"))
    with pytest.raises(DomainValidationError):
        codec.unpack(zlib.compress(b"BAD1\x01\x00\x00\x00"))
    with pytest.raises(DomainValidationError):
        codec.unpack(zlib.compress(b"LB61\x05\x00\x00\x00short"))


async def test_secure_temp_video_disposer_deletes_on_success_error_and_oversize(
    tmp_path: Path,
) -> None:
    temp_dir = tmp_path / "vid_tmp"
    disposer = SecureTempVideoDisposer(str(temp_dir))

    async def _valid_stream() -> AsyncIterator[bytes]:
        yield b"ftypmp42"
        yield b"\x01\x02\x03\x04" * 16

    captured_path: Path | None = None
    async with disposer.secure_temp_video(_valid_stream(), max_bytes=4096) as vid_path:
        captured_path = vid_path
        assert vid_path.exists()
        assert vid_path.parent == temp_dir

    assert captured_path is not None
    assert not captured_path.exists()
    assert list(temp_dir.iterdir()) == []

    # Exception during inference still cleans up temp file
    with pytest.raises(RuntimeError, match="boom"):
        async with disposer.secure_temp_video(_valid_stream(), max_bytes=4096) as vid_path:
            assert vid_path.exists()
            raise RuntimeError("boom")
    assert list(temp_dir.iterdir()) == []

    # Empty stream rejected and cleaned up
    async def _empty_stream() -> AsyncIterator[bytes]:
        yield b""

    with pytest.raises(DomainValidationError):
        async with disposer.secure_temp_video(_empty_stream(), max_bytes=4096):
            pass
    assert list(temp_dir.iterdir()) == []

    # Oversize stream aborted immediately and cleaned up
    async def _huge_stream() -> AsyncIterator[bytes]:
        yield b"a" * 512
        yield b"b" * 512

    with pytest.raises(PayloadTooLargeError):
        async with disposer.secure_temp_video(_huge_stream(), max_bytes=600):
            pass
    assert list(temp_dir.iterdir()) == []
