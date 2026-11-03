# How agents are evaluated

This is the contract of the evaluator: what a package is, what counts as finding an error, how the numbers are
computed and how a release is decided. The code in `aae/evals/` implements it; the held-out sets in `heldout/`
are written from this document alone.

## 1. Packages and seeded errors

A package is what a reviewer receives before sign-off: this year's annual report of a German GmbH (balance
sheet, income statement, notes with the fixed-asset and liabilities schedules, management report) and last
year's published report (balance sheet and income statement only, without comparatives). Both are PDFs. In
about one package in five, this year's report is a scan: page images with no text layer.

The figures are generated so that everything ties in exact cents. Every printed line is rounded to TEUR on its
own, so a printed total may differ from the sum of its printed lines; that is a **rounding difference** and is
correct. A total of *n* printed lines may differ from their sum by at most ⌊(n + 1) / 2⌋ TEUR.

Into a quarter of packages nothing is seeded (clean packages). Into the rest, one to three errors are seeded,
each of one kind:

| Kind | What changes | Example |
|---|---|---|
| `casting` | a subtotal or total | "Summe Passiva" shows 109.962 where the lines give 109.926 |
| `tie` | a figure that must equal one in another statement | schedule book value ≠ balance sheet line |
| `prior_year` | a comparative (previous-year column) and the totals above it | comparative 1.479, last year's report 1.499 |
| `narrative` | a number in the notes or management report | "Eigenkapitalquote 62,9 %" where the balance sheet gives 61,4 % |
| `missing_disclosure` | a required note is removed | no auditor's fee table (§ 285 Nr. 17 HGB) |
| `period` | a heading names the wrong year | "Anhang für das Geschäftsjahr 2025" in the 2026 report |

In one package in five, a **restatement** is planted as a decoy: an amount is moved between two lines of the
comparatives and the notes disclose it. The comparatives then differ from last year's report, correctly.

## 2. Ground truth

Every checkable place on the pages has a **location id**:

- a table cell: `<document>:<table>:<row>:<column>`, e.g. `jahresabschluss_2026:bs_liabilities:bs.P.B.2:py`
- a number in prose: `<document>:claim:<claim id>`, e.g. `jahresabschluss_2026:claim:claim.equity_ratio`
- a heading: `<document>:heading:<heading id>`
- a required disclosure: `<document>:disclosure:<key>` with key one of `fixed_asset_schedule`,
  `liabilities_by_term`, `audit_fees`, `employees`, `appropriation`

The truth file of a package lists, for each location on the pages, its page, box, printed text and (for cells)
the printed row label and column header. For each seeded error it lists the **acceptable locations**: the place
changed plus every place whose check the change breaks (the other side of a broken tie, the total and lines of
a sum that no longer adds up). It also lists the **acceptable types**: the error's kind plus the kind of every
check it breaks (a changed schedule book value breaks a tie and the schedule row, so `tie` and `casting` both
fit). It lists the decoy's locations and every rounding difference.

A reviewer who points at any acceptable location, with an acceptable type, has found the error. This is lenient
on purpose: a reviewer who flags the total that does not add up has found the problem even if the wrong line is
another one. Section 7 says what that leniency costs.

## 3. Findings

An agent returns a list of findings. Each has a `type` (one of the six kinds), the `document` (file name),
and as much of a pointer as the reviewer can give: `page`, `row_label` and `column` as printed, a `quote` (a
sentence, heading or the name of a missing disclosure), the `found_value` and `expected_value`, an
`explanation` and a `confidence`.

## 4. Locating a finding

The evaluator turns a finding into location ids, in this order:

1. **Missing disclosure.** A `missing_disclosure` finding is located by the disclosure it names. Words in its row
   label and quote are matched first (German or English: "Anlagenspiegel", "auditor's fee", "Arbeitnehmer",
   "Ergebnisverwendung", "Verbindlichkeitenspiegel", "remaining term", …; the full list is
   `config/matching.yaml`); only if they name none, words in the explanation are used.
