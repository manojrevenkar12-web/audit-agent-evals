# 4. Traces: an append-only Parquet archive, ClickHouse for queries, BigQuery on GCP

**Context.** Every evaluation run must stay explainable months later (which answers, which verdicts, at what
cost), and old runs must be re-scorable when the matcher changes. Query load is analytical: cost per agent,
latency percentiles, verdicts by type over time.

**Decision.** Each run is written once as Parquet (runs, spans, findings) with a SHA-256 manifest, under a
day-partitioned path that maps one-to-one to GCS. Run ids are derived from the answers, so recording twice is
harmless. ClickHouse (embedded via chdb locally) holds the hot part with a TTL, uses ReplacingMergeTree and is
read with FINAL, and can be rebuilt from the archive. On GCP the same Parquet layout sits in GCS (lifecycle to
Coldline, deletion after 400 days) with BigQuery partitioned tables for the hot part and an external table over
the archive. Runs that a release decision rests on are pinned and never pruned. One table definition generates
the Arrow, ClickHouse and BigQuery schemas.

**Consequences.** Replay needs only the archive and the truth, not the agent or the model. Writers get
`objectCreator`, not delete; the API reads only.
