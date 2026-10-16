# SecurePrint

**Every page checked before it prints.**

> **Tried SecurePrint or read about it? [Give us feedback](https://github.com/kwhanweerasekara-eng/secureprint/issues/new?template=review.yml)** with the review form, or join the [Reviews and feedback discussion](https://github.com/kwhanweerasekara-eng/secureprint/discussions/1).

SecurePrint is a print data loss prevention (DLP) system. It adds a virtual printer to the staff computer, checks every document at the moment it is printed, classifies it, masks only the sensitive values, labels every page and keeps an audit trail. Staff print from any application as usual and simply choose the SecurePrint printer.

It was built for small businesses that print personal data every day (pharmacies, clinics, offices) but cannot justify an enterprise DLP suite, and is proposed for Koswaththa Pharmacy and Grocery.

## How it works

1. **Capture.** The user prints to the *SecurePrint Protected Printer*. The operating system turns the job into a PDF and hands it to the capture agent, which uploads it to the SecurePrint server with the user's personal access token and deletes the unmasked local copy.
2. **Read.** The server extracts every word with its exact position on the page (PyMuPDF).
3. **Detect.** Regular expressions and a keyword dictionary find 12 categories: credentials, API keys, payment cards (Luhn checked), bank accounts, IBANs, Sri Lankan NIC numbers, passports, salaries, employee IDs, email addresses, phone numbers and classification markers. Labels are read from the page layout (the cell to the left and the nearest column heading), so values in tables and forms are found.
4. **Score and classify.** Each category found adds its weight, capped at 100:

   | Score | Level | What happens |
   |---|---|---|
   | 0 to 20 | Public | Printed at once with a footer |
   | 21 to 40 | Internal | Printed at once with a footer |
   | 41 to 70 | Confidential | Security alert, then a masked copy with a footer |
   | 71 to 100 | Restricted | Security alert, then a masked copy with a watermark and footer |

   A real password, API key or card number makes a document Restricted whatever its score (category floors).
5. **Decide.** The security alert lists the categories found and how many, never the values. It has two buttons, *Cancel printing* and *Mask and print*. Cancel is the default, and closing the window or pressing Escape also cancels.
6. **Mask, label, verify, release.** Sensitive values are removed from the PDF (true redaction, not a box drawn on top), a classification footer is stamped on every page, and Restricted pages get a watermark. The masked file is opened again and searched for every masked value. If anything can still be read, the job is blocked. Only the processed copy is released, to a network printer, a local printer or a folder.

Every step is written to an audit log and shown on the web dashboard.

### It fails closed

If the server cannot be reached, the SecurePrint printer reports *Waiting for the SecurePrint server* and the operating system keeps the job in its print queue until the server is back. If a document cannot be read or the masking cannot be verified, nothing is printed and the user is told why.

## Dashboard

- **Live print monitor.** A pop-up appears on any dashboard page the moment a job is printed, coloured by level (with a chime for Restricted). It shows the document, what happened to it, the kinds of data found with counts and who printed it, never the values.
- **Why this score?** Each job's page shows the points every kind of sensitive data added to the risk score, the total, and why a level was raised (for example a password found on its own).
- **Compliance report.** On the Audit page, administrators can download a PDF for any date range: documents by level, masked, cancelled and blocked jobs, the most common sensitive data, jobs per user and recent restricted documents. It contains no detected values.
- Jobs, the audit log, rules, policies, printers, users and access tokens are all managed from the dashboard. Documents are checked only by printing to the SecurePrint printer.

## Print capture

| Platform | How the job is captured | Status |
|---|---|---|
| macOS | CUPS sends the job to a small IPP/1.1 printer receiver (`apps/linux-agent/ipp_receiver.py`) that listens only on `localhost:8001` and accepts only PDF | Tested end to end on a MacBook |
| Ubuntu | A `cups-pdf` printer writes each job into a private spool folder | Tested with real CUPS 2.4 in a container |
| Windows | `apps/windows-agent`: Microsoft Print to PDF on a file port, PowerShell capture script, Windows Forms alert | Written, not yet tested on a Windows PC |

The agent keeps the copies, two-sided and colour settings from the print dialog and applies them when the masked copy is released. Landscape pages that the print system turned sideways are shown upright before the footer is stamped.

## Repository layout

```
apps/api/                FastAPI server: print jobs, decisions, users, rules, policies, audit, reports
apps/web/                Next.js dashboard
apps/linux-agent/        Capture agent and printer setup for macOS and Ubuntu
apps/windows-agent/      Capture agent for Windows (PowerShell)
services/document-analysis/     Text extraction and detection
services/classification/        Scoring, thresholds, category floors, policies
services/document-processing/   Redaction, watermark, footer, verification, page orientation
services/audit/                 Audit events
config/                  Detection patterns, keywords and weights (JSON)
tests/                   Automated tests, fixtures and the evaluation scripts
scripts/secureprint-mac.sh      Start, stop, restart, status and logs on macOS
docs/                    Run guides and evaluation results
```

## Setup on macOS

You need Python 3.12 from python.org (it includes Tkinter for the alert), Node.js LTS and Apple's command line tools (`xcode-select --install`).

```bash
git clone https://github.com/kwhanweerasekara-eng/secureprint.git
cd secureprint
make venv            # Python environment and API requirements
make install-web     # dashboard packages
cp apps/web/.env.local.example apps/web/.env.local
scripts/secureprint-mac.sh start
```

Open http://localhost:3000 and sign in. The first start creates an administrator account with the password from `DEFAULT_ADMIN_PASSWORD` (`admin123` if it is not set). **Change it straight away**, and set a long random `JWT_SECRET` (see `.env.example`) before using SecurePrint with real documents.

Then add the printer and the capture agent:

1. In the dashboard, open **Tokens** and create a personal access token.
2. Copy `apps/linux-agent/agent.conf.example`, fill in `SERVER_URL` and `API_TOKEN`, and follow the macOS section of `apps/linux-agent/README.md` to run `setup-printer-mac.sh`.
3. Print any document and choose **SecurePrint Protected Printer**.

The full step by step guides are in `docs/move-to-another-mac.md` and `docs/start-stop-mac.md`. For Ubuntu see `apps/linux-agent/README.md`, and for Windows see `apps/windows-agent/README.md`.

### Start and stop

```bash
scripts/secureprint-mac.sh status     # what is running and how many jobs are waiting
scripts/secureprint-mac.sh start
scripts/secureprint-mac.sh stop
scripts/secureprint-mac.sh restart
scripts/secureprint-mac.sh logs
```

Run these from the project folder. A Docker setup (`docker-compose.yml`, `make up`) is also included for the server and dashboard.

## Tests

```bash
./.venv/bin/python -m pytest -q
```

156 automated tests cover every detection rule, the layout context, scoring and floors, redaction and verification, the REST API, the print capture receiver and the virtual printer flow. The evaluation scripts are in `tests/evaluation/realistic/` and are described in `docs/evaluation-results.md`.

## Results

Evaluated on 67 realistic office documents of 21 types with 485 annotated sensitive values, plus a hold out set of 18 documents of 6 new types that was scored only once. Every name and number in the test documents is synthetic.

| Measure | Main set | Hold out set |
|---|---|---|
| Sensitive values found (recall) | 99.8% | 100% |
| Detections that were correct (precision) | 94.3% | 88.2% |
| Values still readable after masking | 0 of 482 | 0 of 45 |
| Classification agreement with reviewers | 70.1% | 83.3% |

A typical 20 page document is processed in 0.35 seconds, and a dense 20 page payroll file (about 270 values per page) in 2.7 seconds, inside the 3 second target.

## Limitations

- **Simulated reviewers.** The classification reference labels came from User 1, User 2 and User 3, three reviewer roles simulated by the project team, not from independent people.
- **Team written test documents.** Both realistic sets were written by the team, so real documents may score lower.
- **Scanned pages.** Pages without a text layer are blocked rather than read, because there is no OCR yet.
- **Local formats.** The rules target Sri Lankan documents. Formats without a rule, such as a US social security number or a date of birth, are not masked.
- **False alarms.** Public hotlines and prices near the word *payroll* still add points, so some ordinary documents raise an alert.
- **Masking check.** Verification searches the text of the output. It does not read text inside images.

## Team

IE3092 Information Security Project, BSc (Hons) in Information Technology specialising in Cyber Security, Sri Lanka Institute of Information Technology (SLIIT).

| Name | Student ID |
|---|---|
| Weerasekera H.K.H. | IT23626942 |
| Dilushanka D.P.N. | IT23601192 |
| Nehanya M.D.V. | IT23763708 |
| Mawathagama H.M.P.R.B. | IT23579972 |
