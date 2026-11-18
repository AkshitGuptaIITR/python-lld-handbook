import pytest
from lesson_01_inheritance import AuditMixin, FeeMixin, PaymentGateway, RazorpayGateway


class TestStaticAndClassMethods:
    @pytest.mark.parametrize(
        "merchant_id,expected",
        [
            ("merch_abc123", True),
            ("merch_A1", True),
            ("merch_", False),
            ("merch_abc_123", False),
            ("merch_abc-123", False),
            ("vendor_abc123", False),
            ("", False),
        ],
    )
    def test_is_valid_merchant_id(self, merchant_id: str, expected: bool) -> None:
        assert PaymentGateway.is_valid_merchant_id(merchant_id) is expected

    def test_from_dsn_creates_base_instance_and_normalizes_currency(self) -> None:
        gw = PaymentGateway.from_dsn("merch_ind01@inr")
        assert type(gw) is PaymentGateway
        assert gw.merchant_id == "merch_ind01"
        assert gw.currency == "INR"

    def test_from_dsn_is_polymorphic_for_subclasses(self) -> None:
        rzp = RazorpayGateway.from_dsn(
            "merch_blr99@usd",
            fee_bps=250,
            region="IN-SOUTH",
        )
        assert type(rzp) is RazorpayGateway
        assert rzp.merchant_id == "merch_blr99"
        assert rzp.currency == "USD"
        assert rzp.fee_bps == 250
        assert rzp.region == "IN-SOUTH"
        assert rzp.audit_log == []

    @pytest.mark.parametrize(
        "bad_dsn",
        [
            "merch_ind01",
            "merch_ind01@inr@extra",
            "",
        ],
    )
    def test_from_dsn_invalid_format_raises(self, bad_dsn: str) -> None:
        with pytest.raises(ValueError, match="Invalid DSN format"):
            PaymentGateway.from_dsn(bad_dsn)


class TestValidationAndInit:
    def test_invalid_merchant_id_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid merchant_id"):
            PaymentGateway(merchant_id="bad_id")

    @pytest.mark.parametrize("bad_currency", ["IN", "INRU", "123", "I$R", ""])
    def test_invalid_currency_raises(self, bad_currency: str) -> None:
        with pytest.raises(ValueError, match="Currency must be a 3-letter ISO code"):
            PaymentGateway(merchant_id="merch_valid1", currency=bad_currency)

    def test_negative_fee_bps_raises(self) -> None:
        with pytest.raises(ValueError, match="fee_bps cannot be negative"):
            RazorpayGateway(merchant_id="merch_valid1", fee_bps=-10)

    def test_unexpected_kwargs_rejected_by_object_init(self) -> None:
        with pytest.raises(TypeError):
            RazorpayGateway(merchant_id="merch_valid1", unknown_param=42)  # type: ignore[call-arg]


class TestMROAndCooperativeExecution:
    def test_mro_order_is_exact(self) -> None:
        assert RazorpayGateway.__mro__ == (
            RazorpayGateway,
            AuditMixin,
            FeeMixin,
            PaymentGateway,
            object,
        )

    def test_diamond_init_runs_base_once_and_isolates_audit_logs(self) -> None:
        gw1 = RazorpayGateway(merchant_id="merch_one1")
        gw2 = RazorpayGateway(merchant_id="merch_two2")

        gw1.process_payment(5000)
        assert len(gw1.audit_log) == 1
        assert gw2.audit_log == []

    def test_cooperative_process_payment_unwinds_in_mro_reverse_order(self) -> None:
        gw = RazorpayGateway(
            merchant_id="merch_shop1",
            currency="inr",
            fee_bps=200,  # 2%
            region="APAC",
        )
        result = gw.process_payment(10_000)

        assert result == {
            "merchant_id": "merch_shop1",
            "currency": "INR",
            "amount_minor": 10_000,
            "fee_minor": 200,
            "net_minor": 9_800,
            "region": "APAC",
            "trail": [
                "PaymentGateway",
                "FeeMixin",
                "AuditMixin",
                "RazorpayGateway",
            ],
        }
        assert gw.audit_log == ["merch_shop1:10000:INR"]

    @pytest.mark.parametrize("bad_amount", [0, -1, -5000])
    def test_non_positive_amount_raises_and_does_not_audit(
        self, bad_amount: int
    ) -> None:
        gw = RazorpayGateway(merchant_id="merch_shop1")
        with pytest.raises(ValueError, match="Amount must be positive"):
            gw.process_payment(bad_amount)
        assert gw.audit_log == []
