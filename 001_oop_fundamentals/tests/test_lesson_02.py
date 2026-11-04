import pytest
from lesson_02_encapsulation_properties import ComputeAccount


def test_account_initialization_and_properties() -> None:
    acc = ComputeAccount(
        tenant_id="  org-123  ",
        initial_credits=250.0,
        credit_limit=1000.0,
        api_secret="super_secret_key",
    )

    assert acc.tenant_id == "org-123"
    assert acc.credits == 250.0
    assert acc.credit_limit == 1000.0
    assert acc.remaining_capacity == 750.0
    assert acc.usage_history == ()


def test_read_only_properties_cannot_be_mutated() -> None:
    acc = ComputeAccount("org-1", 100.0, 500.0, "valid_secret")

    with pytest.raises(AttributeError):
        acc.tenant_id = "org-2"  # type: ignore[misc]

    with pytest.raises(AttributeError):
        acc.credit_limit = 2000.0  # type: ignore[misc]

    with pytest.raises(AttributeError):
        acc.remaining_capacity = 0.0  # type: ignore[misc]


def test_credits_setter_validation_in_init_and_assignment() -> None:
    # Validation triggered inside __init__
    with pytest.raises(ValueError, match="Credits cannot be negative"):
        ComputeAccount("org-1", -10.0, 500.0, "valid_secret")

    with pytest.raises(ValueError, match="Credits cannot exceed credit_limit"):
        ComputeAccount("org-1", 600.0, 500.0, "valid_secret")

    acc = ComputeAccount("org-1", 100.0, 500.0, "valid_secret")

    # Validation triggered on direct property assignment
    acc.credits = 450.0
    assert acc.credits == 450.0
    assert acc.remaining_capacity == 50.0

    with pytest.raises(ValueError, match="Credits cannot exceed credit_limit"):
        acc.credits = 500.01


def test_consume_and_defensive_usage_history() -> None:
    acc = ComputeAccount("org-1", 300.0, 500.0, "valid_secret")

    acc.consume(120.5)
    acc.consume(79.5)

    assert acc.credits == 100.0
    assert acc.remaining_capacity == 400.0
    assert acc.usage_history == (120.5, 79.5)
    assert isinstance(acc.usage_history, tuple)

    with pytest.raises(ValueError, match="Consumption amount must be positive"):
        acc.consume(0)

    with pytest.raises(ValueError, match="Insufficient credits"):
        acc.consume(150.0)


def test_private_name_mangling_and_secret_rotation() -> None:
    acc = ComputeAccount("org-1", 100.0, 500.0, "initial_secret")

    # Direct access to .__api_secret or .api_secret must fail
    assert not hasattr(acc, "api_secret")
    assert not hasattr(acc, "__api_secret")
    assert "_ComputeAccount__api_secret" in acc.__dict__

    assert acc.verify_secret("wrong") is False
    assert acc.verify_secret("initial_secret") is True

    with pytest.raises(PermissionError, match="Invalid current secret"):
        acc.rotate_secret("wrong_old", "new_valid_secret")

    with pytest.raises(ValueError, match="Secret must be at least 8 characters"):
        acc.rotate_secret("initial_secret", "short")

    acc.rotate_secret("initial_secret", "new_valid_secret")
    assert acc.verify_secret("initial_secret") is False
    assert acc.verify_secret("new_valid_secret") is True
