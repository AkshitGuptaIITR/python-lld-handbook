import pytest
from lesson_03_dunder_magic_methods import SemanticVersion, TransactionalBuffer


def test_semantic_version_repr_str_and_validation() -> None:
    v = SemanticVersion(2, 10, 4)
    assert v.major == 2
    assert v.minor == 10
    assert v.patch == 4
    assert repr(v) == "SemanticVersion(major=2, minor=10, patch=4)"
    assert str(v) == "v2.10.4"

    with pytest.raises(ValueError, match="Version numbers cannot be negative"):
        SemanticVersion(1, -1, 0)


def test_semantic_version_equality_ordering_and_hashing() -> None:
    v1 = SemanticVersion(1, 2, 0)
    v1_dup = SemanticVersion(1, 2, 0)
    v2 = SemanticVersion(1, 10, 0)
    v3 = SemanticVersion(2, 0, 0)

    assert v1 == v1_dup
    assert v1 != v2
    assert (v1 == "v1.2.0") is False  # Must handle non-SemanticVersion gracefully

    # Total ordering checks
    assert v1 < v2 < v3
    assert v3 > v2
    assert v1 <= v1_dup
    assert v2 >= v1

    with pytest.raises(TypeError):
        _ = v1 < "v2.0.0"  # type: ignore[operator]

    # Hashability in sets and dicts
    version_set = {v1, v1_dup, v2}
    assert len(version_set) == 2

    deployments = {v1: "deprecated", v3: "active"}
    assert deployments[SemanticVersion(1, 2, 0)] == "deprecated"


def test_transactional_buffer_commit_and_sequence_protocol() -> None:
    buf = TransactionalBuffer()
    assert len(buf) == 0

    with buf as tx:
        assert tx is buf
        buf("event_a")
        buf("event_b")
        # Staged items are not visible in committed length until exit
        assert len(buf) == 0

    assert len(buf) == 2
    assert buf[0] == "event_a"
    assert buf[-1] == "event_b"
    assert list(buf) == ["event_a", "event_b"]
    assert repr(buf) == "TransactionalBuffer(committed=['event_a', 'event_b'])"


def test_transactional_buffer_rollback_on_exception() -> None:
    buf = TransactionalBuffer()

    with buf:
        buf("initial_event")

    assert len(buf) == 1

    # Simulate an exception mid-transaction; staged items must be rolled back
    # and the exception must NOT be swallowed
    with pytest.raises(ZeroDivisionError):
        with buf:
            buf("uncommitted_event_1")
            buf("uncommitted_event_2")
            _ = 1 / 0

    assert len(buf) == 1
    assert list(buf) == ["initial_event"]

    # Subsequent transactions should still work cleanly
    with buf:
        buf("recovered_event")

    assert list(buf) == ["initial_event", "recovered_event"]


def test_transactional_buffer_guards() -> None:
    buf = TransactionalBuffer()

    # Calling outside a 'with' block must fail
    with pytest.raises(RuntimeError, match="Cannot stage items outside of an active transaction"):
        buf("rogue_event")

    # Empty strings rejected
    with pytest.raises(ValueError, match="Item cannot be empty"):
        with buf:
            buf("   ")

    # Nested transactions rejected
    with pytest.raises(RuntimeError, match="Nested transactions are not supported"):
        with buf:
            with buf:
                buf("nested")