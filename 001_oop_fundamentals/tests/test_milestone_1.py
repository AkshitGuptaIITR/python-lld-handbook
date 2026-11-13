from decimal import Decimal
import pytest
from dataclasses import FrozenInstanceError

from milestone_1_ecommerce_core import (
    Money,
    Order,
    OrderLineItem,
    OrderStatus,
    Product,
)


class TestMoney:
    def test_creation_and_quantization(self) -> None:
        m1 = Money(Decimal("199.995"), " inr ")
        assert m1.amount == Decimal("200.00")
        assert m1.currency == "INR"
        assert str(m1) == "INR 200.00"

        m2 = Money(50, "USD")  # type: ignore[arg-type]
        assert m2.amount == Decimal("50.00")
        assert m2.currency == "USD"

    def test_rejects_float_bool_and_negative(self) -> None:
        with pytest.raises(TypeError):
            Money(19.99, "INR")  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            Money(True, "INR")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="negative"):
            Money(Decimal("-0.01"), "INR")
        with pytest.raises(ValueError):
            Money(Decimal("10"), "IN")
        with pytest.raises(ValueError):
            Money(Decimal("10"), "123")

    def test_immutability_and_slots(self) -> None:
        m = Money(Decimal("10.00"), "INR")
        assert not hasattr(m, "__dict__")
        with pytest.raises(FrozenInstanceError):
            m.amount = Decimal("20.00")  # type: ignore[misc]

    def test_arithmetic_and_currency_guard(self) -> None:
        m1 = Money(Decimal("100.50"), "INR")
        m2 = Money(Decimal("49.50"), "INR")
        usd = Money(Decimal("10.00"), "USD")

        assert m1 + m2 == Money(Decimal("150.00"), "INR")
        assert m1 - m2 == Money(Decimal("51.00"), "INR")
        assert m1 * 3 == Money(Decimal("301.50"), "INR")
        assert 2 * m2 == Money(Decimal("99.00"), "INR")
        assert m1 * Decimal("0.10") == Money(Decimal("10.05"), "INR")

        with pytest.raises(ValueError, match="negative"):
            _ = m2 - m1

        with pytest.raises(ValueError, match="Currency mismatch"):
            _ = m1 + usd

        with pytest.raises(ValueError, match="Currency mismatch"):
            _ = m1 - usd

    def test_comparisons_and_truthiness(self) -> None:
        zero = Money(Decimal("0.00"), "INR")
        ten = Money(Decimal("10.00"), "INR")
        twenty = Money(Decimal("20.00"), "INR")
        usd_ten = Money(Decimal("10.00"), "USD")

        assert bool(zero) is False
        assert bool(ten) is True
        assert ten < twenty
        assert ten <= twenty
        assert twenty > ten
        assert twenty >= ten
        assert ten != usd_ten

        with pytest.raises(ValueError, match="Currency mismatch"):
            _ = ten < usd_ten


class TestProduct:
    def test_product_lifecycle_and_stock_encapsulation(self) -> None:
        p = Product(
            "  p-101 ", " Mechanical Keyboard ", Money(Decimal("4500.00")), stock=10
        )
        assert p.product_id == "p-101"
        assert p.name == "Mechanical Keyboard"
        assert p.stock == 10
        assert not hasattr(p, "__dict__")

        p.reserve_stock(4)
        assert p.stock == 6

        p.release_stock(2)
        assert p.stock == 8

        with pytest.raises(ValueError, match="Insufficient stock"):
            p.reserve_stock(9)

        with pytest.raises(ValueError):
            p.stock = -1

        with pytest.raises(TypeError):
            p.stock = True  # type: ignore[assignment]


class TestOrderAggregate:
    @pytest.fixture
    def catalog(self) -> dict[str, Product]:
        return {
            "kb": Product("kb", "Keyboard", Money(Decimal("4000.00"), "INR"), stock=5),
            "mouse": Product(
                "mouse", "Mouse", Money(Decimal("1500.00"), "INR"), stock=10
            ),
            "usd_item": Product(
                "usd_item", "Monitor", Money(Decimal("300.00"), "USD"), stock=2
            ),
        }

    def test_add_merge_and_remove_items(self, catalog: dict[str, Product]) -> None:
        order = Order("ord-1", currency="INR")
        assert len(order) == 0
        assert order.total == Money(Decimal("0.00"), "INR")

        order.add_item(catalog["kb"], quantity=2)
        order.add_item(catalog["mouse"], quantity=1)
        order.add_item(
            catalog["kb"], quantity=1
        )  # Merges with existing line item -> qty 3

        assert len(order) == 2
        assert "kb" in order
        assert catalog["mouse"] in order
        assert "nonexistent" not in order
        assert catalog["kb"].stock == 2
        assert catalog["mouse"].stock == 9
        assert order.total == Money(Decimal("13500.00"), "INR")

        # Verify items property returns an immutable tuple
        assert isinstance(order.items, tuple)
        assert [item.product_id for item in order] == ["kb", "mouse"]

        # Remove item restores stock
        order.remove_item(catalog["kb"])
        assert len(order) == 1
        assert "kb" not in order
        assert catalog["kb"].stock == 5
        assert order.total == Money(Decimal("1500.00"), "INR")

    def test_currency_mismatch_rejected(self, catalog: dict[str, Product]) -> None:
        order = Order("ord-2", currency="INR")
        with pytest.raises(ValueError, match="currency"):
            order.add_item(catalog["usd_item"], quantity=1)

    def test_state_transitions_and_cancellation(
        self, catalog: dict[str, Product]
    ) -> None:
        order = Order("ord-3", currency="INR")

        # Cannot confirm empty order
        with pytest.raises(ValueError, match="empty"):
            order.confirm()

        order.add_item(catalog["kb"], quantity=2)
        order.confirm()
        assert order.status == OrderStatus.CONFIRMED

        # Cannot add or remove after confirmation
        with pytest.raises(RuntimeError):
            order.add_item(catalog["mouse"], quantity=1)
        with pytest.raises(RuntimeError):
            order.remove_item(catalog["kb"])

        # Cancel confirmed order -> restores stock and is idempotent
        order.cancel(catalog)
        assert order.status == OrderStatus.CANCELLED
        assert catalog["kb"].stock == 5
        assert len(order) == 0

        # Second cancel is a safe no-op
        order.cancel(catalog)
        assert catalog["kb"].stock == 5
