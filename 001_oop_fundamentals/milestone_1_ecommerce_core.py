from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum, auto


class OrderStatus(StrEnum):
    DRAFT = auto()
    CONFIRMED = auto()
    SHIPPED = auto()
    CANCELLED = auto()


def _validate_currency_code(currency: str) -> str:
    clean_currency = currency.strip().upper()
    if (
        len(clean_currency) != 3
        or not clean_currency.isascii()
        or not clean_currency.isalpha()
    ):
        raise ValueError(f"Invalid 3-letter currency code: {currency!r}")
    return clean_currency


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str = "INR"

    def __post_init__(self) -> None:
        if isinstance(self.amount, (float, bool)) or not isinstance(
            self.amount, (Decimal, int, str)
        ):
            raise TypeError("Amount must be a Decimal, int, or numeric string.")

        quantized_amount = Decimal(str(self.amount)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if quantized_amount < Decimal("0.00"):
            raise ValueError("Money amount cannot be negative.")

        clean_currency = _validate_currency_code(self.currency)

        object.__setattr__(self, "amount", quantized_amount)
        object.__setattr__(self, "currency", clean_currency)

    def _assert_same_currency(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise ValueError(
                f"Currency mismatch: {self.currency} vs {other.currency}"
            )

    def __add__(self, other: object) -> "Money":
        if not isinstance(other, Money):
            return NotImplemented
        self._assert_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: object) -> "Money":
        if not isinstance(other, Money):
            return NotImplemented
        self._assert_same_currency(other)
        if self.amount < other.amount:
            raise ValueError("Resulting Money cannot be negative.")
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: int | Decimal) -> "Money":
        if isinstance(factor, bool) or not isinstance(factor, (int, Decimal)):
            raise TypeError("Multiplier factor must be an int or Decimal.")
        if factor < 0:
            raise ValueError("Multiplier factor cannot be negative.")
        return Money(self.amount * factor, self.currency)

    def __rmul__(self, factor: int | Decimal) -> "Money":
        return self.__mul__(factor)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._assert_same_currency(other)
        return self.amount < other.amount

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._assert_same_currency(other)
        return self.amount <= other.amount

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._assert_same_currency(other)
        return self.amount > other.amount

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._assert_same_currency(other)
        return self.amount >= other.amount

    def __bool__(self) -> bool:
        return self.amount > Decimal("0.00")

    def __str__(self) -> str:
        return f"{self.currency} {self.amount:.2f}"


class Product:
    __slots__ = ("_product_id", "_name", "_price", "_stock")

    def __init__(
        self, product_id: str, name: str, price: Money, stock: int = 0
    ) -> None:
        clean_id = product_id.strip()
        clean_name = name.strip()

        if not clean_id or not clean_name:
            raise ValueError("product_id and name must be non-empty.")

        if not isinstance(price, Money) or not bool(price):
            raise ValueError("Price must be a positive Money instance.")

        self._product_id: str = clean_id
        self._name: str = clean_name
        self._price: Money = price
        self._stock: int = 0
        self.stock = stock  # Reuses the @stock.setter validation!

    @property
    def product_id(self) -> str:
        return self._product_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def price(self) -> Money:
        return self._price

    @property
    def stock(self) -> int:
        return self._stock

    @stock.setter
    def stock(self, value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("Stock must be an integer.")
        if value < 0:
            raise ValueError("Stock quantity cannot be negative.")
        self._stock = value

    def reserve_stock(self, quantity: int) -> None:
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("Reserve quantity must be a positive integer.")
        if quantity > self._stock:
            raise ValueError(
                f"Insufficient stock for {self._product_id}: requested {quantity}, available {self._stock}."
            )
        self._stock -= quantity

    def release_stock(self, quantity: int) -> None:
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("Release quantity must be a positive integer.")
        self._stock += quantity


@dataclass(frozen=True, slots=True)
class OrderLineItem:
    product_id: str
    product_name: str
    unit_price: Money
    quantity: int

    def __post_init__(self) -> None:
        clean_id = self.product_id.strip()
        clean_name = self.product_name.strip()
        if not clean_id or not clean_name:
            raise ValueError("product_id and product_name must be non-empty.")

        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int) or self.quantity < 1:
            raise ValueError("quantity must be an integer >= 1.")

        object.__setattr__(self, "product_id", clean_id)
        object.__setattr__(self, "product_name", clean_name)

    @property
    def subtotal(self) -> Money:
        return self.unit_price * self.quantity


class Order:
    __slots__ = ("_order_id", "_currency", "_status", "_items")

    def __init__(self, order_id: str, currency: str = "INR") -> None:
        clean_order_id = order_id.strip()
        if not clean_order_id:
            raise ValueError("order_id cannot be empty.")

        self._order_id: str = clean_order_id
        self._currency: str = _validate_currency_code(currency)
        self._status: OrderStatus = OrderStatus.DRAFT
        self._items: dict[str, OrderLineItem] = {}

    @property
    def order_id(self) -> str:
        return self._order_id

    @property
    def currency(self) -> str:
        return self._currency

    @property
    def status(self) -> OrderStatus:
        return self._status

    @property
    def items(self) -> tuple[OrderLineItem, ...]:
        return tuple(self._items.values())

    @property
    def total(self) -> Money:
        return sum(
            (item.subtotal for item in self._items.values()),
            start=Money(Decimal("0.00"), self._currency),
        )

    def _ensure_draft(self) -> None:
        if self._status != OrderStatus.DRAFT:
            raise RuntimeError(
                f"Cannot modify order in {self._status} state; must be DRAFT."
            )

    def add_item(self, product: Product, quantity: int = 1) -> None:
        self._ensure_draft()

        if product.price.currency != self._currency:
            raise ValueError(
                f"Product currency {product.price.currency} does not match order currency {self._currency}."
            )

        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
            raise ValueError("Quantity must be an integer >= 1.")

        product.reserve_stock(quantity)

        existing = self._items.get(product.product_id)
        new_quantity = existing.quantity + quantity if existing else quantity

        self._items[product.product_id] = OrderLineItem(
            product_id=product.product_id,
            product_name=product.name,
            unit_price=product.price,
            quantity=new_quantity,
        )

    def remove_item(self, product: Product) -> None:
        self._ensure_draft()

        if product.product_id not in self._items:
            raise KeyError(f"Product {product.product_id!r} not in order.")

        removed_item = self._items.pop(product.product_id)
        product.release_stock(removed_item.quantity)

    def confirm(self) -> None:
        self._ensure_draft()

        if not self._items:
            raise ValueError("Cannot confirm an empty order.")

        self._status = OrderStatus.CONFIRMED

    def cancel(self, products_by_id: dict[str, Product]) -> None:
        if self._status == OrderStatus.SHIPPED:
            raise RuntimeError("Cannot cancel a shipped order.")

        if self._status == OrderStatus.CANCELLED:
            return

        for item in self._items.values():
            products_by_id[item.product_id].release_stock(item.quantity)

        self._items.clear()
        self._status = OrderStatus.CANCELLED

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[OrderLineItem]:
        return iter(self._items.values())

    def __contains__(self, item: object) -> bool:
        if isinstance(item, str):
            return item in self._items
        if isinstance(item, Product):
            return item.product_id in self._items
        return False