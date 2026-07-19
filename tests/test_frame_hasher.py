import numpy as np

from src.cache.frame_hasher import FrameHasher


def test_compute_returns_hex_string() -> None:
    hasher = FrameHasher()
    fake_frame = np.random.randint(0, 256, (480, 640, 3), dtype=np.uint8).tobytes()
    result = hasher.compute(fake_frame)
    assert isinstance(result, str)
    assert len(result) == 16


def test_similar_frames_small_distance() -> None:
    hasher = FrameHasher()
    base = np.zeros((100, 100, 3), dtype=np.uint8)
    hash_a = hasher.compute(base.tobytes())
    similar = base.copy()
    similar[5, 5] = [1, 1, 1]
    hash_b = hasher.compute(similar.tobytes())
    assert hasher.hamming_distance(hash_a, hash_b) <= 4


def test_different_frames_large_distance() -> None:
    hasher = FrameHasher()
    black = np.zeros((100, 100, 3), dtype=np.uint8)
    white = np.full((100, 100, 3), 255, dtype=np.uint8)
    dist = hasher.hamming_distance(
        hasher.compute(black.tobytes()), hasher.compute(white.tobytes())
    )
    assert dist >= 20


def test_hamming_distance_identity() -> None:
    hasher = FrameHasher()
    assert hasher.hamming_distance("abcdef1234567890", "abcdef1234567890") == 0
