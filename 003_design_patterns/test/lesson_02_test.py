from collections.abc import Sequence
from dataclasses import FrozenInstanceError
import json
import pytest
from lesson_02_factory import (
    AuditCsvReportJob,
    BaseExporter,
    CsvExporter,
    DailyJsonReportJob,
    JsonExporter,
    MarkdownExporter,
    ReportExporter,
    ReportJob,
    ReportRow,
)


@pytest.fixture
def sample_rows() -> list[ReportRow]:
    return [
        ReportRow(record_id="srv-01", metric="cpu_pct", value=42.567),
        ReportRow(record_id="srv-02", metric="mem_pct", value=78.1),
    ]


class TestReportRowAndProtocol:
    def test_report_row_is_frozen_slotted_and_validated(self) -> None:
        row = ReportRow(record_id="r1", metric="latency_ms", value=12.4)
        assert not hasattr(row, "__dict__")

        with pytest.raises(FrozenInstanceError):
            row.value = 99.9  # type: ignore[misc]

        with pytest.raises(ValueError, match="record_id"):
            ReportRow(record_id="  ", metric="latency_ms", value=12.4)

        with pytest.raises(ValueError, match="metric"):
            ReportRow(record_id="r1", metric="", value=12.4)

    def test_base_exporter_is_abstract_and_subclasses_satisfy_protocol(self) -> None:
        with pytest.raises(TypeError, match="abstract"):
            BaseExporter()  # type: ignore[abstract]

        for exporter in (JsonExporter(), CsvExporter(), MarkdownExporter()):
            assert isinstance(exporter, ReportExporter)


class TestClassMethodRegistryAndFactory:
    def test_builtin_formats_registered_and_sorted(self) -> None:
        assert BaseExporter.available_formats() == ("csv", "json", "markdown")

    def test_create_normalizes_format_and_forwards_kwargs(
        self, sample_rows: list[ReportRow]
    ) -> None:
        exporter = BaseExporter.create("  JSON ", indent=2)
        assert type(exporter) is JsonExporter
        assert exporter.format_name == "json"

        output = exporter.export(sample_rows)
        assert "\n  " in output
        parsed = json.loads(output)
        assert parsed == [
            {"record_id": "srv-01", "metric": "cpu_pct", "value": 42.567},
            {"record_id": "srv-02", "metric": "mem_pct", "value": 78.1},
        ]

    def test_create_unknown_format_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported export format"):
            BaseExporter.create("parquet")

    def test_duplicate_format_registration_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(BaseExporter, "_registry", dict(BaseExporter._registry))

        with pytest.raises(ValueError, match="already registered"):

            @BaseExporter.register("  CSV ")
            class DuplicateCsvExporter(BaseExporter):
                @property
                def format_name(self) -> str:
                    return "csv"

                def export(self, rows: Sequence[ReportRow]) -> str:
                    return ""

    def test_empty_format_registration_raises(self) -> None:
        with pytest.raises(ValueError, match="format_name cannot be empty"):
            BaseExporter.register("   ")

    def test_open_closed_plugin_registration_without_modifying_factory(
        self, monkeypatch: pytest.MonkeyPatch, sample_rows: list[ReportRow]
    ) -> None:
        monkeypatch.setattr(BaseExporter, "_registry", dict(BaseExporter._registry))

        @BaseExporter.register("tsv")
        class TsvExporter(BaseExporter):
            @property
            def format_name(self) -> str:
                return "tsv"

            def export(self, rows: Sequence[ReportRow]) -> str:
                return "\n".join(f"{r.record_id}\t{r.metric}\t{r.value}" for r in rows)

        assert "tsv" in BaseExporter.available_formats()
        created = BaseExporter.create("TSV")
        assert type(created) is TsvExporter
        assert created.export(sample_rows) == "srv-01\tcpu_pct\t42.567\nsrv-02\tmem_pct\t78.1"


class TestBuiltinExporters:
    def test_csv_exporter_with_and_without_header(
        self, sample_rows: list[ReportRow]
    ) -> None:
        csv_with_header = BaseExporter.create("csv", delimiter=";")
        assert csv_with_header.export(sample_rows) == (
            "record_id;metric;value\n"
            "srv-01;cpu_pct;42.567\n"
            "srv-02;mem_pct;78.1"
        )

        csv_no_header = CsvExporter(delimiter=",", include_header=False)
        assert csv_no_header.export(sample_rows) == (
            "srv-01,cpu_pct,42.567\n"
            "srv-02,mem_pct,78.1"
        )
        assert csv_no_header.export([]) == ""

    def test_markdown_exporter_formats_precision(
        self, sample_rows: list[ReportRow]
    ) -> None:
        md = BaseExporter.create("markdown", precision=1)
        assert md.export(sample_rows) == (
            "| record_id | metric | value |\n"
            "| --- | --- | --- |\n"
            "| srv-01 | cpu_pct | 42.6 |\n"
            "| srv-02 | mem_pct | 78.1 |"
        )
        assert md.export([]) == (
            "| record_id | metric | value |\n"
            "| --- | --- | --- |"
        )

    def test_exporter_config_validation(self) -> None:
        with pytest.raises(ValueError, match="indent"):
            JsonExporter(indent=-1)
        with pytest.raises(ValueError, match="delimiter"):
            CsvExporter(delimiter="||")
        with pytest.raises(ValueError, match="precision"):
            MarkdownExporter(precision=-2)


class TestFactoryMethodReportJobs:
    def test_report_job_is_abstract_and_validates_title(self) -> None:
        with pytest.raises(TypeError, match="abstract"):
            ReportJob(title="Daily Metrics")  # type: ignore[abstract]

        with pytest.raises(ValueError, match="title cannot be empty"):
            DailyJsonReportJob(title="   ")

    def test_daily_json_report_job_uses_factory_method(
        self, sample_rows: list[ReportRow]
    ) -> None:
        job = DailyJsonReportJob(title="  Daily Infra  ", indent=None)
        rendered = job.generate(sample_rows)
        expected_body = json.dumps(
            [
                {"record_id": "srv-01", "metric": "cpu_pct", "value": 42.567},
                {"record_id": "srv-02", "metric": "mem_pct", "value": 78.1},
            ],
            indent=None,
        )
        assert rendered == f"# Daily Infra [json]\n{expected_body}"

    def test_audit_csv_report_job_uses_factory_method(
        self, sample_rows: list[ReportRow]
    ) -> None:
        job = AuditCsvReportJob(title="Compliance Audit", delimiter="|")
        rendered = job.generate(sample_rows)
        assert rendered == (
            "# Compliance Audit [csv]\n"
            "record_id|metric|value\n"
            "srv-01|cpu_pct|42.567\n"
            "srv-02|mem_pct|78.1"
        )