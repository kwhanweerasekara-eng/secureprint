# Reviewer guide: labelling the SecurePrint evaluation corpus

Thank you for helping calibrate SecurePrint. Your labels decide where the
classification thresholds sit, so please work **on your own** and do not
discuss documents with the other reviewers until all three columns are done.

## What to do

1. Open each PDF in `tests/fixtures/realistic/` (67 documents, mostly one page).
2. Decide how the printed copy should be handled if it were left on a shared printer.
3. Write one label in your column of `reviewer_labels.csv`: `PUBLIC`,
   `INTERNAL`, `CONFIDENTIAL` or `RESTRICTED`.

Judge the content, not the title. Don't run SecurePrint on the documents
first, and don't look at `manifest.json` or the engine's report.

## The four levels (proposal Table 3.1)

| Level | Meaning | Typical example |
|---|---|---|
| PUBLIC | Safe for release to any audience | Marketing brochure, published notice |
| INTERNAL | For use within the organisation only | Internal procedure, meeting minutes |
| CONFIDENTIAL | Sensitive business or personal information | Employee record, supplier contract |
| RESTRICTED | Highly sensitive or critical | Payroll data, credentials, account details |

If you are torn between two levels, pick the higher one.

All names, ID numbers, account numbers, card numbers and passwords in these
documents are synthetic and do not belong to real people.
