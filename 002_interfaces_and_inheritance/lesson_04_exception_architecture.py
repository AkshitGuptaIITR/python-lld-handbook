from typing import Any, Protocol, runtime_checkable
import json
from json import JSONDecodeError


class LedgerError(Exception):
    def __init__(
        self, message: str, *, error_code: str, context: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.message: str = message
        self.error_code: str = error_code
        self.context: dict[str, Any] = dict(context) if context is not None else {}

    @property
    def retryable(self) -> bool:
        return False


class AccountNotFoundError(LedgerError):
    def __init__(self, account_id: str) -> None:
        super().__init__(
            f"Account not found: {account_id}",
            error_code="ACCOUNT_NOT_FOUND",
            context={"account_id": account_id},
        )
        self.account_id: str = account_id


class InsufficientFundsError(LedgerError):
    def __init__(
        self, *, account_id: str, balance_minor: int, required_minor: int
    ) -> None:
        super().__init__(
            f"Insufficient funds in account {account_id}: balance={balance_minor}, required={required_minor}",
            error_code="INSUFFICIENT_FUNDS",
            context={
                "account_id": account_id,
                "balance_minor": balance_minor,
                "required_minor": required_minor,
            },
        )
        self.account_id: str = account_id
        self.balance_minor: int = balance_minor
        self.required_minor: int = required_minor


class InvalidPayloadError(LedgerError):
    def __init__(self, message: str, *, field: str | None = None) -> None:
        ctx: dict[str, Any] = {"field": field} if field is not None else {}
        super().__init__(message, error_code="INVALID_PAYLOAD", context=ctx)
        self.field: str | None = field


class LedgerStorageError(LedgerError):
    def __init__(self, message: str, *, operation: str, retryable: bool = True) -> None:
        super().__init__(
            message, error_code="STORAGE_FAILURE", context={"operation": operation}
        )
        self.operation: str = operation
        self._retryable: bool = retryable

    @property
    def retryable(self) -> bool:
        return self._retryable


@runtime_checkable
class RawAccountStore(Protocol):
    def fetch_raw(self, account_id: str) -> str: ...
    def save_raw(self, account_id: str, serialized: str) -> None: ...


class AccountRepository:
    def __init__(self, *, store: RawAccountStore) -> None:
        self._store = store

    def get_balance(self, account_id: str) -> int:
        try:
            raw = self._store.fetch_raw(account_id)
        except KeyError as exc:
            raise AccountNotFoundError(account_id) from exc
        except (TimeoutError, OSError) as exc:
            raise LedgerStorageError(
                f"Failed to read account {account_id}",
                operation="fetch",
                retryable=True,
            ) from exc

        try:
            data = json.loads(raw)
        except JSONDecodeError:
            raise InvalidPayloadError(
                f"Corrupt record for account {account_id}", field="balance_minor"
            ) from None

        if not isinstance(data, dict):
            raise InvalidPayloadError(
                f"Corrupt record for account {account_id}", field="balance_minor"
            ) from None

        balance = data.get("balance_minor")
        if type(balance) is not int:
            raise InvalidPayloadError(
                f"Corrupt record for account {account_id}", field="balance_minor"
            ) from None

        return balance

    def set_balance(self, account_id: str, balance_minor: int) -> None:
        if balance_minor < 0:
            raise InvalidPayloadError(
                "Balance cannot be negative", field="balance_minor"
            )

        serialized = json.dumps(
            {"account_id": account_id, "balance_minor": balance_minor}
        )

        try:
            self._store.save_raw(account_id, serialized)
        except (TimeoutError, OSError) as exc:
            raise LedgerStorageError(
                f"Failed to write account {account_id}",
                operation="save",
                retryable=True,
            ) from exc


class TransferService:
    def __init__(self, *, repo: AccountRepository):
        self._repo = repo

    def transfer(
        self, *, from_account: str, to_account: str, amount_minor: int
    ) -> tuple[int, int]:
        if amount_minor <= 0:
            raise InvalidPayloadError(
                "Transfer amount must be positive", field="amount_minor"
            )

        if from_account == to_account:
            raise InvalidPayloadError(
                "Cannot transfer to the same account", field="to_account"
            )

        src_balance = self._repo.get_balance(from_account)

        if src_balance < amount_minor:
            raise InsufficientFundsError(
                account_id=from_account,
                balance_minor=src_balance,
                required_minor=amount_minor,
            )

        dst_balance = self._repo.get_balance(to_account)

        new_src = src_balance - amount_minor
        new_dst = dst_balance + amount_minor

        self._repo.set_balance(from_account, new_src)
        self._repo.set_balance(to_account, new_dst)

        return (new_src, new_dst)
