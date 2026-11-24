import json
import pytest
from lesson_04_exception_architecture import (
    AccountNotFoundError,
    AccountRepository,
    InsufficientFundsError,
    InvalidPayloadError,
    LedgerError,
    LedgerStorageError,
    RawAccountStore,
    TransferService,
)


class FakeRawStore:
    """In-memory raw store supporting fault injection for read/write operations."""

    def __init__(self, initial: dict[str, str] | None = None) -> None:
        self.records: dict[str, str] = dict(initial) if initial is not None else {}
        self.fail_on_fetch: Exception | None = None
        self.fail_on_save: Exception | None = None

    def fetch_raw(self, account_id: str) -> str:
        if self.fail_on_fetch is not None:
            raise self.fail_on_fetch
        return self.records[account_id]

    def save_raw(self, account_id: str, serialized: str) -> None:
        if self.fail_on_save is not None:
            raise self.fail_on_save
        self.records[account_id] = serialized


class TestExceptionHierarchyAndPayloads:
    def test_hierarchy_roots_at_exception_not_base_exception_directly(self) -> None:
        assert issubclass(LedgerError, Exception)
        assert not issubclass(LedgerError, KeyboardInterrupt)
        for sub_cls in (
            AccountNotFoundError,
            InsufficientFundsError,
            InvalidPayloadError,
            LedgerStorageError,
        ):
            assert issubclass(sub_cls, LedgerError)

    def test_super_init_populates_args_and_defensively_copies_context(self) -> None:
        raw_ctx = {"tenant": "in_blr"}
        err = LedgerError("Something broke", error_code="GENERIC", context=raw_ctx)
        raw_ctx["tenant"] = "mutated"

        assert str(err) == "Something broke"
        assert err.args == ("Something broke",)
        assert err.error_code == "GENERIC"
        assert err.context == {"tenant": "in_blr"}
        assert err.retryable is False

    def test_retryable_flag_distinguishes_transient_vs_permanent_errors(self) -> None:
        not_found = AccountNotFoundError("acc_1")
        insufficient = InsufficientFundsError(
            account_id="acc_1",
            balance_minor=100,
            required_minor=500,
        )
        transient_io = LedgerStorageError(
            "DB timeout", operation="fetch", retryable=True
        )
        permanent_io = LedgerStorageError(
            "Disk corrupt", operation="fetch", retryable=False
        )

        assert not_found.retryable is False
        assert insufficient.retryable is False
        assert transient_io.retryable is True
        assert permanent_io.retryable is False


class TestRepositoryExceptionTranslation:
    def test_store_conforms_to_protocol(self) -> None:
        assert isinstance(FakeRawStore(), RawAccountStore)

    def test_missing_account_translates_key_error_with_explicit_cause(self) -> None:
        store = FakeRawStore()
        repo = AccountRepository(store=store)

        with pytest.raises(AccountNotFoundError, match="acc_404") as exc_info:
            repo.get_balance("acc_404")

        err = exc_info.value
        assert err.account_id == "acc_404"
        assert err.error_code == "ACCOUNT_NOT_FOUND"
        assert err.context == {"account_id": "acc_404"}
        assert isinstance(err.__cause__, KeyError)
        assert err.__suppress_context__ is True

    def test_timeout_on_fetch_translates_to_retryable_storage_error_with_cause(
        self,
    ) -> None:
        store = FakeRawStore()
        store.fail_on_fetch = TimeoutError("socket read timeout")
        repo = AccountRepository(store=store)

        with pytest.raises(
            LedgerStorageError, match="Failed to read account acc_1"
        ) as exc_info:
            repo.get_balance("acc_1")

        err = exc_info.value
        assert err.operation == "fetch"
        assert err.retryable is True
        assert isinstance(err.__cause__, TimeoutError)
        assert err.__suppress_context__ is True

    def test_os_error_on_save_translates_to_retryable_storage_error_with_cause(
        self,
    ) -> None:
        store = FakeRawStore()
        store.fail_on_save = OSError("connection reset by peer")
        repo = AccountRepository(store=store)

        with pytest.raises(
            LedgerStorageError, match="Failed to write account acc_1"
        ) as exc_info:
            repo.set_balance("acc_1", 5000)

        err = exc_info.value
        assert err.operation == "save"
        assert err.retryable is True
        assert isinstance(err.__cause__, OSError)

    @pytest.mark.parametrize(
        "corrupt_json",
        [
            "{not-valid-json",
            '["a", "list", "not", "dict"]',
            '{"account_id": "acc_1"}',
            '{"account_id": "acc_1", "balance_minor": "500"}',
            '{"account_id": "acc_1", "balance_minor": true}',
        ],
    )
    def test_corrupt_record_suppresses_internal_parser_context(
        self, corrupt_json: str
    ) -> None:
        store = FakeRawStore({"acc_1": corrupt_json})
        repo = AccountRepository(store=store)

        with pytest.raises(InvalidPayloadError, match="Corrupt record") as exc_info:
            repo.get_balance("acc_1")

        err = exc_info.value
        assert err.error_code == "INVALID_PAYLOAD"
        assert err.field == "balance_minor"
        assert err.__cause__ is None
        assert err.__suppress_context__ is True

    def test_set_balance_rejects_negative_amount(self) -> None:
        store = FakeRawStore()
        repo = AccountRepository(store=store)

        with pytest.raises(InvalidPayloadError, match="negative") as exc_info:
            repo.set_balance("acc_1", -1)

        assert exc_info.value.field == "balance_minor"


