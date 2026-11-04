import pytest
from lesson_01_classes_and_memory import TelemetryPacket, WorkerNode


@pytest.fixture(autouse=True)
def reset_class_state() -> None:
    """Ensure class-level state is clean before every test."""
    WorkerNode.total_active_nodes = 0
    WorkerNode.default_timeout = 30


def test_worker_node_instance_isolation() -> None:
    node_a = WorkerNode(node_id="node-a", region="ap-south-1")
    node_b = WorkerNode(node_id="node-b", region="us-east-1")

    node_a.assign_task("task-101")

    assert node_a.tasks == ["task-101"]
    assert node_b.tasks == [], "Mutable list leaked across instances!"
    assert node_a.tasks is not node_b.tasks


def test_class_counter_and_idempotent_decommission() -> None:
    assert WorkerNode.total_active_nodes == 0

    n1 = WorkerNode("n1", "ap-south-1")
    n2 = WorkerNode("n2", "eu-west-1")
    assert WorkerNode.total_active_nodes == 2
    assert "total_active_nodes" not in n1.__dict__, "Counter was shadowed on instance!"

    n1.assign_task("job-1")
    n1.decommission()

    assert n1.is_active is False
    assert n1.tasks == []
    assert WorkerNode.total_active_nodes == 1

    # Calling decommission again should be idempotent
    n1.decommission()
    assert WorkerNode.total_active_nodes == 1

    n2.decommission()
    assert WorkerNode.total_active_nodes == 0


def test_inactive_node_rejects_tasks() -> None:
    node = WorkerNode("n1", "ap-south-1")
    node.decommission()

    with pytest.raises(RuntimeError, match="Cannot assign task to an inactive node"):
        node.assign_task("job-99")


def test_empty_task_id_rejected() -> None:
    node = WorkerNode("n1", "ap-south-1")
    with pytest.raises(ValueError, match="task_id cannot be empty"):
        node.assign_task("   ")


def test_timeout_lookup_chain_and_shadowing() -> None:
    n1 = WorkerNode("n1", "ap-south-1")
    n2 = WorkerNode("n2", "ap-south-1")

    # Initially, both read from WorkerNode.__dict__
    assert "default_timeout" not in n1.__dict__
    assert n1.default_timeout == 30
    assert n2.default_timeout == 30

    # Override on n1 only
    n1.override_timeout(120)
    assert "default_timeout" in n1.__dict__
    assert n1.default_timeout == 120
    assert n2.default_timeout == 30
    assert WorkerNode.default_timeout == 30

    # Updating class default affects n2, but n1 keeps its shadowed value
    WorkerNode.default_timeout = 45
    assert n2.default_timeout == 45
    assert n1.default_timeout == 120

    with pytest.raises(ValueError, match="Timeout must be positive"):
        n1.override_timeout(0)


def test_telemetry_packet_slots_enforcement() -> None:
    packet = TelemetryPacket(packet_id="pkt-1", timestamp=1700000000.5, payload_bytes=512)

    assert packet.packet_id == "pkt-1"
    assert packet.timestamp == 1700000000.5
    assert packet.payload_bytes == 512

    # Verify no __dict__ exists on the instance
    assert not hasattr(packet, "__dict__")

    # Verify dynamic attribute assignment is blocked
    with pytest.raises(AttributeError):
        packet.unexpected_attr = "leak"  # type: ignore[attr-defined]


def test_telemetry_packet_validation() -> None:
    with pytest.raises(ValueError, match="payload_bytes cannot be negative"):
        TelemetryPacket(packet_id="pkt-2", timestamp=1700000000.0, payload_bytes=-10)