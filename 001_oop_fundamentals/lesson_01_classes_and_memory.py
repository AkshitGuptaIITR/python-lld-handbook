# class Test:
#     def __new__(cls):  # This is the constructor
#         # Allocates the raw PyObject structure on the C heap and returns the memory reference.
#         pass

#     def __init__(self):  # This is the initializer
#         # Receives that freshly allocated memory reference as its first parameter
#         pass


# #! Having a mutable data type in class attribute
# class WorkerNode:
#     # ? This is mutable attribute lives in Class.__dict__
#     # ? So shared across all the objects good for singleton class but not in general
#     tasks: list[str] = (
#         []
#     )  #! Never initialize mutable data types in class attribute use init function for the same

#     def __init__(self):
#         pass


# #! Updating the immutable in init function
# class WorkerNode:
#     active_count: int = 0

#     def __init__(self) -> None:
#         # ? ❌ BUG: This expands to self.active_count = self.active_count + 1
#         # ? It reads 0 from WorkerNode.__dict__, then writes active_count = 1 into self.__dict__!
#         # ? WorkerNode.active_count remains 0 forever!
#         self.active_count += 1
#         #! Instead use
#         WorkerNode.active_count += 1  # ! Mutate class attribute


# #! ✅ IDIOMATIC HIGH-THROUGHPUT PYTHON
# class TelemetryPacket:
#     __slots__ = ("packet_id", "timestamp", "payload_bytes")

#     def __init__(self, packet_id: str, timestamp: float, payload_bytes: int) -> None:
#         self.packet_id = packet_id
#         self.timestamp = timestamp
#         self.payload_bytes = payload_bytes


class WorkerNode:
    default_timeout: int = 30
    total_active_nodes: int = 0

    def __init__(self, node_id: str, region: str):
        self.node_id = node_id
        self.region = region
        self.is_active: bool = True
        self.tasks: list[str] = []
        WorkerNode.total_active_nodes += 1

    def assign_task(self, task_id: str) -> None:
        if not self.is_active:
            raise RuntimeError("Cannot assign task to an inactive node.")

        if not task_id.strip():
            raise ValueError("task_id cannot be empty")

        self.tasks.append(task_id)

    def override_timeout(self, new_timeout: int):
        if new_timeout <= 0:
            raise ValueError("Timeout must be positive")
        self.default_timeout = new_timeout

    def decommission(self):
        if not self.is_active:
            return
        self.is_active = False
        self.tasks = []
        WorkerNode.total_active_nodes -= 1


class TelemetryPacket:
    __slots__ = ("packet_id", "timestamp", "payload_bytes")

    def __init__(self, packet_id: str, timestamp: float, payload_bytes: int):
        if payload_bytes < 0:
            raise ValueError("payload_bytes cannot be negative.")

        self.packet_id = packet_id
        self.timestamp = timestamp
        self.payload_bytes = payload_bytes
