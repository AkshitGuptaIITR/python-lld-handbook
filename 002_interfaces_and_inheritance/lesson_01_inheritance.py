from typing import Any, Self


class PaymentGateway:
    def __init__(self, *, merchant_id: str, currency: str = "INR", **kwargs: Any):
        if not self.is_valid_merchant_id(merchant_id):
            raise ValueError("Invalid merchant_id")

        currency = currency.strip().upper()

        if len(currency) != 3 or not currency.isalpha():
            raise ValueError("Currency must be a 3-letter ISO code")

        self.merchant_id = merchant_id.strip()
        self.currency = currency
        super().__init__(**kwargs)

    @staticmethod
    def is_valid_merchant_id(merchant_id: str) -> bool:
        if (
            not merchant_id.strip().startswith("merch_")
            or not merchant_id.strip()[6:].isalnum()
        ):
            return False
        return True

    @classmethod
    def from_dsn(cls, dsn: str, **kwargs: Any) -> Self:
        values = dsn.strip().split("@")
        if len(values) != 2:
            raise ValueError("Invalid DSN format")

        return cls(merchant_id=values[0], currency=values[1], **kwargs)

    def process_payment(self, amount_minor: int) -> dict[str, Any]:
        if amount_minor <= 0:
            raise ValueError("Amount must be positive")

        return {
            "merchant_id": self.merchant_id,
            "currency": self.currency,
            "amount_minor": amount_minor,
            "trail": ["PaymentGateway"],
        }


class FeeMixin(PaymentGateway):
    def __init__(self, *, fee_bps: int = 100, **kwargs: Any):
        if fee_bps < 0:
            raise ValueError("fee_bps cannot be negative.")
        self.fee_bps = fee_bps
        super().__init__(**kwargs)

    def process_payment(self, amount_minor: int) -> dict[str, Any]:
        result = super().process_payment(amount_minor)
        fee_minor = (amount_minor * self.fee_bps) // 10_000
        result["fee_minor"] = fee_minor
        result["net_minor"] = amount_minor - fee_minor
        result["trail"].append("FeeMixin")
        return result


class AuditMixin(PaymentGateway):
    def __init__(self, **kwargs: Any):
        self.audit_log: list[str] = []
        super().__init__(**kwargs)

    def process_payment(self, amount_minor: int) -> dict[str, Any]:
        result = super().process_payment(amount_minor)
        result["trail"].append("AuditMixin")
        self.audit_log.append(
            f"{result['merchant_id']}:{amount_minor}:{result['currency']}"
        )
        return result


class RazorpayGateway(AuditMixin, FeeMixin):
    def __init__(self, *, region: str = "APAC", **kwargs):
        self.region = region
        super().__init__(**kwargs)

    def process_payment(self, amount_minor: int) -> dict[str, Any]:
        result = super().process_payment(amount_minor)
        result["region"] = self.region
        result["trail"].append("RazorpayGateway")
        return result
