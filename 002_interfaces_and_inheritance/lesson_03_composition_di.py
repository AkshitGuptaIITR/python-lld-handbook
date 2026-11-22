from typing import runtime_checkable, Protocol, Any, Self
import time


@runtime_checkable
class HttpTransport(Protocol):
    def post(
        self, url: str, payload: dict[str, Any], headers: dict[str, str]
    ) -> int: ...


@runtime_checkable
class Clock(Protocol):
    def now(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...


@runtime_checkable
class Signer(Protocol):
    def sign(self, payload: dict[str, Any], timestamp: float) -> str: ...


class SystemClock:
    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class HmacStyleSigner:
    def __init__(self, *, secret: str) -> None:
        if not secret or not secret.strip():
            raise ValueError("Secret cannot be empty")

        self._secret = secret

    def sign(self, payload: dict[str, Any], timestamp: float) -> str:
        keys = sorted(payload.keys())
        canonical = "&".join(f"{key}={payload[key]}" for key in keys)
        return f"sig:{self._secret}:{int(timestamp)}:{canonical}"


class RetryingTransport:
    def __init__(
        self,
        *,
        transport: HttpTransport,
        clock: Clock,
        max_attempts: int = 3,
        base_backoff_sec: float = 0.5,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")

        if base_backoff_sec < 0.0:
            raise ValueError("base_backoff_sec cannot be negative")

        self._transport = transport
        self._clock = clock
        self._max_attempts = max_attempts
        self._base_backoff_sec = base_backoff_sec

    def post(self, url: str, payload: dict[str, Any], headers: dict[str, str]) -> int:
        for i in range(self._max_attempts):
            try:
                status = self._transport.post(url, payload, headers)

                if status < 500:
                    return status
                else:
                    if i == self._max_attempts - 1:
                        return status
                    self._clock.sleep(self._base_backoff_sec * (2**i))

            except (TimeoutError, ConnectionError) as e:
                if i == self._max_attempts - 1:
                    raise e
                self._clock.sleep(self._base_backoff_sec * (2**i))


class WebhookDispatcher:
    def __init__(
        self, *, transport: HttpTransport, signer: Signer, clock: Clock
    ) -> None:
        self._transport = transport
        self._signer = signer
        self._clock = clock
        self._dispatched: int = 0
        self._failed: int = 0

    @property
    def stats(self) -> dict[str, int]:
        return {"dispatched": self._dispatched, "failed": self._failed}

    def dispatch(
        self, *, endpoint_url: str, event_type: str, data: dict[str, Any]
    ) -> bool:
        if not endpoint_url.startswith("https://"):
            raise ValueError("Endpoint URL must use HTTPS")

        event_type = event_type.strip()
        if not event_type:
            raise ValueError("event_type cannot be empty")

        ts = self._clock.now()

        envelope: dict[str, Any] = {"event": event_type, "timestamp": ts, "data": data}
        signature = self._signer.sign(envelope, ts)

        headers: dict[str, str] = {"X-Signature": signature, "X-Event-Type": event_type}

        status = self._transport.post(endpoint_url, envelope, headers)

        if 200 <= status < 300:
            self._dispatched += 1
            return True
        else:
            self._failed += 1
            return False

    @classmethod
    def create_production(
        cls,
        *,
        transport: HttpTransport,
        secret: str,
        max_attempts: int = 3,
        base_backoff_sec: float = 0.5,
    ) -> Self:
        clock = SystemClock()
        retrying_transport = RetryingTransport(
            transport=transport,
            clock=clock,
            max_attempts=max_attempts,
            base_backoff_sec=base_backoff_sec,
        )
        signer = HmacStyleSigner(secret=secret)

        return cls(transport=retrying_transport, signer=signer, clock=clock)
