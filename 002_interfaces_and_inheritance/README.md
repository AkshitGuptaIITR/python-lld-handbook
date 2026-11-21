# Phase 2: Interfaces, Polymorphism & Error Architecture

---

## Lesson 2.1: Inheritance, `super()`, MRO & `@classmethod` vs. `@staticmethod`

**Implementation:** [`lesson_2_1_inheritance_mro/gateways.py`](lesson_2_1_inheritance_mro/gateways.py)

### Core Under-the-Hood Mechanics
* **C3 Linearization (`__mro__`):** At class creation time, CPython computes a deterministic resolution tuple (`Cls.__mro__`) guaranteeing that children precede parents, left-to-right base declaration order is preserved, and subclassing never alters ancestor ordering (monotonicity). Inconsistent graphs fail immediately at import time with `TypeError`.
* **What `super()` Actually Does:** `super()` does **not** point to a parent class—it constructs a lightweight proxy (`__thisclass__`, `__self__`) that resolves attributes starting at the **next class in `type(self).__mro__`**. This enables sibling mixins in a diamond hierarchy to cooperate without direct coupling.
* **Descriptor Binding (`@classmethod` vs. `@staticmethod`):**
  * `@classmethod` binds the first argument to the **runtime class (`cls`)** via `__get__`, making it the standard idiom for polymorphic alternate constructors (`from_dsn`) annotated with `typing.Self`.
  * `@staticmethod` returns the underlying function untouched (no `self` or `cls`), serving purely to namespace stateless utilities tied to the domain.

### Production Rules & Interview Traps
* **Cooperative Diamond `__init__`:** Always enforce keyword-only arguments (`*`) paired with `**kwargs: Any` across cooperative inheritance trees. Each class consumes its own parameters and forwards `super().__init__(**kwargs)` so the shared base runs **once** and `object.__init__()` rejects unknown keyword arguments with `TypeError`.
* **Unwinding Order:** In `RazorpayGateway -> AuditMixin -> FeeMixin -> PaymentGateway`, calling `super().process_payment()` dives down to `PaymentGateway` first and executes post-`super()` mutations in reverse MRO order (`PaymentGateway` $\rightarrow$ `FeeMixin` $\rightarrow$ `AuditMixin` $\rightarrow$ `RazorpayGateway`).
* **Complexity:** Initialization and payment processing run in **$O(D)$** time where $D$ is MRO depth ($O(1)$ for fixed hierarchies), with **$O(1)$** per-transaction auxiliary space.

### Class Diagram
```mermaid
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