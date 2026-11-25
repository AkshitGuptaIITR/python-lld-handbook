from dataclasses import dataclass
from typing import Protocol, Iterable


@dataclass(frozen=True, slots=True)
class OrderContext:
    order_id: str
    subtotal_paise: int
    item_count: int
    payment_method: str = "UPI"

    def __post_init__(self) -> None:
        if not self.order_id or not self.order_id.strip():
            raise ValueError("order_id cannot be empty.")

        if self.subtotal_paise < 0:
            raise ValueError("subtotal_paise cannot be negative")

        if self.item_count < 0:
            raise ValueError("item_count cannot be negative")


class DiscountStrategy(Protocol):
    def __call__(self, order: OrderContext) -> int: ...


def no_discount(order: OrderContext) -> int:
    return 0


def make_payment_method_cashback(
    *, method: str, flat_paise: int, min_subtotal_paise: int = 0
) -> DiscountStrategy:
    if not method or not method.strip():
        raise ValueError("method cannot be empty")

    if flat_paise < 0:
        raise ValueError("flat_paise cannot be negative")

    if min_subtotal_paise < 0:
        raise ValueError("min_subtotal_paise cannot be negative")

    target_method = method.strip().upper()

    def check_method(order: OrderContext) -> int:
        if (
            order.payment_method.strip().upper() == target_method
            and order.subtotal_paise >= min_subtotal_paise
        ):
            return min(flat_paise, order.subtotal_paise)
        else:
            return 0

    return check_method


@dataclass(frozen=True, slots=True)
class PercentageCapDiscount:
    discount_bps: int
    max_discount_paise: int | None = None

    def __post_init__(self) -> None:
        if not (0 <= self.discount_bps <= 10_000):
            raise ValueError("discount_bps must be between 0 and 10000")

        if self.max_discount_paise is not None and self.max_discount_paise < 0:
            raise ValueError("max_discount_paise cannot be negative")

    def __call__(self, order: OrderContext) -> int:
        discount = (order.subtotal_paise * self.discount_bps) // 10_000
        if self.max_discount_paise is not None:
            discount = min(discount, self.max_discount_paise)

        return min(discount, order.subtotal_paise)


@dataclass(frozen=True, slots=True)
class TieredBulkDiscount:
    tiers: tuple[tuple[int, int], ...]

    def __post_init__(self) -> None:
        if not self.tiers:
            raise ValueError("tiers cannot be empty")

        for min_qty, bps in self.tiers:
            if min_qty < 1:
                raise ValueError("min_item_count must be at least 1")

            if not (0 <= bps <= 10_000):
                raise ValueError("discount_bps must be between 0 and 10000")

        if len({qty for qty, _ in self.tiers}) != len(self.tiers):
            raise ValueError("Duplicate min_item_count thresholds in tiers")

        object.__setattr__(self, "tiers", tuple(sorted(self.tiers, key=lambda t: t[0])))

    def __call__(self, order: OrderContext) -> int:
        bps = 0
        for qty, dis in self.tiers:
            if order.item_count >= qty:
                bps = max(dis, bps)

        return (order.subtotal_paise * bps) // 10_000


class CheckoutPricer:
    def __init__(self, *, strategy: DiscountStrategy = no_discount) -> None:
        self._strategy = strategy

    @property
    def strategy(self) -> DiscountStrategy:
        return self._strategy

    @strategy.setter
    def strategy(self, value: DiscountStrategy) -> None:
        self._strategy = value

    @staticmethod
    def _calculate_with_strategy(
        order: OrderContext, strategy: DiscountStrategy
    ) -> int:
        discount = strategy(order)
        if discount < 0:
            raise ValueError("Strategy returned negative discount")

        effective_discount = min(discount, order.subtotal_paise)
        return order.subtotal_paise - effective_discount

    def calculate_payable(self, order: OrderContext) -> int:
        return self._calculate_with_strategy(order, self._strategy)

    def select_best_payable(
        self, order: OrderContext, candidates: Iterable[DiscountStrategy]
    ) -> tuple[int, DiscountStrategy]:
        candidate_list = list(candidates)
        if not candidate_list:
            raise ValueError("candidates cannot be empty")

        best_strategy = candidate_list[0]
        best_payable = self._calculate_with_strategy(order, best_strategy)

        for candidate in candidate_list[1:]:
            payable = self._calculate_with_strategy(order, candidate)
            if payable < best_payable:
                best_payable = payable
                best_strategy = candidate

        return best_payable, best_strategy
