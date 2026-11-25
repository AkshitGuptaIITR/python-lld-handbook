# Phase 3: SOLID & The 5 High-Yield LLD Patterns

---

## Lesson 3.1: Strategy Pattern (Class-Based vs. First-Class `Callable` Strategies)

**Implementation:** [`lesson_3_1_strategy/pricing.py`](lesson_3_1_strategy/pricing.py)

### Core Under-the-Hood Mechanics
* **CPython `tp_call` Slot:** Executing `strategy(order)` dispatches directly to the C-level `Py_TYPE(strategy)->tp_call` pointer. Plain functions execute their bytecode frame with zero wrapper overhead, while callable class instances bind `self` and invoke `__call__`.
* **Closures (`__closure__` & `PyCellObject`):** Closure factories (`make_payment_method_cashback`) capture configuration variables inside lightweight `PyCellObject` cells without defining boilerplate classes.
* **Unified Callback `Protocol` (PEP 544):** Declaring `def __call__(self, order: OrderContext) -> int: ...` on `DiscountStrategy` allows `mypy --strict` to accept stateless functions, closures, and `@dataclass` callables interchangeably under one interface.

### Production Rules & Interview Traps
* **Exact Integer Currency Arithmetic:** Always compute amounts in integer minor units (`paise`) and rates in basis points (`bps`, where `10_000 bps = 100%`) using floor division (`//`) to avoid IEEE-754 floating-point drift.
* **Immutable Evaluation Contexts:** Model `OrderContext` as `@dataclass(frozen=True, slots=True)` so multi-strategy evaluators (`select_best_payable`) cannot mutate shared state across candidates. When normalizing fields inside a frozen dataclass `__post_init__`, use `object.__setattr__`.
* **Pricer-Level Clamping & Guardrails:** Validate non-negative discounts and clamp `effective_discount = min(discount, order.subtotal_paise)` inside `CheckoutPricer` so misconfigured strategies never yield negative payables.
* **Complexity:** Single-strategy evaluation runs in **$O(1)$ time** ($O(T)$ for `TieredBulkDiscount` with $T$ tiers) and **$O(1)$ space**; `select_best_payable` runs in **$O(K)$ time** across $K$ candidate strategies and **$O(K)$ auxiliary space**.

### Class Diagram
```mermaid
classDiagram
    class OrderContext {
        <<frozen dataclass>>
        +str order_id
        +int subtotal_paise
        +int item_count
        +str payment_method
    }

    class DiscountStrategy {
        <<Protocol>>
        +__call__(order: OrderContext) int
    }

    class no_discount {
        <<function>>
        +__call__(order: OrderContext) int
    }

    class make_payment_method_cashback {
        <<closure factory>>
        +__call__(order: OrderContext) int
    }

    class PercentageCapDiscount {
        <<frozen dataclass>>
        +int discount_bps
        +int | None max_discount_paise
        +__call__(order: OrderContext) int
    }

    class TieredBulkDiscount {
        <<frozen dataclass>>
        +tuple~tuple~int, int~, ...~ tiers
        +__call__(order: OrderContext) int
    }

    class CheckoutPricer {
        -DiscountStrategy _strategy
        +DiscountStrategy strategy
        +calculate_payable(order: OrderContext) int
        +select_best_payable(order: OrderContext, candidates: Iterable~DiscountStrategy~) tuple~int, DiscountStrategy~
    }

    DiscountStrategy <|.. no_discount : structural conformance
    DiscountStrategy <|.. make_payment_method_cashback : structural conformance
    DiscountStrategy <|.. PercentageCapDiscount : structural conformance
    DiscountStrategy <|.. TieredBulkDiscount : structural conformance
    CheckoutPricer --> DiscountStrategy : delegates pricing
    CheckoutPricer ..> OrderContext : evaluates