from typing import Any
import pytest
from lesson_03_composition_di import (
    Clock,
    HmacStyleSigner,
    HttpTransport,
    RetryingTransport,
    Signer,
    SystemClock,
    WebhookDispatcher,
)


class FakeClock:
    """Deterministic clock test double — zero real sleeping."""

    def __init__(self, current_time: float = 1_700_000_000.0) -> None:
        self.current_time = current_time
        self.sleep_calls: list[float] = []

    def now(self) -> float:
        return self.current_time

    def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        self.current_time += seconds


class FakeTransport:
    """Scriptable transport test double recording all outbound calls."""

    def __init__(self, outcomes: list[int | Exception]) -> None:
        self._outcomes = list(outcomes)
        self.requests: list[tuple[str, dict[str, Any], dict[str, str]]] = []

    def post(self, url: str, payload: dict[str, Any], headers: dict[str, str]) -> int:
        self.requests.append((url, payload, headers))
        if not self._outcomes:
            return 200
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class TestStructuralConformance:
    def test_implementations_satisfy_protocols_without_inheritance(self) -> None:
        clock = FakeClock()
        sys_clock = SystemClock()
        signer = HmacStyleSigner(secret="topsecret")
        raw_transport = FakeTransport([200])
        retrying = RetryingTransport(transport=raw_transport, clock=clock)

        assert isinstance(clock, Clock)
        assert isinstance(sys_clock, Clock)
        assert isinstance(signer, Signer)
        assert isinstance(raw_transport, HttpTransport)
        assert isinstance(retrying, HttpTransport)
        assert HttpTransport not in RetryingTransport.__mro__


class TestHmacStyleSigner:
    def test_canonical_key_ordering_and_signature_format(self) -> None:
        signer = HmacStyleSigner(secret="whsec_123")
        sig = signer.sign({"z": 1, "a": "hello", "m": True}, timestamp=1700000050.9)
        assert sig == "sig:whsec_123:1700000050:a=hello&m=True&z=1"

    def test_empty_payload_signature(self) -> None:
        signer = HmacStyleSigner(secret="whsec_123")
        assert signer.sign({}, timestamp=100.0) == "sig:whsec_123:100:"

    @pytest.mark.parametrize("bad_secret", ["", "   "])
    def test_empty_secret_rejected(self, bad_secret: str) -> None:
        with pytest.raises(ValueError, match="Secret cannot be empty"):
            HmacStyleSigner(secret=bad_secret)


class TestRetryingTransport:
    def test_succeeds_on_first_attempt_without_sleeping(self) -> None:
        clock = FakeClock()
        inner = FakeTransport([201])
        transport = RetryingTransport(transport=inner, clock=clock, max_attempts=3)

        status = transport.post("https://example.com/hook", {"a": 1}, {})
        assert status == 201
        assert len(inner.requests) == 1
        assert clock.sleep_calls == []

    @pytest.mark.parametrize("client_status", [400, 401, 404, 422])
    def test_does_not_retry_non_retryable_4xx_errors(self, client_status: int) -> None:
        clock = FakeClock()
        inner = FakeTransport([client_status, 200])
        transport = RetryingTransport(transport=inner, clock=clock, max_attempts=3)

        status = transport.post("https://example.com/hook", {"a": 1}, {})
        assert status == client_status
        assert len(inner.requests) == 1
        assert clock.sleep_calls == []

    def test_retries_5xx_with_exponential_backoff_until_success(self) -> None:
        clock = FakeClock()
        inner = FakeTransport([502, 503, 200])
        transport = RetryingTransport(
            transport=inner,
            clock=clock,
            max_attempts=4,
            base_backoff_sec=0.5,
        )

        status = transport.post("https://example.com/hook", {"a": 1}, {})
        assert status == 200
        assert len(inner.requests) == 3
        assert clock.sleep_calls == [0.5, 1.0]

    def test_returns_last_5xx_when_attempts_exhausted(self) -> None:
        clock = FakeClock()
        inner = FakeTransport([500, 502, 504])
        transport = RetryingTransport(
            transport=inner,
            clock=clock,
            max_attempts=3,
            base_backoff_sec=1.0,
        )

        status = transport.post("https://example.com/hook", {"a": 1}, {})
        assert status == 504
        assert len(inner.requests) == 3
        assert clock.sleep_calls == [1.0, 2.0]

    def test_retries_transient_network_exceptions_and_reraises_on_exhaustion(
        self,
    ) -> None:
        clock = FakeClock()
        inner = FakeTransport(
            [TimeoutError("read timed out"), ConnectionError("reset")]
        )
        transport = RetryingTransport(
            transport=inner,
            clock=clock,
            max_attempts=2,
            base_backoff_sec=0.25,
        )

        with pytest.raises(ConnectionError, match="reset"):
            transport.post("https://example.com/hook", {"a": 1}, {})

        assert len(inner.requests) == 2
        assert clock.sleep_calls == [0.25]

    def test_invalid_retry_config_rejected(self) -> None:
        clock = FakeClock()
        inner = FakeTransport([])

        with pytest.raises(ValueError, match="max_attempts"):
            RetryingTransport(transport=inner, clock=clock, max_attempts=0)

        with pytest.raises(ValueError, match="base_backoff_sec"):
            RetryingTransport(transport=inner, clock=clock, base_backoff_sec=-0.1)


