from dataclasses import FrozenInstanceError
import pytest
from lesson_01_strategy import (
    CheckoutPricer,
    DiscountStrategy,
    OrderContext,
    PercentageCapDiscount,
    TieredBulkDiscount,
    make_payment_method_cashback,
    no_discount,
)


class TestOrderContext:
    def test_valid_order_context_is_immutable_and_slotted(self) -> None:
        order = OrderContext(order_id="ord_101", subtotal_paise=50_000, item_count=3)
        assert order.payment_method == "UPI"
        assert not hasattr(order, "__dict__")

        with pytest.raises(FrozenInstanceError):
            order.subtotal_paise = 10_000  # type: ignore[misc]

    @pytest.mark.parametrize(
        "order_id,subtotal,items,msg",
        [
            ("", 1000, 1, "order_id"),
            ("   ", 1000, 1, "order_id"),
            ("ord_1", -1, 1, "subtotal_paise"),
            ("ord_1", 1000, -1, "item_count"),
        ],
    )
    def test_invalid_order_context_rejected(
        self, order_id: str, subtotal: int, items: int, msg: str
    ) -> None:
        with pytest.raises(ValueError, match=msg):
            OrderContext(order_id=order_id, subtotal_paise=subtotal, item_count=items)


class TestFunctionAndClosureStrategies:
    def test_no_discount_function(self) -> None:
        order = OrderContext(order_id="ord_1", subtotal_paise=25_000, item_count=2)
        assert no_discount(order) == 0

    def test_payment_method_cashback_closure_eligibility_and_clamping(self) -> None:
        upi_cashback = make_payment_method_cashback(
            method="  upi ",
            flat_paise=5_000,
            min_subtotal_paise=20_000,
        )

        eligible = OrderContext(
            order_id="ord_1", subtotal_paise=20_000, item_count=1, payment_method="upi"
        )
        below_min = OrderContext(
            order_id="ord_2", subtotal_paise=19_999, item_count=1, payment_method="UPI"
        )
        wrong_method = OrderContext(
            order_id="ord_3", subtotal_paise=50_000, item_count=2, payment_method="CARD"
        )

        assert upi_cashback(eligible) == 5_000
        assert upi_cashback(below_min) == 0
        assert upi_cashback(wrong_method) == 0

    def test_cashback_clamps_to_order_subtotal(self) -> None:
        generous = make_payment_method_cashback(method="UPI", flat_paise=10_000)
        small_order = OrderContext(order_id="ord_s", subtotal_paise=3_500, item_count=1)
        assert generous(small_order) == 3_500

    def test_invalid_cashback_params_rejected(self) -> None:
        with pytest.raises(ValueError, match="method"):
            make_payment_method_cashback(method="  ", flat_paise=100)
        with pytest.raises(ValueError, match="flat_paise"):
            make_payment_method_cashback(method="UPI", flat_paise=-1)
        with pytest.raises(ValueError, match="min_subtotal_paise"):
            make_payment_method_cashback(
                method="UPI", flat_paise=100, min_subtotal_paise=-5
            )


