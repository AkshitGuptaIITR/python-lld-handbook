from __future__ import annotations

from dataclasses import dataclass
from typing import (
    Any,
    Protocol,
    runtime_checkable,
    Sequence,
    ClassVar,
    Callable,
    TypeVar,
)
from abc import ABC, abstractmethod
import json

ExporterT = TypeVar("ExporterT", bound="BaseExporter")


@dataclass(frozen=True, slots=True)
class ReportRow:
    record_id: str
    metric: str
    value: float

    def __post_init__(self) -> None:
        if not self.record_id or not self.record_id.strip():
            raise ValueError("record_id cannot be empty")

        if not self.metric or not self.metric.strip():
            raise ValueError("metric cannot be empty")


@runtime_checkable
class ReportExporter(Protocol):
    @property
    def format_name(self) -> str: ...

    def export(self, rows: Sequence[ReportRow]) -> str: ...


class BaseExporter(ABC):
    _registry: ClassVar[dict[str, type[BaseExporter]]] = {}

    @classmethod
    def register(cls, format_name: str) -> Callable[[type[ExporterT]], type[ExporterT]]:
        normalized = format_name.strip().lower()
        if not normalized:
            raise ValueError("format_name cannot be empty")

        def decorator(subclass: type[ExporterT]) -> type[ExporterT]:
            if normalized in cls._registry:
                raise ValueError(f"Format already registered: {normalized}")
            cls._registry[normalized] = subclass
            return subclass

        return decorator

    @classmethod
    def create(cls, format_name: str, **kwargs: Any) -> BaseExporter:
        normalized = format_name.strip().lower()
        exporter_cls = cls._registry.get(normalized)
        if exporter_cls is None:
            raise ValueError(f"Unsupported export format: {format_name}")
        return exporter_cls(**kwargs)

    @classmethod
    def available_formats(cls) -> tuple[str, ...]:
        return tuple(sorted(cls._registry.keys()))

    @property
    @abstractmethod
    def format_name(self) -> str: ...

    @abstractmethod
    def export(self, rows: Sequence[ReportRow]) -> str: ...


@BaseExporter.register("json")
class JsonExporter(BaseExporter):
    def __init__(self, *, indent: int | None = None) -> None:
        if indent is not None and indent < 0:
            raise ValueError("indent cannot be negative")

        self._indent = indent

    @property
    def format_name(self) -> str:
        return "json"

    def export(self, rows: Sequence[ReportRow]) -> str:
        rows = [
            {"record_id": r.record_id, "metric": r.metric, "value": r.value}
            for r in rows
        ]

        return json.dumps(rows, indent=self._indent)


@BaseExporter.register("csv")
class CsvExporter(BaseExporter):
    def __init__(self, *, delimiter: str = ",", include_header: bool = True):
        if len(delimiter) != 1:
            raise ValueError("delimiter must of single character")

        self._delimiter = delimiter
        self._include_header = include_header

    @property
    def format_name(self) -> str:
        return "csv"

    def export(self, rows: Sequence[ReportRow]) -> str:
        lines: list[str] = []
        if self._include_header:
            lines.append(f"record_id{self._delimiter}metric{self._delimiter}value")

        for r in rows:
            lines.append(
                f"{r.record_id}{self._delimiter}{r.metric}{self._delimiter}{r.value}"
            )
        return "\n".join(lines)


@BaseExporter.register("markdown")
class MarkdownExporter(BaseExporter):
    def __init__(self, *, precision: int = 2):
        if precision < 0:
            raise ValueError("precision cannot be negative")

        self._precision = precision

    @property
    def format_name(self) -> str:
        return "markdown"

    def export(self, rows: Sequence[ReportRow]) -> str:
        lines = ["| record_id | metric | value |", "| --- | --- | --- |"]

        for r in rows:
            lines.append(
                f"| {r.record_id} | {r.metric} | {r.value:.{self._precision}f} |"
            )

        return "\n".join(lines)


class ReportJob(ABC):
    def __init__(self, *, title: str) -> None:
        title = title.strip()
        if not title:
            raise ValueError("title cannot be empty")

        self._title = title

    @abstractmethod
    def _create_export(self) -> ReportExporter: ...

    def generate(self, rows: Sequence[ReportRow]):
        exporter = self._create_export()
        body = exporter.export(rows)

        return f"# {self._title} [{exporter.format_name}]\n{body}"


class DailyJsonReportJob(ReportJob):
    def __init__(self, *, title: str, indent: str | None = 2):
        super().__init__(title=title)
        self._indent = indent

    def _create_export(self) -> ReportExporter:
        return JsonExporter(indent=self._indent)


class AuditCsvReportJob(ReportJob):
    def __init__(self, *, title, delimiter: str = ","):
        super().__init__(title=title)
        self._delimiter = delimiter

    def _create_export(self):
        return CsvExporter(delimiter=self._delimiter)
