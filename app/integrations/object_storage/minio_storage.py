from __future__ import annotations
from io import BytesIO
from datetime import timedelta
from minio import Minio
from app.core.config import get_settings

settings = get_settings()

class MinioStorage:
    def __init__(self) -> None:
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self._ensure_bucket(settings.minio_bucket_papers)
        self._ensure_bucket(settings.minio_bucket_exports)

    def _ensure_bucket(self, bucket: str) -> None:
        if not self.client.bucket_exists(bucket):
            self.client.make_bucket(bucket)

    def put_pdf(self, object_key: str, data: bytes, content_type: str = 'application/pdf') -> str:
        self.client.put_object(settings.minio_bucket_papers, object_key, BytesIO(data), length=len(data), content_type=content_type)
        return object_key

    def get_pdf(self, object_key: str) -> bytes:
        response = self.client.get_object(settings.minio_bucket_papers, object_key)
        try:
            return response.read()
        finally:
            response.close(); response.release_conn()

    def put_export(self, object_key: str, data: bytes, content_type: str) -> str:
        self.client.put_object(settings.minio_bucket_exports, object_key, BytesIO(data), length=len(data), content_type=content_type)
        return object_key

    def presigned_pdf_url(self, object_key: str, expires_seconds: int = 3600) -> str:
        return self.client.presigned_get_object(settings.minio_bucket_papers, object_key, expires=timedelta(seconds=expires_seconds))

    def export_public_url(self, object_key: str) -> str:
        """拼接 paper-exports 桶的永久公开访问 URL。
        要求 MinIO 控制台将 paper-exports 桶设为 Public Read 策略。
        """
        scheme = 'https' if settings.minio_secure else 'http'
        return f'{scheme}://{settings.minio_endpoint}/{settings.minio_bucket_exports}/{object_key}'