class TestCallableDataclassStrategies:
    def test_percentage_cap_discount(self) -> None:
        promo = PercentageCapDiscount(
            discount_bps=1_500, max_discount_paise=10_000
        )  # 15%, cap ₹100
        small = OrderContext(
            order_id="ord_1", subtotal_paise=40_000, item_count=1
        )  # 15% = 6,000
        large = OrderContext(
            order_id="ord_2", subtotal_paise=100_000, item_count=2
        )  # 15% = 15,000 -> capped at 10,000

        assert promo(small) == 6_000
        assert promo(large) == 10_000

    @pytest.mark.parametrize("bad_bps", [-1, 10_001])
    def test_percentage_invalid_bps_rejected(self, bad_bps: int) -> None:
        with pytest.raises(ValueError, match="discount_bps"):
            PercentageCapDiscount(discount_bps=bad_bps)

    def test_percentage_negative_cap_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_discount_paise"):
            PercentageCapDiscount(discount_bps=500, max_discount_paise=-10)

    def test_tiered_bulk_discount_normalizes_tiers_and_applies_highest_match(
        self,
    ) -> None:
        # Intentionally passed unsorted to verify __post_init__ normalization
        bulk = TieredBulkDiscount(tiers=((10, 2_000), (3, 500), (5, 1_200)))
        assert bulk.tiers == ((3, 500), (5, 1_200), (10, 2_000))

        order_2 = OrderContext(order_id="o1", subtotal_paise=100_000, item_count=2)
        order_3 = OrderContext(order_id="o2", subtotal_paise=100_000, item_count=3)
        order_7 = OrderContext(order_id="o3", subtotal_paise=100_000, item_count=7)
        order_12 = OrderContext(order_id="o4", subtotal_paise=100_000, item_count=12)

        assert bulk(order_2) == 0
        assert bulk(order_3) == 5_000
        assert bulk(order_7) == 12_000
        assert bulk(order_12) == 20_000

    def test_tiered_bulk_validation(self) -> None:
        with pytest.raises(ValueError, match="tiers cannot be empty"):
            TieredBulkDiscount(tiers=())

        with pytest.raises(ValueError, match="min_item_count"):
            TieredBulkDiscount(tiers=((0, 500),))

        with pytest.raises(ValueError, match="discount_bps"):
            TieredBulkDiscount(tiers=((2, 12_000),))

        with pytest.raises(ValueError, match="Duplicate"):
            TieredBulkDiscount(tiers=((3, 500), (3, 1_000)))


class TestCheckoutPricer:
    def test_default_strategy_and_runtime_swapping(self) -> None:
        order = OrderContext(order_id="ord_9", subtotal_paise=80_000, item_count=4)
        pricer = CheckoutPricer()
        assert pricer.strategy is no_discount
        assert pricer.calculate_payable(order) == 80_000

        pct = PercentageCapDiscount(discount_bps=1_000)  # 10% -> 8,000 off
        pricer.strategy = pct
        assert pricer.strategy == pct
        assert pricer.calculate_payable(order) == 72_000

    def test_pricer_guards_negative_and_excessive_custom_strategy_discounts(
        self,
    ) -> None:
        order = OrderContext(order_id="ord_9", subtotal_paise=10_000, item_count=1)

        def buggy_negative(_: OrderContext) -> int:
            return -500

        def over_discount(_: OrderContext) -> int:
            return 99_999

        pricer = CheckoutPricer(strategy=buggy_negative)
        with pytest.raises(ValueError, match="negative discount"):
            pricer.calculate_payable(order)

        pricer.strategy = over_discount
        assert pricer.calculate_payable(order) == 0

    def test_select_best_payable_picks_lowest_payable_and_breaks_ties_by_order(
        self,
    ) -> None:
        order = OrderContext(
            order_id="ord_festive",
            subtotal_paise=100_000,
            item_count=5,
            payment_method="UPI",
        )
        upi_offer = make_payment_method_cashback(
            method="UPI", flat_paise=12_000
        )  # 12,000 off
        bulk_offer = TieredBulkDiscount(tiers=((5, 1_200),))  # 12% = 12,000 off (tie!)
        pct_offer = PercentageCapDiscount(discount_bps=1_000)  # 10% = 10,000 off

        pricer = CheckoutPricer(strategy=no_discount)
        best_payable, winner = pricer.select_best_payable(
            order,
            [pct_offer, upi_offer, bulk_offer],
        )

        assert best_payable == 88_000
        assert winner is upi_offer
        # Active strategy on pricer must remain untouched
        assert pricer.strategy is no_discount

    def test_select_best_payable_empty_candidates_raises(self) -> None:
        order = OrderContext(order_id="ord_1", subtotal_paise=10_000, item_count=1)
        pricer = CheckoutPricer()
        candidates: list[DiscountStrategy] = []

        with pytest.raises(ValueError, match="candidates cannot be empty"):
            pricer.select_best_payable(order, candidates)
