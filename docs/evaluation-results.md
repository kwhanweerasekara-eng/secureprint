# Evaluation results: realistic corpus

Objective 14 and section 3.9 of the proposal. Produced by the scripts in
`tests/evaluation/realistic/`. Run on 14 October 2026 on a 4-core Linux
machine. "Before" is the engine as it was handed over; "after" is the engine
after the fixes driven by the first run (the iterative refinement of
section 3.1), the card security code rule and the category floors (T05).

## Why a second corpus

The original synthetic set (`tests/evaluation/generate_dataset.py`, 92
documents) builds every document from fragments written to trigger exactly
one rule each, so its 100% scores only show that the rules match themselves.
The realistic corpus (`corpus.py`) is written the way staff actually write:
labels such as "NIC No." or "A/C", phone numbers with spaces or `+94`, values
in table cells and form fields, multi-page payroll sheets, and many harmless
numbers that look sensitive (invoice and PO numbers, VAT numbers, serials,
prices, public hotlines). Every sensitive value is annotated inline, which
allows value-level scoring and a check of what is still readable after
masking.

- **Main corpus:** 67 documents, 21 office document types, 485 values. This
  is the corpus the fixes were developed against.
- **Hold-out corpus:** 18 documents, 6 new document types, 45 values. Written
  after the first run, and the rules were not adjusted against it. It shows
  whether the fixes generalise, though it shares the same value generators,
  so it is still not a substitute for real-world documents.

## Results

| Measure | Main, before | Main, after | Hold-out, after |
|---|---|---|---|
| Value precision | 85.9% | 94.3% | 88.2% |
| Value recall | 47.6% | 99.8% | 100% |
| Category precision | 59.6% | 69.6% | 82.3% |
| Category recall | 83.2% | 100% | 100% |
| **Values readable after "Mask and print"** | **184 of 482 (38.2%)** | **0 of 482** | **0 of 45** |
| Classification vs simulated reviewers (User 1-3) | - | 70.1% | 83.3% |

The original synthetic set (92 documents) still scores 100% on every measure.

Value recall is now 100% for every category except NIC (99%, one miss).
The three card security codes (CVV) that were missed before are found by a
new `card_security_code` rule. It only fires on a 3 or 4 digit number next to a
"CVV", "CVC" or "Security code" label.

## Classification and the simulated reviewers

**The reviewer labels are simulated.** Three human reviewers were not
available, so the labels in `reviewer_labels.csv` were written by the author
playing three reviewer roles, called **User 1-3 (simulated)**:

- **User 1** applies Table 3.1 strictly.
- **User 2** reads it from a personal-data (PDPA) point of view.
- **User 3** is a pragmatic office manager.

Each simulated reviewer labelled every document type on its own, before
seeing the engine's output. These figures show that the method works, but
they are not a human study. **The dissertation must say that the reviewers
were simulated**, and the step should be repeated with real people if time
allows. The column names `user_1_simulated` and so on, and every report and
script output, keep the label.

