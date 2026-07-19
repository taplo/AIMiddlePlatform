import io
import logging
import os

from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)

_client: Minio | None = None
_bucket: str = "aimp-results"


def get_storage() -> Minio | None:
    global _client
    if _client is None:
        endpoint = os.getenv("S3_ENDPOINT", "")
        if not endpoint:
            logger.warning("S3_ENDPOINT 未设置，存储功能已禁用")
            return None
        access_key = os.getenv("S3_ACCESS_KEY", "minioadmin")
        secret_key = os.getenv("S3_SECRET_KEY", "minioadmin")
        secure = os.getenv("S3_SECURE", "false").lower() == "true"
        region = os.getenv("S3_REGION", "us-east-1")
        _client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure, region=region)
        _bucket = os.getenv("S3_BUCKET", "aimp-results")
        try:
            if not _client.bucket_exists(_bucket):
                _client.make_bucket(_bucket)
                logger.info("已创建 S3 存储桶 '%s'", _bucket)
        except S3Error as e:
            logger.warning("无法访问 S3 存储桶 '%s'：%s", _bucket, e)
    return _client


def put_object(key: str, data: bytes, content_type: str = "application/octet-stream") -> bool:
    client = get_storage()
    if client is None:
        return False
    try:
        client.put_object(_bucket, key, io.BytesIO(data), length=len(data), content_type=content_type)
        return True
    except Exception as e:
        logger.error("S3 对象上传失败 %s：%s", key, e)
        return False


def get_object(key: str) -> bytes | None:
    client = get_storage()
    if client is None:
        return None
    try:
        resp = client.get_object(_bucket, key)
        data = resp.read()
        resp.close()
        resp.release_conn()
        return data
    except S3Error as e:
        if e.code == "NoSuchKey":
            return None
        logger.error("S3 对象获取失败 %s：%s", key, e)
        return None


def delete_object(key: str) -> bool:
    client = get_storage()
    if client is None:
        return False
    try:
        client.remove_object(_bucket, key)
        return True
    except Exception as e:
        logger.error("S3 对象删除失败 %s：%s", key, e)
        return False


def list_objects(prefix: str = "") -> list[str]:
    client = get_storage()
    if client is None:
        return []
    try:
        objects = client.list_objects(_bucket, prefix=prefix, recursive=True)
        return [obj.object_name for obj in objects]
    except Exception as e:
        logger.error("S3 对象列表获取失败：%s", e)
        return []
