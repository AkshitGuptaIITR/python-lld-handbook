# Phase 2: Interfaces, Polymorphism & Error Architecture

---

## Lesson 2.1: Inheritance, `super()`, MRO & `@classmethod` vs. `@staticmethod`

**Implementation:** [`lesson_2_1_inheritance_mro/gateways.py`](lesson_2_1_inheritance_mro/gateways.py)

### Core Under-the-Hood Mechanics

- **C3 Linearization (`__mro__`):** At class creation time, CPython computes a deterministic resolution tuple (`Cls.__mro__`) guaranteeing that children precede parents, left-to-right base declaration order is preserved, and subclassing never alters ancestor ordering (monotonicity). Inconsistent graphs fail immediately at import time with `TypeError`.
- **What `super()` Actually Does:** `super()` does **not** point to a parent class—it constructs a lightweight proxy (`__thisclass__`, `__self__`) that resolves attributes starting at the **next class in `type(self).__mro__`**. This enables sibling mixins in a diamond hierarchy to cooperate without direct coupling.
- **Descriptor Binding (`@classmethod` vs. `@staticmethod`):**
  - `@classmethod` binds the first argument to the **runtime class (`cls`)** via `__get__`, making it the standard idiom for polymorphic alternate constructors (`from_dsn`) annotated with `typing.Self`.
  - `@staticmethod` returns the underlying function untouched (no `self` or `cls`), serving purely to namespace stateless utilities tied to the domain.

### Production Rules & Interview Traps

- **Cooperative Diamond `__init__`:** Always enforce keyword-only arguments (`*`) paired with `**kwargs: Any` across cooperative inheritance trees. Each class consumes its own parameters and forwards `super().__init__(**kwargs)` so the shared base runs **once** and `object.__init__()` rejects unknown keyword arguments with `TypeError`.
- **Unwinding Order:** In `RazorpayGateway -> AuditMixin -> FeeMixin -> PaymentGateway`, calling `super().process_payment()` dives down to `PaymentGateway` first and executes post-`super()` mutations in reverse MRO order (`PaymentGateway` $\rightarrow$ `FeeMixin` $\rightarrow$ `AuditMixin` $\rightarrow$ `RazorpayGateway`).
- **Complexity:** Initialization and payment processing run in **$O(D)$** time where $D$ is MRO depth ($O(1)$ for fixed hierarchies), with **$O(1)$** per-transaction auxiliary space.

### Class Diagram

````mermaid
classDiagram
    class PaymentGateway {
        +str merchant_id
        +str currency
        +is_valid_merchant_id(merchant_id: str)$ bool
        +from_dsn(dsn: str, **kwargs: Any)$ Self
        +process_payment(amount_minor: int) dict~str, Any~
    }

    class FeeMixin {
        +int fee_bps
        +process_payment(amount_minor: int) dict~str, Any~
    }

    class AuditMixin {
        +list~str~ audit_log
        +process_payment(amount_minor: int) dict~str, Any~
    }

    class RazorpayGateway {
        +str region
        +process_payment(amount_minor: int) dict~str, Any~
    }

    PaymentGateway <|-- FeeMixin
    PaymentGateway <|-- AuditMixin
    AuditMixin <|-- RazorpayGateway
    FeeMixin <|-- RazorpayGateway

classDiagram
    class BlobStore {
        <<Protocol>>
        +bool read_only
        +put(key: str, data: bytes) int
        +get(key: str) bytes
        +delete(key: str) bool
    }

    class InMemoryBlobStore {
        -bool _read_only
        -dict~str, bytes~ _data
        +bool read_only
        +put(key: str, data: bytes) int
        +get(key: str) bytes
        +delete(key: str) bool
    }

    class BaseManagedStore {
        <<ABC>>
        -str _namespace
        -bool _read_only
        +str namespace
        +bool read_only
        +put(key: str, data: bytes) int
        +get(key: str) bytes
        +delete(key: str) bool
        #_qualify_key(key: str) str
        #_write_raw(qualified_key: str, data: bytes)* int
        #_read_raw(qualified_key: str)* bytes
        #_delete_raw(qualified_key: str)* bool
    }

    class NamespacedMemoryStore {
        -dict~str, bytes~ _backend
        +list~str~ raw_keys
        #_write_raw(qualified_key: str, data: bytes) int
        #_read_raw(qualified_key: str) bytes
        #_delete_raw(qualified_key: str) bool
    }

    BaseManagedStore <|-- NamespacedMemoryStore : nominal inheritance
    BlobStore <|.. InMemoryBlobStore : structural conformance
    BlobStore <|.. NamespacedMemoryStore : structural conformance


