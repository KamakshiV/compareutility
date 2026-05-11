"""Blob / local file persistence (Azure Blob or local disk for POC)."""

import uuid
from pathlib import Path

from app.config import get_settings


class StoredBlobMissingError(FileNotFoundError):
    """
    Raised when a row's storage_key has no backing bytes (common on Render with local disk:
    redeploys/restarts wipe ./data/storage while Postgres still references old uploads).
    Fix: set AZURE_STORAGE_CONNECTION_STRING (and container) for durable blob storage.
    """


class StorageBackend:
    async def save_bytes(self, data: bytes, suffix: str = "") -> str:
        raise NotImplementedError

    async def read_bytes(self, key: str) -> bytes:
        raise NotImplementedError

    def local_path(self, key: str) -> Path:
        raise NotImplementedError


class LocalStorage(StorageBackend):
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    async def save_bytes(self, data: bytes, suffix: str = "") -> str:
        key = f"{uuid.uuid4().hex}{suffix}"
        path = self.root / key
        path.write_bytes(data)
        return key

    async def read_bytes(self, key: str) -> bytes:
        path = self.root / key
        if not path.is_file():
            raise StoredBlobMissingError(
                f"Upload file not found at {path}. On Render, local STORAGE_LOCAL_PATH is ephemeral: "
                "redeploys remove files while the database still lists them. Re-upload after deploy, "
                "or configure AZURE_STORAGE_CONNECTION_STRING (+ AZURE_CONTAINER_NAME) for persistent storage."
            )
        return path.read_bytes()

    def local_path(self, key: str) -> Path:
        return self.root / key


class AzureBlobStorage(StorageBackend):
    def __init__(self, connection_string: str, container: str) -> None:
        from azure.storage.blob.aio import BlobServiceClient

        self._client = BlobServiceClient.from_connection_string(connection_string)
        self._container = container

    async def save_bytes(self, data: bytes, suffix: str = "") -> str:
        key = f"{uuid.uuid4().hex}{suffix}"
        blob = self._client.get_blob_client(container=self._container, blob=key)
        await blob.upload_blob(data, overwrite=True)
        return key

    async def read_bytes(self, key: str) -> bytes:
        blob = self._client.get_blob_client(container=self._container, blob=key)
        stream = await blob.download_blob()
        return await stream.readall()

    def local_path(self, key: str) -> Path:
        raise RuntimeError("Azure storage has no local path")


def get_storage() -> StorageBackend:
    settings = get_settings()
    if settings.azure_storage_connection_string:
        return AzureBlobStorage(settings.azure_storage_connection_string, settings.azure_container_name)
    return LocalStorage(Path(settings.storage_local_path))
