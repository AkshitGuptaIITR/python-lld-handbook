class ComputeAccount:
    def __init__(
        self,
        tenant_id: str,
        initial_credits: float,
        credit_limit: float,
        api_secret: str,
    ) -> None:
        if not tenant_id.strip():
            raise ValueError("tenant_id cannot be empty.")
        if credit_limit <= 0:
            raise ValueError("credit_limit must be positive.")
        if len(api_secret) < 8:
            raise ValueError("Secret must be at least 8 characters.")
        self._tenant_id: str = tenant_id.strip() # protected
        self._credit_limit: float = float(credit_limit)
        self.__api_secret: str = api_secret
        self._usage_history: list[float] = []
        self.credits = initial_credits

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    @property
    def credit_limit(self) -> float:
        return self._credit_limit

    @property
    def credits(self) -> float:
        return self._credits

    @credits.setter
    def credits(self, value: float):
        if value < 0:
            raise ValueError("Credits cannot be negative.")
        if value > self._credit_limit:
            raise ValueError("Credits cannot exceed credit_limit.")
        self._credits = value

    @property
    def remaining_capacity(self) -> float:
        return self._credit_limit - self._credits

    @property
    def usage_history(self) -> tuple[float, ...]:
        return tuple(self._usage_history)

    def consume(self, amount: float) -> None:
        if amount <= 0:
            raise ValueError("Consumption amount must be positive.")

        if amount > self._credits:
            raise ValueError("Insufficient credits.")

        self._usage_history.append(amount)
        self.credits = self.credits - float(amount)

    def verify_secret(self, candidate: str) -> bool:
        return True if self.__api_secret == candidate else False

    def rotate_secret(self, old_secret: str, new_secret: str):
        if not self.verify_secret(old_secret):
            raise PermissionError("Invalid current secret.")
        if len(new_secret) < 8:
            raise ValueError("Secret must be at least 8 characters.")

        self.__api_secret = new_secret