## Lesson 2.4: Custom Domain Exception Hierarchies & Context Preservation

**Implementation:** [`lesson_2_4_exception_architecture/ledger.py`](lesson_2_4_exception_architecture/ledger.py)

### Core Under-the-Hood Mechanics
* **`BaseException` vs. `Exception`:** Custom domain hierarchies must root at `Exception`, never `BaseException`. Catching `BaseException` intercepts control-flow and process signals (`KeyboardInterrupt`, `SystemExit`, `GeneratorExit`), preventing clean shutdowns.
* **Exception Chaining Internals (PEP 3134 & PEP 409):**
  * **Implicit Context (`__context__`):** Raising a new exception inside an `except` block automatically attaches the active exception to `__context__`.
  * **Explicit Translation (`raise DomainError(...) from exc`):** Sets `__cause__ = exc` and `__suppress_context__ = True`. Used at repository boundaries (`AccountRepository`) to translate low-level storage exceptions (`KeyError`, `TimeoutError`, `OSError`) into domain errors while preserving the root cause for debugging.
  * **Context Suppression (`raise DomainError(...) from None`):** Sets `__cause__ = None` and `__suppress_context__ = True`. Used when translating malformed payload/parser failures (`json.JSONDecodeError`) so noisy internal parsing frames do not leak upward.
* **`BaseException.args` Contract:** Always invoke `super().__init__(message)` inside custom exception constructors so `self.args[0]` is populated for `str(exc)`, logging formatters, `pytest.raises(..., match=...)`, and `multiprocessing` pickling.

### Production Rules & Interview Traps
* **Actionable Metadata over Class Explosion:** Expose uniform properties (`error_code`, `retryable`, `context`) on the base `LedgerError` so callers and retry workers can route errors programmatically without fragile `isinstance` chains.
* **Defensive Context Copying:** Copy caller-supplied `context` dictionaries (`dict(context)`) in `__init__` so external mutations after an exception is raised cannot corrupt audit metadata.
* **The `bool` Subclasses `int` Trap:** Because `isinstance(True, int)` is `True` in Python, always validate integer JSON fields with `not isinstance(val, bool) and isinstance(val, int)`.
* **Complexity:** Account lookup, payload validation, and two-account transfers execute in **$O(1)$ average time** (for bounded record sizes) and **$O(1)$ auxiliary space**.

### Class Diagram
```mermaid
classDiagram
    class Exception {
        <<built-in>>
    }

    class LedgerError {
        +str message
        +str error_code
        +dict~str, Any~ context
        +bool retryable
    }

    class AccountNotFoundError {
        +str account_id
    }

    class InsufficientFundsError {
        +str account_id
        +int balance_minor
        +int required_minor
    }

    class InvalidPayloadError {
        +str | None field
    }

    class LedgerStorageError {
        +str operation
        -bool _retryable
        +bool retryable
    }

    class RawAccountStore {
        <<Protocol>>
        +fetch_raw(account_id: str) str
        +save_raw(account_id: str, serialized: str) None
    }

    class AccountRepository {
        -RawAccountStore _store
        +get_balance(account_id: str) int
        +set_balance(account_id: str, balance_minor: int) None
    }

    class TransferService {
        -AccountRepository _repo
        +transfer(from_account: str, to_account: str, amount_minor: int) tuple~int, int~
    }

    Exception <|-- LedgerError
    LedgerError <|-- AccountNotFoundError
    LedgerError <|-- InsufficientFundsError
    LedgerError <|-- InvalidPayloadError
    LedgerError <|-- LedgerStorageError

    AccountRepository --> RawAccountStore : translates boundary errors
    TransferService --> AccountRepository : enforces domain invariants
````
