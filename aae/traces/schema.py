"""One definition of the trace tables; the Parquet archive, ClickHouse and BigQuery schemas are generated from it.

runs      one row per (evaluation run, package): the agent's answer for that package, scored
spans     one row per step of an agent run (reads, checks, model calls) with tokens, cost and latency
findings  one row per finding, with the evaluator's verdict and the defect it matched
"""

from __future__ import annotations

import pyarrow as pa

# logical type -> (arrow, ClickHouse, BigQuery)
TYPES = {
    "string": (pa.string(), "String", "STRING"),
    "string?": (pa.string(), "Nullable(String)", "STRING"),
    "int": (pa.int64(), "Int64", "INT64"),
    "int?": (pa.int64(), "Nullable(Int64)", "INT64"),
    "float": (pa.float64(), "Float64", "FLOAT64"),
    "bool": (pa.bool_(), "Bool", "BOOL"),
    "date": (pa.date32(), "Date", "DATE"),
    "timestamp": (pa.timestamp("ms", tz="UTC"), "DateTime64(3, 'UTC')", "TIMESTAMP"),
    "json": (pa.string(), "String", "JSON"),
}

COMMON = [
    ("run_id", "string", "evaluation run: agent, split, answers"),
    ("day", "date", "day the run was recorded"),
    ("agent", "string", "name@version"),
    ("split", "string", "dataset split"),
]

TABLES: dict[str, list[tuple[str, str, str]]] = {
    "runs": COMMON
    + [
        ("package", "string", "package id"),
        ("recorded_at", "timestamp", "when the run was recorded"),
        ("error", "string?", "agent error, if any"),
        ("findings", "int", "findings returned"),
        ("defects", "int", "seeded defects in the package"),
        ("found", "int", "defects found"),
        ("pages_read", "int", "pages with a text layer or read by the model"),
        ("pages_unreadable", "int", "pages the agent could not read"),
        ("scanned", "bool", "the package contains a scanned report"),
        ("cost_usd", "float", "model cost"),
        ("latency_ms", "float", "wall time of the agent's steps"),
    ],
    "spans": COMMON
    + [
        ("package", "string", "package id"),
        ("seq", "int", "position in the run"),
        ("name", "string", "step"),
        ("kind", "string", "retrieve | extract | check | llm | tool | other"),
        ("started_ms", "float", "offset from the run's start"),
        ("duration_ms", "float", "duration"),
        ("input_tokens", "int", "model input tokens"),
        ("output_tokens", "int", "model output tokens"),
        ("cache_read_tokens", "int", "prompt-cache reads"),
        ("cost_usd", "float", "cost"),
        ("model", "string", "model alias"),
        ("status", "string", "ok | error"),
        ("attributes", "json", "other attributes"),
    ],
    "findings": COMMON
    + [
        ("package", "string", "package id"),
        ("idx", "int", "position in the agent's answer"),
        ("type", "string", "finding type"),
        ("document", "string", "file"),
        ("page", "int?", "page"),
        ("row_label", "string?", "line item as printed"),
        ("col", "string?", "column header as printed"),
        ("quote", "string?", "sentence, heading or disclosure"),
        ("found_value", "string?", "value shown"),
        ("expected_value", "string?", "value the agent expected"),
        ("explanation", "string", "agent's reason"),
        ("confidence", "float", "agent's confidence"),
        ("verdict", "string", "hit | duplicate | mistyped | decoy | rounding | unlocated | false_alarm"),
        ("defect", "string?", "matched defect id"),
        ("located", "string", "how the finding was located"),
    ],
}

ORDER_BY = {
    "runs": "(agent, split, package, run_id)",
    "spans": "(run_id, package, seq)",
    "findings": "(run_id, package, idx)",
}


def arrow_schema(table: str) -> pa.Schema:
    return pa.schema([pa.field(n, TYPES[t][0], nullable=t.endswith("?")) for n, t, _ in TABLES[table]])


def _quote(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


def clickhouse_ddl(table: str, database: str, hot_days: int) -> str:
    cols = ",\n  ".join(f"`{n}` {TYPES[t][1]} COMMENT '{_quote(d)}'" for n, t, d in TABLES[table])
    return (
        f"CREATE TABLE IF NOT EXISTS {database}.{table} (\n  {cols},\n  `ingested_at` DateTime64(3, 'UTC') DEFAULT now64(3)\n)\n"
        f"ENGINE = ReplacingMergeTree(ingested_at)\nPARTITION BY toYYYYMM(day)\nORDER BY {ORDER_BY[table]}\n"
        f"TTL day + INTERVAL {hot_days} DAY DELETE"
    )


def bigquery_schema(table: str) -> list[dict]:
    return [
        {"name": n, "type": TYPES[t][2], "mode": "NULLABLE" if t.endswith("?") else "REQUIRED", "description": d}
        for n, t, d in TABLES[table]
    ]