| Measure (main corpus, 67 documents) | Result |
|---|---|
| Agreement between the simulated reviewers (Fleiss' kappa) | 0.762 (50 of 67 unanimous) |
| Engine vs reviewer majority, thresholds 20/40/70 | 70.1% |
| Best thresholds found by search | 20/40/70 (no change is better) |
| 5-fold cross-validated accuracy | 67.2% |
| Hold-out corpus (18 documents, not used for fitting) | 83.3% |

The proposal's thresholds were already the best fit, so they were kept. Most
of the remaining disagreement comes from two document types:

- Invoices are scored CONFIDENTIAL where the reviewers chose INTERNAL.
- Brochures are scored INTERNAL where the reviewers chose PUBLIC. A price on a
  line that mentions "payroll" and a public hotline add points.

**Category floors (T05).** Some values make a document Restricted on their
own, whatever the total score: a password, an API key or a card number.
`config/weights.json` now gives these categories `"min_classification":
"RESTRICTED"`, and the pipeline raises the score-based level to that floor. A
floor applies only when the value itself was found. The bare word "password"
in a policy document does not trigger it. The audit log records when the
level was raised. An admin can change the floors through the
`category_floors` system setting.

## Processing time

Full server path: extract, detect, score, classify, mask, watermark, footer,
save, then re-open the file to check that nothing masked can still be read.
Median of three runs, with the worst run in brackets. Run with
`benchmark_latency.py` and saved in `latency.json`.

| Document | Values found | Before | After first fixes | Now |
|---|---|---|---|---|
| 20 pages, typical office documents | 83 | 353 ms | 402 ms | 346 ms (494 ms) |
| 100 pages, typical (T07) | 413 | 1.6 s | 1.8 s | 1.8 s (2.0 s) |
| 20 pages, dense payroll (about 270 values a page) | 5,408 | 3.7 s | 9.5 s | **2.7 s (2.8 s)** |
| 100 pages, dense payroll | 27,203 | 23 s | 55 s | 16 s (18 s) |

The 3-second target for a 20-page document is now met in both profiles,
including the worst case. Dense pages had become slow because the fixed
engine finds three times as many values and PyMuPDF redacts them one box at a
time. Two changes brought the time down:

- Boxes stacked in the same table column are merged into one, but only if the
  merged box covers no other words.
- Redactions are applied in batches.

The dense 20-page case has little headroom, so slower hardware may miss the
target.

## What was changed

| Problem found in the first run | Fix |
|---|---|
| A label only counted on the value's own line, so table columns ("Gross pay"), form fields ("Account no. \| 1234...") and table passwords were missed. This was the main cause of leaks. | Context also comes from the cell to the left on the same row and the nearest column header above (a short line with no digits). A label at the end of a wrapped line counts for the next line, unless that label already has its own value. |
| Phones written `077 123 4567`, `077-1234567`, `+94 77 123 4567` were missed. | Telephone pattern covers spaced, dashed and `+94` forms. |
| `DB_PASSWORD=...` was missed, and passwords in table cells or form fields had no label on their line. | Credential pattern no longer needs a word boundary before "password". New `credential_field` rule finds password-shaped values under a Password header or beside a Password label. |
| CVV codes on card forms had no rule. | New `card_security_code` rule: 3 or 4 digits next to a CVV/CVC/security code label. The card number Luhn check now applies only to 12+ digit numbers. |
| A credential or card number alone could score below Restricted. | Category floors (T05), see above. |
| Dense payroll pages took 9.5 s for 20 pages. | Column-run box merging and batched redaction (see Processing time). |
| Organisation formats such as `SL/04512` or `E01234` were missed. | New `employee_id_field` rule finds any letters-plus-digits code labelled as an employee number. |
| Account numbers written in groups (`0012 3456 7890`) were missed. | Account pattern accepts grouped digits. |
| Every `Rs.`/`LKR`/`USD` amount counted as a salary, so prices and invoice totals added 20 points and were masked. | Currency amounts only count as salary with a salary label nearby. |
| The keyword "account" fired on "Accounts Executive" and `accounts@...`. | Keywords match whole words only. |
| 12-digit PO numbers (`4500...`) were taken for new-format NICs. | New NIC check reads the birth year from the first four digits and requires 1900 to 2030. The old check read the wrong digits. |

Tried and dropped: scoring keyword-only categories at half weight, to stop
the bare word "password" in a policy from adding 40 points. It lowered
agreement with the author's provisional labels (61.2% to 55.2%), so it was
reverted.

Existing installations get the improved rules automatically on the next
start. `upgrade_builtin_rules` in `apps/api/services/seed.py` updates a
built-in rule only if it still has its original pattern, so rules an admin
has edited are left alone. The two new rules are added by the existing seeding.

## Remaining false positives

These are counted as errors here, but some are judgment calls a reviewer may
accept:

- Public contact details: company hotlines and role mailboxes (`hello@`, `accounts@`, `media@`).
- "Account" in non-banking senses ("remote access account").
- Prices on a line that also mentions payroll ("...invoicing and payroll. Packages start from Rs. 4,990").
- Classification words used in passing ("pricing is confidential").

## How to reproduce

```
python tests/evaluation/realistic/corpus.py                 # main corpus (67 PDFs)
python tests/evaluation/realistic/corpus.py holdout         # hold-out corpus (18 PDFs)
python tests/evaluation/realistic/run_realistic.py          # accuracy, masking, latency
python tests/evaluation/realistic/run_realistic.py holdout
python tests/evaluation/realistic/benchmark_latency.py      # 1 to 100 pages
python tests/evaluation/realistic/calibrate_thresholds.py calibrate   # kappa, thresholds, cross-validation
```

Unit tests for each fix are in `tests/test_detection_layout.py`, and the
category floors are tested in `tests/test_virtual_printer_flow.py`. The full
suite (156 tests) passes.

Four unused synthetic PDFs from an earlier dataset version
(`045`-`048_confidential_credential_email`) and eight orphaned by the
scenario rename were removed from `tests/fixtures/synthetic`. None was
listed in the manifest. On the Mac copy they were moved to
`_backup-before-update-2026-10-14` instead of being deleted.
