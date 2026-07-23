from src.api.routes.analyze import MAX_FRAME_BYTES


def test_max_frame_bytes_constant():
    assert MAX_FRAME_BYTES == 10 * 1024 * 1024


def test_frame_size_check():
    small = "A" * 100
    assert len(small) <= MAX_FRAME_BYTES

    large = "A" * (10 * 1024 * 1024 + 1)
    assert len(large) > MAX_FRAME_BYTES
