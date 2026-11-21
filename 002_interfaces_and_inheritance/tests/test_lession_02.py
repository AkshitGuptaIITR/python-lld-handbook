import pytest
from lesson_02_interfaces_protocols import (
    BaseManagedStore,
    BlobStore,
    InMemoryBlobStore,
    NamespacedMemoryStore,
    sync_blob,
)


class UnrelatedCustomStore:
    """Completely uninherited class testing pure structural Protocol compatibility."""

    def __init__(self, read_only: bool = False) -> None:
        self.read_only = read_only  # Plain attribute satisfying @property on Protocol
        self._items: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> int:
        self._items[key] = data
        return len(data)

    def get(self, key: str) -> bytes:
        return self._items[key]

    def delete(self, key: str) -> bool:
        return self._items.pop(key, None) is not None


class IncompleteStore:
    """Missing `delete` method — must fail runtime Protocol check."""

    @property
    def read_only(self) -> bool:
        return False

    def put(self, key: str, data: bytes) -> int:
        return len(data)

    def get(self, key: str) -> bytes:
        return b""


class TestNominalAndStructuralContracts:
    def test_in_memory_store_is_structural_only(self) -> None:
        assert BlobStore not in InMemoryBlobStore.__mro__
        store = InMemoryBlobStore()
        assert isinstance(store, BlobStore)

    def test_unrelated_custom_store_satisfies_protocol(self) -> None:
        custom = UnrelatedCustomStore()
        assert BlobStore not in UnrelatedCustomStore.__mro__
        assert isinstance(custom, BlobStore)

    def test_incomplete_store_fails_runtime_protocol_check(self) -> None:
        broken = IncompleteStore()
        assert not isinstance(broken, BlobStore)

    def test_base_managed_store_cannot_be_instantiated_directly(self) -> None:
        with pytest.raises(TypeError, match="abstract"):
            BaseManagedStore(namespace="prod")  # type: ignore[abstract]

    def test_partial_abc_subclass_cannot_be_instantiated(self) -> None:
        class PartialStore(BaseManagedStore):
            def _write_raw(self, qualified_key: str, data: bytes) -> int:
                return len(data)

            def _read_raw(self, qualified_key: str) -> bytes:
                return b""

        with pytest.raises(TypeError, match="abstract"):
            PartialStore(namespace="prod")  # type: ignore[abstract]

    def test_namespaced_store_is_both_nominal_abc_and_structural_protocol(self) -> None:
        store = NamespacedMemoryStore(namespace="invoices")
        assert isinstance(store, BaseManagedStore)
        assert isinstance(store, BlobStore)
        assert BlobStore not in NamespacedMemoryStore.__mro__


class TestInMemoryBlobStore:
    def test_crud_lifecycle(self) -> None:
        store = InMemoryBlobStore()
        written = store.put("report.pdf", b"%PDF-1.7")
        assert written == 8
        assert store.get("report.pdf") == b"%PDF-1.7"
        assert store.delete("report.pdf") is True
        assert store.delete("report.pdf") is False

        with pytest.raises(KeyError):
            store.get("report.pdf")

    @pytest.mark.parametrize("bad_key", ["", "   "])
    def test_empty_key_rejected(self, bad_key: str) -> None:
        store = InMemoryBlobStore()
        with pytest.raises(ValueError, match="Key cannot be empty"):
            store.put(bad_key, b"data")

    def test_read_only_blocks_mutations(self) -> None:
        store = InMemoryBlobStore(read_only=True)
        assert store.read_only is True

        with pytest.raises(PermissionError, match="read-only"):
            store.put("a.txt", b"hello")

        with pytest.raises(PermissionError, match="read-only"):
            store.delete("a.txt")


class TestNamespacedMemoryStore:
    @pytest.mark.parametrize("bad_ns", ["", "   ", "team/subteam"])
    def test_invalid_namespace_rejected(self, bad_ns: str) -> None:
        with pytest.raises(ValueError, match="Invalid namespace"):
            NamespacedMemoryStore(namespace=bad_ns)

    def test_template_qualifies_keys_and_delegates_to_hooks(self) -> None:
        store = NamespacedMemoryStore(namespace="  kyc  ")
        assert store.namespace == "kyc"

        size = store.put("pan.jpg", b"\xff\xd8\xff")
        assert size == 3
        assert store.raw_keys == ["kyc/pan.jpg"]
        assert store.get("pan.jpg") == b"\xff\xd8\xff"
        assert store.delete("pan.jpg") is True
        assert store.raw_keys == []

    def test_read_only_enforced_by_base_template(self) -> None:
        store = NamespacedMemoryStore(namespace="audit", read_only=True)
        with pytest.raises(PermissionError, match="read-only"):
            store.put("log.txt", b"entry")


class TestPolymorphicSyncBlob:
    def test_sync_across_heterogeneous_blob_stores(self) -> None:
        src = InMemoryBlobStore()
        dst = NamespacedMemoryStore(namespace="backup")
        custom = UnrelatedCustomStore()

        src.put("config.json", b'{"env":"prod"}')

        bytes_copied_1 = sync_blob(src, dst, "config.json")
        bytes_copied_2 = sync_blob(dst, custom, "config.json")

        assert bytes_copied_1 == 14
        assert bytes_copied_2 == 14
        assert dst.raw_keys == ["backup/config.json"]
        assert custom.get("config.json") == b'{"env":"prod"}'

    def test_sync_to_read_only_target_fails_before_reading_source(self) -> None:
        src = InMemoryBlobStore()  # Does not contain "missing.bin"
        dst = NamespacedMemoryStore(namespace="replica", read_only=True)

        # Because target read_only is checked first, PermissionError is raised
        # rather than KeyError from source.get("missing.bin").
        with pytest.raises(PermissionError, match="Target store is read-only"):
            sync_blob(src, dst, "missing.bin")