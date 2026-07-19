import os
from unittest.mock import MagicMock, patch

from src.core.storage import delete_object, get_object, get_storage, list_objects, put_object


def test_get_storage_returns_none_when_not_configured():
    with patch.dict(os.environ, {}, clear=True):
        assert get_storage() is None


def test_put_object_returns_false_when_disabled():
    with patch.dict(os.environ, {}, clear=True):
        assert put_object("test.txt", b"data") is False


def test_get_object_returns_none_when_disabled():
    with patch.dict(os.environ, {}, clear=True):
        assert get_object("test.txt") is None


def test_delete_object_returns_false_when_disabled():
    with patch.dict(os.environ, {}, clear=True):
        assert delete_object("test.txt") is False


def test_list_objects_returns_empty_when_disabled():
    with patch.dict(os.environ, {}, clear=True):
        assert list_objects() == []


def test_get_storage_creates_client():
    mock_client = MagicMock()
    with patch.dict(os.environ, {"S3_ENDPOINT": "play.min.io:9000"}, clear=True):
        with patch("src.core.storage.Minio", return_value=mock_client):
            client = get_storage()
            assert client is not None
