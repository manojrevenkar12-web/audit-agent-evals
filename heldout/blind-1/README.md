# Held-out set blind-1

Written by a Claude subagent that had not seen the code, from docs/EVAL_METHOD.md and the package files only
(the PDFs under `data/heldout/packages/heldout-7000` … `heldout-7011` and the truth files
`data/heldout/truth/*.json`, with `placed` used for the scanned reports). Nothing under `aae/`, `tests/`,
`config/`, `web/`, `infra/`, the scripts, or any other `heldout/` set was opened, and no evaluator was run.

## Contents

- `cases.yaml`: 78 findings across all 12 packages, in the order an agent would return them, grouped by
  package. Every seeded error (17) is the `hit` of exactly one finding.
- Verdicts: hit 17, duplicate 16, rounding 15, false_alarm 14, mistyped 7, unlocated 5, decoy 4.
- Finding types: casting 32, missing_disclosure 14, tie 11, prior_year 10, narrative 7, period 4.
- Scanned packages (7001, 7002, 7003, 7009, 7010) have 27 findings; clean packages (7008 with a decoy,
  7010 without one) have 10.
- Cases marked `OPEN:` in `why` depend on a point EVAL_METHOD.md leaves open (listed below). For each one,
  the expected verdict is what a careful reader of the document would expect.

## Ambiguities found in EVAL_METHOD.md

1. **No `period` errors in this split.** None of heldout-7000…7011 has a seeded `period` error, so `period`
   findings here can only be `false_alarm`, `unlocated` or `mistyped`. The kind is covered as a finding type
   only.
2. **Fall-through between the §4 steps.** "In this order" does not say whether a step that applies but finds
   nothing hands over to the next step (for example, a quote with no matching heading going on to claims and
   then to step 5). This set assumes it does, and that the first step that finds something decides.
   Several cases depend on this (7000 quote "Summe Passiva", 7002 value-only finding, the unlocated cases).
3. **Period findings with a row label.** Step 2 ("if a row label is given") comes before step 3 ("for period
   findings"). Read literally, a period finding with a row label is located as a cell (7006 case gives
   `mistyped`). The other reading sends period findings to headings only.
4. **Several locations.** A finding can resolve to several locations (every cell of a row, headers that
   contain the column text, duplicate labels on one page). §5 says "points at" without saying whether any
   one of them is enough. This set assumes any one is enough. Error verdicts come first, then decoy, then
   rounding ("and at no error", "and at no error or decoy").
5. **Two errors at once.** If one finding's locations cover two errors, one already found and one not, §5
   does not say which error it is matched to. This set assumes `hit` for the error not yet found (7003 total
   row). If both errors are still unfound, nothing in the document decides.
6. **Missing column vs. column that matches nothing.** Step 2 describes "if the column matches nothing" but
   not the case where no column is given. This set treats a missing column as matching nothing, so the
   found_value fallback and then "every cell of the row" apply.
7. **The `document` field.** §3 says a finding names its document, but §4 never says that locating is
   limited to that document. Labels such as "Summe Passiva" and "Andere Anlagen, …" appear in both reports,
   sometimes on the same page number. The cases were written so the verdict is the same either way where
   possible.
8. **Year matching and the prior-year report.** "A year both share" gives this year's py cell and last
   year's cy cell (both headed "31.12.2025 TEUR") when the document is not used to narrow the search.
9. **Matching words for missing disclosures.** §4 gives examples and points to `config/matching.yaml` for
   the full list. Whether "fixed asset schedule" (English) or "Honorar des Abschlussprüfers" (German table
   title) names a disclosure is not stated. This set expects both to match; see the 7001 and 7009 duplicates.
   It also does not say whether section references (e.g. "§ 285 Nr. 17") count as names.
10. **Value normalisation.** Step 4 ignores only a trailing "%" or "TEUR". It is not said whether "47.4"
    matches "47,4" (this set says no, so `unlocated`), whether `found_value` "3.635 TEUR" matches a cell
    printed "3.635" in steps 2 and 5, or how "47,4%" without a space is handled (this set says it matches).
11. **"Claims on the given page (or anywhere)".** This could mean "anywhere when no page is given" or "fall
    back to anywhere when the page has no match". It also says "the claim sharing at least half of its
    words" without saying whose words ("its" could mean the claim or the quote) or how words are split.
12. **Where the restatement is.** §1 says the notes disclose the restatement, but the decoy's locations in
    the truth are only this year's comparative cells. Flagging the disclosure sentence (7005) resolves to
    nothing (`unlocated`). Flagging the restatement on last year's report (7007) gives a cell that is not a
    decoy location (`false_alarm`). The document does not say whether either should count as `decoy`.
13. **Heading matching details.** Step 3 does not say whether numbering ("4. Verbindlichkeiten") or case is
    ignored for headings, as it is for row labels. It also does not say whether a quote can match a block
    title that is not a heading (e.g. "Verbindlichkeitenspiegel (TEUR)").
14. **Page that does not match.** "A page, if given and matching, narrows them" is read as: a page with none
    of the candidate labels is ignored (7005 "Gesamthonorar" on the wrong page).
15. **Rounding difference "total".** §5 says `rounding` is for "a total with a rounding difference". The
    truth also lists schedule cells such as accumulated depreciation, which are not totals in the usual
    sense. This set treats every listed rounding location as eligible.
