from typing import Protocol, runtime_checkable
from abc import ABC, abstractmethod


@runtime_checkable
class BlobStore(Protocol):
    @property
    def read_only(self) -> bool: ...

    def put(self, key: str, data: bytes) -> int: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> bool: ...


class InMemoryBlobStore:
    def __init__(self, read_only: bool = False):
        self._read_only: bool = read_only
        self._data: dict[str, bytes] = {}

    @property
    def read_only(self) -> bool:
        return self._read_only

    def put(self, key: str, data: bytes) -> int:
        if self._read_only:
            raise PermissionError("Store is read-only")

        if not key or not key.strip():
            raise ValueError("Key cannot be empty")

        self._data[key] = data
        return len(data)

    def get(self, key: str) -> bytes:
        if key not in self._data:
            raise KeyError(f"Blob not found: {key}")

        return self._data[key]

    def delete(self, key: str) -> bool:
        if self._read_only:
            raise PermissionError("Store is read-only")

        if key in self._data:
            del self._data[key]
            return True

        return False


class BaseManagedStore(ABC):
    def __init__(self, *, namespace: str, read_only: bool = False):
        namespace = namespace.strip()

        if not namespace or "/" in namespace:
            raise ValueError("Invalid namespace")

        self._namespace: str = namespace
        self._read_only: bool = read_only

    @property
    def namespace(self) -> str:
        return self._namespace

    @property
    def read_only(self) -> bool:
        return self._read_only

    def _qualify_key(self, key: str) -> str:
        key = key.strip()
        if not key:
            raise ValueError("Key cannot be empty")

        return f"{self.namespace}/{key}"

    @abstractmethod
    def _write_raw(self, qualified_key: str, data: bytes) -> int: ...

    @abstractmethod
    def _read_raw(self, qualified_key: str) -> bytes: ...

    @abstractmethod
    def _delete_raw(self, qualified_key: str) -> bool: ...

    def put(self, key: str, data: bytes) -> int:
        if self._read_only:
            raise PermissionError("Store is read-only")
        qualified_key = self._qualify_key(key)
        return self._write_raw(qualified_key, data)

    def get(self, key: str) -> bytes:
        qualified_key = self._qualify_key(key)
        return self._read_raw(qualified_key)

    def delete(self, key: str) -> bool:
        if self._read_only:
            raise PermissionError("Store is read-only")

        qualified_key = self._qualify_key(key)

        return self._delete_raw(qualified_key)


class NamespacedMemoryStore(BaseManagedStore):
    def __init__(self, *, namespace: str, read_only: bool = False) -> None:
        super().__init__(namespace=namespace, read_only=read_only)

        self._backend: dict[str, bytes] = {}

    @property
    def raw_keys(self) -> list[str]:
        return list(self._backend.keys())

    def _write_raw(self, qualified_key: str, data: bytes) -> int:
        if self._read_only:
            raise PermissionError("Store is read-only")

        self._backend[qualified_key] = data
        return len(data)

    def _read_raw(self, qualified_key: str) -> bytes:
        if qualified_key not in self._backend:
            raise KeyError(f"Blob not found: {qualified_key}")

        return self._backend[qualified_key]

    def _delete_raw(self, qualified_key):
        if self._read_only:
            raise PermissionError("Store is read-only")

        if qualified_key in self._backend:
            self._backend.pop(qualified_key)
            return True

        return False


def sync_blob(source: BlobStore, target: BlobStore, key: str) -> int:
    if target.read_only:
        raise PermissionError("Target store is read-only")

    payload = source.get(key)

    target.put(key, payload)

    return len(payload)
