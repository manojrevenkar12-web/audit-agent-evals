# Working on audit-agent-evals

## Fast feedback

- `pytest -q` (about 15 seconds; builds the 16-package `unit` split on first run).
- `ruff check aae tests && ruff format --check aae tests && mypy aae`.
- `aae build && aae eval baseline --split dev` (about a minute) for real numbers.
- `aae release <candidate>` runs production and the candidate on the `test` split and applies the gates.
- Model-based agents and the judge call Claude through the Claude Code CLI; answers are cached in
  `data/llm_cache/`. `AAE_LLM=off` makes a cache miss an error instead of a paid call (CI uses it).

## Invariants (each has a test)

1. **Agents never see the truth.** Code in `aae/agents/` imports only `aae.config` and `aae.agents`, never names
   truth files or the location map, and reads only the PDFs in a package folder (`tests/test_isolation.py`).
   Prompts do not describe how the data is made.
2. **Every finding gets exactly one verdict with a reason** (hit, duplicate, mistyped, decoy, rounding,
   unlocated, false alarm). Precision and the false-alarm breakdown always add up (`tests/test_match.py`).
3. **Gates decide releases.** A candidate ships only if it meets the floors and is non-inferior to production on
   the `test` split, paired by package (`config/gates.yaml`, `tests/test_metrics_gate.py`). `test` is never
   used to build or tune an agent; use `dev`.
4. **The archive is the record.** Runs are written once as Parquet with a SHA-256 manifest; run ids come from
   the answers, so recording twice changes nothing; ClickHouse is rebuilt from the archive; replay re-scores an
   archived run without the agent; runs named by a release decision are never pruned (`tests/test_traces.py`).
5. **One table definition.** Parquet, ClickHouse and BigQuery schemas come from `aae/traces/schema.py`;
   regenerate `infra/bigquery/*.json` with `aae schema`.
6. **Settings live in `config/`**, not in code: dataset mix, agent variants, HGB reading knowledge, matching,
   gates, trace retention, judge.
7. **Change behaviour, bump the version.** An agent's saved answers are keyed by `name@version`; a change to an
   agent's code or prompt without a new version would mix old and new answers.

## Held-out rule

`heldout/<set>/` holds cases written by someone who has not read the code. Never change the matcher, metrics or
gates to pass a set before its first run is recorded in `reports/heldout/<set>/first_run.json`; that file is never
rewritten. If you study a set's failures, write `regression` to `heldout/<set>/STATUS` and have someone who has
not seen the code write a new set from `heldout/WRITING_CASES.md` only.
