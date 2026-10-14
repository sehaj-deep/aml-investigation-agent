"""OpenTelemetry traces stored in Postgres (FR-6; Langfuse may come later).

Spans are exported straight from the SDK into a `traces` table. There is no
collector service: a collector has no Postgres exporter, and one fewer service
fits the 16 GB budget.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import psycopg
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS traces (
    span_id        TEXT PRIMARY KEY,
    trace_id       TEXT NOT NULL,
    parent_span_id TEXT,
    name           TEXT NOT NULL,
    service        TEXT NOT NULL,
    case_id        TEXT,
    start_time     TIMESTAMPTZ NOT NULL,
    end_time       TIMESTAMPTZ NOT NULL,
    duration_ms    DOUBLE PRECISION NOT NULL,
    status         TEXT NOT NULL,
    attributes     JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS traces_trace_idx ON traces (trace_id);
CREATE INDEX IF NOT EXISTS traces_case_idx ON traces (case_id);
"""


class PostgresSpanExporter(SpanExporter):
    def __init__(self, url: str, service: str):
        self.url = url
        self.service = service
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(SCHEMA)

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        rows = []
        for s in spans:
            attrs = dict(s.attributes or {})
            rows.append(
                (
                    format(s.context.span_id, "016x"),
                    format(s.context.trace_id, "032x"),
                    format(s.parent.span_id, "016x") if s.parent else None,
                    s.name,
                    self.service,
                    attrs.get("case_id"),
                    s.start_time / 1e9,
                    s.end_time / 1e9,
                    (s.end_time - s.start_time) / 1e6,
                    s.status.status_code.name,
                    json.dumps(attrs, default=str),
                )
            )
        try:
            with psycopg.connect(self.url, autocommit=True) as conn, conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO traces (span_id, trace_id, parent_span_id, name, service, case_id,
                        start_time, end_time, duration_ms, status, attributes)
                    VALUES (%s, %s, %s, %s, %s, %s, to_timestamp(%s), to_timestamp(%s), %s, %s,
                        %s::jsonb)
                    ON CONFLICT (span_id) DO NOTHING
                    """,
                    rows,
                )
        except psycopg.Error:
            return SpanExportResult.FAILURE
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None


def setup_tracing(url: str, service: str) -> TracerProvider:
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    provider.add_span_processor(BatchSpanProcessor(PostgresSpanExporter(url, service)))
    trace.set_tracer_provider(provider)
    return provider
