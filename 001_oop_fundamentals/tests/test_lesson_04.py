import pytest
from dataclasses import FrozenInstanceError
from lesson_04_dataclasses_enums import (
    Environment,
    LogLevel,
    DatabaseConfig,
    DeploymentSpec,
)


class TestEnums:
    def test_environment_strenum_behavior(self) -> None:
        assert Environment.DEVELOPMENT == "development"
        assert Environment.STAGING == "staging"
        assert Environment.PRODUCTION == "production"
        assert isinstance(Environment.PRODUCTION, str)
        assert f"env={Environment.STAGING}" == "env=staging"

    def test_log_level_severity_comparison(self) -> None:
        assert LogLevel.INFO.is_at_least(LogLevel.DEBUG) is True
        assert LogLevel.INFO.is_at_least(LogLevel.INFO) is True
        assert LogLevel.INFO.is_at_least(LogLevel.WARNING) is False
        assert LogLevel.CRITICAL.is_at_least(LogLevel.ERROR) is True


class TestDatabaseConfig:
    def test_valid_creation_and_normalization(self) -> None:
        cfg = DatabaseConfig(
            host="  db.internal.local ",
            port=5432,
            username=" admin ",
            raw_password="s3cr3t_password",
            database=" orders_db ",
            options=("sslmode=require", " ", "connect_timeout=10", "sslmode=require"),
        )
        assert cfg.host == "db.internal.local"
        assert cfg.username == "admin"
        assert cfg.database == "orders_db"
        assert cfg.options == ("sslmode=require", "connect_timeout=10")
        assert (
            cfg.dsn
            == "postgresql://admin:s3cr3t_password@db.internal.local:5432/orders_db"
        )

    def test_secret_protection_and_initvar(self) -> None:
        cfg = DatabaseConfig(
            host="localhost",
            username="postgres",
            raw_password="my_super_secret_password",
            database="app",
        )
        assert not hasattr(cfg, "raw_password")
        assert "my_super_secret_password" not in repr(cfg)
        assert "postgresql://" not in repr(cfg)

    def test_immutability_and_slots(self) -> None:
        cfg = DatabaseConfig(
            host="localhost",
            username="postgres",
            raw_password="secret",
            database="app",
        )
        assert not hasattr(cfg, "__dict__")
        with pytest.raises(FrozenInstanceError):
            cfg.port = 3306  # type: ignore[misc]

    def test_equality_and_hashing_ignores_password(self) -> None:
        cfg1 = DatabaseConfig(
            host="localhost",
            username="postgres",
            raw_password="password_one",
            database="app",
            options=("sslmode=require",),
        )
        cfg2 = DatabaseConfig(
            host="localhost",
            username="postgres",
            raw_password="password_two",
            database="app",
            options=("sslmode=require",),
        )
        assert cfg1 == cfg2
        assert hash(cfg1) == hash(cfg2)
        config_set = {cfg1, cfg2}
        assert len(config_set) == 1

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"host": "   ", "username": "u", "raw_password": "p", "database": "d"},
            {"host": "h", "username": "", "raw_password": "p", "database": "d"},
            {"host": "h", "username": "u", "raw_password": "", "database": "d"},
            {"host": "h", "username": "u", "raw_password": "p", "database": "  "},
            {
                "host": "h",
                "port": 0,
                "username": "u",
                "raw_password": "p",
                "database": "d",
            },
            {
                "host": "h",
                "port": 70000,
                "username": "u",
                "raw_password": "p",
                "database": "d",
            },
        ],
    )
    def test_validation_errors(self, kwargs: dict[str, object]) -> None:
        with pytest.raises(ValueError):
            DatabaseConfig(**kwargs)  # type: ignore[arg-type]


class TestDeploymentSpec:
    @pytest.fixture
    def sample_db(self) -> DatabaseConfig:
        return DatabaseConfig(
            host="localhost", username="app", raw_password="pw", database="core"
        )

    def test_defaults_and_mutable_factory_isolation(
        self, sample_db: DatabaseConfig
    ) -> None:
        spec1 = DeploymentSpec("  Auth-Service ", Environment.DEVELOPMENT, sample_db)
        spec2 = DeploymentSpec("Payment-Service", Environment.DEVELOPMENT, sample_db)

        assert spec1.service_name == "auth-service"
        assert spec1.replicas == 1
        assert spec1.log_level == LogLevel.INFO
        assert len(spec1.deployment_id) == 32
        assert spec1.deployment_id != spec2.deployment_id
        assert not hasattr(spec1, "__dict__")

        spec1.tags.append("v1")
        assert spec2.tags == []

    def test_production_guardrails(self, sample_db: DatabaseConfig) -> None:
        # Fails with 1 replica in production
        with pytest.raises(ValueError, match="at least 2 replicas"):
            DeploymentSpec(
                service_name="api",
                environment=Environment.PRODUCTION,
                db_config=sample_db,
                replicas=1,
            )

        # Fails with DEBUG log level in production
        with pytest.raises(ValueError, match="DEBUG log level is not permitted"):
            DeploymentSpec(
                service_name="api",
                environment=Environment.PRODUCTION,
                db_config=sample_db,
                replicas=2,
                log_level=LogLevel.DEBUG,
            )

        # Succeeds when meeting production criteria
        prod_spec = DeploymentSpec(
            service_name="api",
            environment=Environment.PRODUCTION,
            db_config=sample_db,
            replicas=3,
            log_level=LogLevel.WARNING,
        )
        assert prod_spec.replicas == 3

    def test_ordering_and_equality(self, sample_db: DatabaseConfig) -> None:
        dev_b = DeploymentSpec("billing", Environment.DEVELOPMENT, sample_db)
        dev_a = DeploymentSpec("auth", Environment.DEVELOPMENT, sample_db)
        stage_a = DeploymentSpec("auth", Environment.STAGING, sample_db)
        prod_a = DeploymentSpec("auth", Environment.PRODUCTION, sample_db, replicas=2)
        prod_a_duplicate = DeploymentSpec(
            "AUTH",
            Environment.PRODUCTION,
            sample_db,
            replicas=5,
            log_level=LogLevel.ERROR,
        )

        assert prod_a == prod_a_duplicate
        sorted_specs = sorted([prod_a, dev_b, stage_a, dev_a])
        assert sorted_specs == [dev_a, dev_b, stage_a, prod_a]