2. **A table cell.** If a row label is given, the cells whose printed label equals it are taken. Numbering
   ("A.", "II.", "3.") and case are ignored; if nothing equals it, labels containing it (or contained in it)
   are taken. A page, if given and matching, narrows them. Then the column: an exact header match; else a
   year both share ("2025" finds "31.12.2025 TEUR"); else a header containing the given text. If the column
   matches nothing, a cell whose printed value equals `found_value` is taken when exactly one does; otherwise
   every cell of the row counts.
3. **A heading.** For `period` findings, and for findings with a quote but no row label (other than
   narrative): among the headings on the given page (all headings if that page has none, or no page is
   given), the one whose text equals the quote, else those containing it (or contained in it); a
   `found_value` narrows them.
4. **A number in prose.** Claims on the given page (or anywhere) whose text contains `found_value` (ignoring
   a trailing "%" or "TEUR"); if several do, or no value is given, the claim sharing at least half of its words
   with the quote.
5. **A value on the page.** The one cell on the given page showing `found_value`, if exactly one does.

A finding that resolves to nothing is **unlocated**.

## 5. Verdicts

Every finding gets exactly one verdict:

| Verdict | When | Counts as |
|---|---|---|
| `hit` | it points at an acceptable location of a seeded error not found yet, with an acceptable type | correct |
| `duplicate` | as `hit`, for an error an earlier finding already found | correct |
| `mistyped` | it points at an acceptable location, but its type is not acceptable for that error | wrong |
| `decoy` | it points at a location of the disclosed restatement (and at no error) | wrong |
| `rounding` | it points at a total with a rounding difference (and at no error or decoy) | wrong |
| `unlocated` | it resolves to no location | wrong |
| `false_alarm` | anything else | wrong |

Findings are judged in the order the agent returned them; that order decides which correct finding is the
`hit` and which the `duplicate`. A seeded error is **found** when some finding is its `hit`.

## 6. Metrics

All metrics are ratios of sums over packages:

- **recall** = errors found / errors seeded; also per kind, and separately for packages with and without a
  scanned report (`recall_scanned`, `recall_digital`)
- **precision** = correct findings (`hit` + `duplicate`) / all findings; also per finding type
- **clean false-alarm rate** = clean packages with at least one wrong finding / clean packages
- **decoy false-alarm rate** = packages with a `decoy` verdict / packages with a restatement

A ratio with nothing to count (no errors of a kind, no findings) is undefined, never 0 or 1.

**Intervals.** 95% intervals come from a bootstrap that resamples whole packages (2,000 resamples, fixed seed):
findings in one package share a reader and a layout, so they are not independent. **Comparisons** between two
agents use the same resamples for both (paired), on the same packages; comparing different packages is refused.

## 7. Release gates

A candidate replaces production only if, on the `test` split (never used to build or tune an agent):

- **floors** (point estimates): precision ≥ 0.90, clean false-alarm rate ≤ 0.10, decoy false-alarm rate ≤
  0.15, recall on text documents ≥ 0.85;
- **non-inferiority** against production: for recall and precision overall, the lower end of the 95% interval
  of (candidate − production) is above −0.03; for recall per kind, above −0.10 (−0.15 for the two rarest kinds).

A rule with nothing to count is reported as "n/a"; a decision with no rule passing is not a pass. The numbers
live in `config/gates.yaml`.

**What the leniency costs.** Because any acceptable location counts, a finding at a symptom (the narrative that
no longer matches a wrong comparative) is credited as finding the cause. The judge (below) rejects some of these;
they are listed in the review queue rather than silently re-scored.

## 8. The judge and people

On traffic without seeded truth, a model judges each finding (real error or not) from the PDFs. On seeded
packages its sensitivity and specificity are measured against the verdicts above (`hit`/`duplicate` are
right; `decoy`, `rounding`, `mistyped`, and `false_alarm` on numeric types are wrong; the rest is unknown). The
share of findings it accepts is corrected for its error rates (Rogan–Gladen) to estimate precision.

Findings whose truth is unknown, and findings where the judge and the truth disagree, go to a review queue.
People label them `valid`, `invalid` or `out_of_scope`; the latest label per reviewer counts; items are
settled when all reviewers agree; a quarter of items get a second reviewer, and agreement (Cohen's κ) is
reported. Settled labels and seeded truth together form the golden set.