class TestTransferService:
    def _seed_store(self) -> FakeRawStore:
        return FakeRawStore(
            {
                "acc_alice": json.dumps(
                    {"account_id": "acc_alice", "balance_minor": 10_000}
                ),
                "acc_bob": json.dumps(
                    {"account_id": "acc_bob", "balance_minor": 2_500}
                ),
            }
        )

    def test_successful_transfer_updates_both_accounts(self) -> None:
        store = self._seed_store()
        service = TransferService(repo=AccountRepository(store=store))

        new_src, new_dst = service.transfer(
            from_account="acc_alice",
            to_account="acc_bob",
            amount_minor=3_000,
        )

        assert (new_src, new_dst) == (7_000, 5_500)
        assert json.loads(store.records["acc_alice"])["balance_minor"] == 7_000
        assert json.loads(store.records["acc_bob"])["balance_minor"] == 5_500

    def test_insufficient_funds_raises_structured_domain_error_before_fetching_dest(
        self,
    ) -> None:
        store = FakeRawStore(
            {
                "acc_alice": json.dumps(
                    {"account_id": "acc_alice", "balance_minor": 500}
                ),
                # Note: acc_bob is intentionally absent to verify fail-fast order
            }
        )
        service = TransferService(repo=AccountRepository(store=store))

        with pytest.raises(
            InsufficientFundsError, match="Insufficient funds"
        ) as exc_info:
            service.transfer(
                from_account="acc_alice",
                to_account="acc_bob",
                amount_minor=1_200,
            )

        err = exc_info.value
        assert err.account_id == "acc_alice"
        assert err.balance_minor == 500
        assert err.required_minor == 1_200
        assert err.context == {
            "account_id": "acc_alice",
            "balance_minor": 500,
            "required_minor": 1_200,
        }

    @pytest.mark.parametrize("bad_amount", [0, -100])
    def test_non_positive_transfer_amount_rejected(self, bad_amount: int) -> None:
        service = TransferService(repo=AccountRepository(store=self._seed_store()))

        with pytest.raises(InvalidPayloadError, match="positive") as exc_info:
            service.transfer(
                from_account="acc_alice",
                to_account="acc_bob",
                amount_minor=bad_amount,
            )

        assert exc_info.value.field == "amount_minor"

    def test_self_transfer_rejected(self) -> None:
        service = TransferService(repo=AccountRepository(store=self._seed_store()))

        with pytest.raises(InvalidPayloadError, match="same account") as exc_info:
            service.transfer(
                from_account="acc_alice",
                to_account="acc_alice",
                amount_minor=100,
            )

        assert exc_info.value.field == "to_account"