class TestWebhookDispatcher:
    def test_dispatch_builds_signed_envelope_and_updates_stats(self) -> None:
        clock = FakeClock(current_time=1_700_000_000.0)
        inner = FakeTransport([503, 200, 400])
        retrying = RetryingTransport(
            transport=inner,
            clock=clock,
            max_attempts=3,
            base_backoff_sec=0.5,
        )
        signer = HmacStyleSigner(secret="prod_secret")
        dispatcher = WebhookDispatcher(transport=retrying, signer=signer, clock=clock)

        ok1 = dispatcher.dispatch(
            endpoint_url="https://api.client.io/webhooks",
            event_type="  invoice.paid  ",
            data={"invoice_id": "inv_99"},
        )
        ok2 = dispatcher.dispatch(
            endpoint_url="https://api.client.io/webhooks",
            event_type="invoice.failed",
            data={"invoice_id": "inv_100"},
        )

        assert ok1 is True
        assert ok2 is False
        assert dispatcher.stats == {"dispatched": 1, "failed": 1}
        assert clock.sleep_calls == [0.5]

        # Inspect the successful second outbound call
        url, envelope, headers = inner.requests[1]
        assert url == "https://api.client.io/webhooks"
        assert envelope == {
            "event": "invoice.paid",
            "timestamp": 1_700_000_000.0,
            "data": {"invoice_id": "inv_99"},
        }
        assert headers["X-Event-Type"] == "invoice.paid"
        assert headers["X-Signature"].startswith("sig:prod_secret:1700000000:")

    def test_rejects_insecure_url_or_empty_event_type(self) -> None:
        clock = FakeClock()
        dispatcher = WebhookDispatcher(
            transport=FakeTransport([]),
            signer=HmacStyleSigner(secret="sec"),
            clock=clock,
        )

        with pytest.raises(ValueError, match="HTTPS"):
            dispatcher.dispatch(
                endpoint_url="http://insecure.example.com/hook",
                event_type="order.created",
                data={},
            )

        with pytest.raises(ValueError, match="event_type"):
            dispatcher.dispatch(
                endpoint_url="https://secure.example.com/hook",
                event_type="   ",
                data={},
            )

    def test_create_production_composition_root_wires_dependencies(self) -> None:
        raw_transport = FakeTransport([200])
        dispatcher = WebhookDispatcher.create_production(
            transport=raw_transport,
            secret="root_secret",
            max_attempts=2,
            base_backoff_sec=0.0,
        )

        assert isinstance(dispatcher, WebhookDispatcher)
        assert (
            dispatcher.dispatch(
                endpoint_url="https://hooks.partner.com/events",
                event_type="user.verified",
                data={"user_id": 42},
            )
            is True
        )
        assert dispatcher.stats == {"dispatched": 1, "failed": 0}
