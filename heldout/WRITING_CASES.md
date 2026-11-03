# Writing a held-out case set

A held-out set tests the evaluator (how findings are located and judged) on findings written by someone who has
**not read the code**. Read only `docs/EVAL_METHOD.md`, this file, and the packages and truth files named below.
Do not open anything under `aae/`, `tests/`, `config/` or other sets in `heldout/`.

## Material

- Packages: `data/heldout/packages/heldout-7000` … `heldout-7011` (PDFs; build them with `aae build heldout`).
- Truth: `data/heldout/truth/<package>.json` — the seeded errors with their acceptable locations and types,
  the decoy, the rounding differences, and `placed` (every location id with page, printed text, row label and
  column header).

## What to write

`heldout/<set>/cases.yaml`, a list of findings in the order an agent would return them, grouped by package:

```yaml
- package: heldout-7003
  finding:              # exactly the fields of a finding in EVAL_METHOD.md §3
    type: casting
    document: jahresabschluss_2026.pdf
    page: 2
    row_label: "Summe Aktiva"
    column: "31.12.2026 TEUR"
    found_value: "109.962"
    expected_value: "109.926"
    explanation: "..."
  expect:
    verdict: hit        # hit | duplicate | mistyped | decoy | rounding | unlocated | false_alarm
    defect: heldout-7003.d1   # the error id for hit, duplicate and mistyped; omit otherwise
  why: "one line: which rule of EVAL_METHOD.md decides this"
```

Write 50 to 80 findings across at least 8 packages. Cover every verdict and every kind, and write them the
way different reviewers would: exact labels and loose ones (without numbering, part of a long label), headers
as printed and as a bare year, missing pages or columns, values with and without "TEUR" or "%", quotes that are
a whole sentence or a fragment, missing disclosures named in German and in English, findings on the prior-year
report, findings that point at a symptom rather than the cause, a second finding for the same error, a wrong
type at the right place, rounding differences and the restatement flagged as errors, and plain mistakes.
Decide each expected verdict from EVAL_METHOD.md alone. Where the document leaves a case open, say so in
`why` and choose what a careful reader of the document would expect; do not guess at the implementation.

Also write `heldout/<set>/README.md`: who wrote it, from what, and anything in EVAL_METHOD.md you found
ambiguous. Leave `heldout/<set>/STATUS` containing `blind`.

## The rule

The set is run once and its first run is recorded in `reports/heldout/<set>/first_run.json`, which is never
rewritten. Nobody changes the evaluator to pass a set before that. If someone studies a set's failures, its
STATUS becomes `regression` and a new set is written by someone else, from this file only.
