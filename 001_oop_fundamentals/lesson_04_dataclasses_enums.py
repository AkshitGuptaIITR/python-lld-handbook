from enum import StrEnum, auto, Enum
from dataclasses import dataclass, field, InitVar
from uuid import uuid4


class Environment(StrEnum):
    DEVELOPMENT = auto()
    STAGING = auto()
    PRODUCTION = auto()


class LogLevel(Enum):
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50

    def is_at_least(self, minimum: "LogLevel") -> bool:
        return self.value >= minimum.value


@dataclass(frozen=True, slots=True, kw_only=True)
class DatabaseConfig:
    host: str
    port: int = 5432
    username: str
    raw_password: InitVar[str]
    database: str
    options: tuple[str, ...] = field(default_factory=tuple)
    dsn: str = field(init=False, repr=False, compare=False)

    def __post_init__(self, raw_password: str) -> None:
        clean_host = self.host.strip()
        clean_db = self.database.strip()
        clean_user = self.username.strip()

        if not clean_db or not clean_host or not clean_user or not raw_password:
            raise ValueError(
                "host, username, database, and raw_password must be non-empty."
            )

        if not (1 <= self.port <= 65535):
            raise ValueError(f"Port must be between 1 and 65535, got {self.port}.")

        clean_options = tuple(
            dict.fromkeys(opt.strip() for opt in self.options if opt.strip())
        )

        object.__setattr__(self, "host", clean_host)
        object.__setattr__(self, "username", clean_user)
        object.__setattr__(self, "database", clean_db)
        object.__setattr__(self, "options", clean_options)

        computed_dsn = f"postgresql://{clean_user}:{raw_password}@{clean_host}:{self.port}/{clean_db}"

        object.__setattr__(self, "dsn", computed_dsn)


_ENV_PRIORITY: dict[Environment, int] = {
    Environment.DEVELOPMENT: 1,
    Environment.STAGING: 2,
    Environment.PRODUCTION: 3,
}


@dataclass(slots=True, order=True)
class DeploymentSpec:
    _sort_key: tuple[int, str] = field(init=False, repr=False, compare=True)

    service_name: str = field(compare=False)
    environment: Environment = field(compare=False)
    db_config: DatabaseConfig = field(compare=False)
    replicas: int = field(default=1, compare=False)
    log_level: LogLevel = field(default=LogLevel.INFO, compare=False)
    tags: list[str] = field(default_factory=list, compare=False)
    deployment_id: str = field(default_factory=lambda: uuid4().hex, compare=False)

    def __post_init__(self) -> None:
        clean_name = self.service_name.strip().lower()
        if not clean_name:
            raise ValueError("service_name cannot be empty")
        self.service_name = clean_name

        if self.replicas < 1:
            raise ValueError("replicas must be at least 1.")

        if self.environment == Environment.PRODUCTION:
            if self.replicas < 2:
                raise ValueError("Production deployments require at least 2 replicas")
            if not self.log_level.is_at_least(LogLevel.INFO):
                raise ValueError("DEBUG log level is not permitted in production")

        self._sort_key = (_ENV_PRIORITY[self.environment], self.service_name)
