from functools import total_ordering
from types import TracebackType


@total_ordering
class SemanticVersion:
    def __init__(self, major: int, minor: int, patch: int):
        if major < 0 or minor < 0 or patch < 0:
            raise ValueError("Version numbers cannot be negative.")
        self._major = major
        self._minor = minor
        self._patch = patch

    @property
    def major(self) -> int:
        return self._major

    @property
    def minor(self) -> int:
        return self._minor

    @property
    def patch(self) -> int:
        return self._patch

    # ✅ Fix:
    def __repr__(self) -> str:
        return f"SemanticVersion(major={self._major}, minor={self._minor}, patch={self._patch})"

    def __str__(self) -> str:
        return f"v{self._major}.{self._minor}.{self._patch}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemanticVersion):
            return NotImplemented
        return (self._major, self._minor, self._patch) == (
            other.major,
            other.minor,
            other.patch,
        )

    def __lt__(self, other) -> bool:
        if not isinstance(other, SemanticVersion):
            return NotImplemented

        return (self._major, self._minor, self._patch) < (
            other.major,
            other.minor,
            other.patch,
        )

    def __hash__(self) -> int:
        return hash((self._major, self._minor, self._patch))


class TransactionalBuffer:
    def __init__(self) -> None:
        self._committed: list[str] = []
        self._staged: list[str] = []
        self._is_transaction: bool = False

    def __call__(self, item: str) -> None:
        if not self._is_transaction:
            raise RuntimeError("Cannot stage items outside of an active transaction.")

        if not item.strip():
            raise ValueError("Item cannot be empty.")

        self._staged.append(item)

    def __enter__(self) -> "TransactionBuffer":
        if self._is_transaction:
            raise RuntimeError("Nested transactions are not supported.")
        self._is_transaction = True
        self._staged = []
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ):
        self._is_transaction = False
        if exc_type is None:
            self._committed.extend(self._staged)
        self._staged.clear()

        return False

    def __len__(self) -> int:
        return len(self._committed)

    def __getitem__(self, key: int) -> str:
        return self._committed[key]

    def __repr__(self) -> str:
        return f"TransactionalBuffer(committed={self._committed!r})"
