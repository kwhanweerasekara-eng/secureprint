# Print capture plan: closing the interception gap

This note maps the remaining parts of the project proposal onto the code and
records what was built for print capture and what is still to do.

## Where the project stood

Everything in the proposal's analysis, classification and processing layers
was already in place: PyMuPDF extraction with word geometry, keyword and
regex detection, distinct-category scoring capped at 100, the four
classification levels with the thresholds of Table 3.3, masking, footer,
watermark, the cancel or mask decision, the audit log and release to a
network printer. The web console (the proposal's "future work" central
console) was also done.

Missing were:

| Proposal | Gap |
|---|---|
| Objective 5, section 3.3: background service with a virtual printer | Jobs only entered the system by uploading on the web app's Analyze page. |
| Objective 12, Appendix C: alert dialog on the user's desktop | The decision existed only in the web app. The Windows agent only showed notifications. |
| Objective 14, section 3.9: evaluation with human reviewers and latency targets | Done with simulated reviewers, see `evaluation-results.md`. |

## Design

```
App -> "SecurePrint" printer -> spool file -> capture.ps1 -> API pipeline
    -> (CONFIDENTIAL / RESTRICTED) desktop alert -> cancel, or mask
    -> processed PDF only -> server printer (IPP / socket) or local printer
```

- **Virtual printer.** `setup-printer.ps1` adds a printer named `SecurePrint`
  using the built-in *Microsoft Print to PDF* driver with a local file port.
  Windows renders each job to a PDF at that path with no Save As dialog. This
  matches section 3.3: a virtual printer, no kernel driver, and the PDF path.
  Inspection always happens before any page reaches paper.
- **Capture loop.** `capture.ps1` waits until the spooler has finished the
  file, moves it into the user's own folder, uploads it with the user's
  Personal Access Token (`POST /api/v1/documents/analyze?source=virtual_printer`)
  and deletes the local copy.
- **Desktop alert.** For jobs that need a decision, a Windows Forms dialog
  laid out like Appendix C shows the document name, risk score, classification
  and categories with counts. It never shows the values. *Cancel printing* is
  the default and closing the dialog also cancels.
- **Print control.** Only the server's processed PDF is released, either by
  the server to a printer on the Printers page (`SERVER_PRINTER`) or by the
  agent to a Windows printer (`LOCAL_PRINTER`).
- **Fail closed.** Unreachable server, rejected upload, timeout, scanned
  document or policy block all mean nothing is printed, with a message to
  the user.
- **Audit.** The API records `source: virtual_printer` on the received event
  so evaluation can separate captured jobs from manual uploads.

Windows Forms was chosen over the Tkinter named in Table 3.6 because the
agent is already PowerShell-only with nothing to install. Worth one sentence
in the final report.

## Done in this step

- `apps/windows-agent/setup-printer.ps1`: installs or removes the virtual printer.
- `apps/windows-agent/capture.ps1`: capture, upload, alert dialog, release.
- `agent.bat`, `setup.ps1`, `config.example.bat`, `README.md`: `CAPTURE_ENABLED`,
  `SERVER_PRINTER`, `LOCAL_PRINTER`, `SUMATRA_PATH`.
- `apps/api/routes/documents.py`: optional `source` on uploads, recorded in the audit log.
- `tests/test_virtual_printer_flow.py`: the agent's API calls with a token,
  covering T01 (public prints without an alert), T04 (restricted, masked and
  printed) and T08 (cancel is audited and nothing is released).

The capture script's API flow was exercised against a running API (public
auto-release, mask and print, cancel, server down, release to a socket
printer). The Windows-only parts (the printer cmdlets, spooler timing and the
dialog itself) need a run on a Windows 11 PC.

## Still to do

1. **Try it on Windows 11.** Install the printer, print from Word and Excel,
   and check T01 to T08 end to end on paper.
2. ~~Salary amounts without a currency prefix were not masked.~~ Fixed:
   new `salary_amount_context` rule (Appendix B) masks the amount on salary
   lines and keeps the label. Existing databases pick it up on next start.
3. ~~Failing redaction test.~~ Fixed: the test now verifies only redacted
   values, the same filter the pipeline uses. All 94 tests pass.
4. ~~Evaluation (Objective 14).~~ Done, see `evaluation-results.md`. It
   covers a 67-document realistic corpus plus an 18-document hold-out set,
   threshold calibration and 1 to 100 page latency (20 pages: 0.5 s typical,
   2.8 s dense). The reviewer labels come from **simulated reviewers (User
   1-3)**. Say so in the dissertation, and repeat the labelling with real
   people if possible.
5. ~~Ubuntu secondary target (Table 4.2).~~ Built in `apps/linux-agent/`:
   - `setup-printer.sh` adds a cups-pdf "SecurePrint" printer that writes
     each job into `~/.secureprint/spool`.
   - `capture.py` (standard library plus Tkinter) uploads the job, shows the
     Appendix C alert and releases the processed PDF with `lp` or a server
     printer. It fails closed, like the Windows agent.
   - The same script runs on **macOS**. There `setup-printer-mac.sh` points an
     IPP "SecurePrint Protected Printer" at a small receiver inside
     `capture.py` (`ipp_receiver.py`, localhost:8001), because macOS has no
     cups-pdf.

   Tested in a container with real CUPS 2.4 against a live API:
   - cups-pdf on Ubuntu: a payroll sheet was RESTRICTED, then masked and
     printed; a brochure was released straight away.
   - The IPP receiver, with the queue created by `lpadmin -m everywhere`:
     a cancelled job was audited and nothing was printed; a masked job was
     saved with the RESTRICTED footer.
   - The Tkinter dialog was rendered under Xvfb.

   Still to do is a run on a real Ubuntu desktop (the Mac run passed, see item 6).
6. ~~Try it on macOS.~~ Done on 14 October 2026, on an Apple-silicon
   MacBook Air with Python 3.12.10 from python.org. The Xcode Python 3.9 is too
   old for the server. A payroll sheet printed to "SecurePrint Protected
   Printer" was classified RESTRICTED (score 95), masked after the alert, and
   saved to `~/Desktop/SecurePrint Released`.
   T01 (a public certificate printed with no alert), T04 (masked) and T08
   (cancelled, nothing saved) also passed. A freeze on the second alert in the
   same process was fixed by keeping one persistent Tk root.
7. **Print capture improvements (15 October 2026).** Found by printing through
   real CUPS 2.4 to the IPP receiver and reading back what arrived:
   - **Pages arrived in reverse order with Linux CUPS.** The receiver
     advertised a face-up output tray, so CUPS 2.4 with cups-filters reversed
     every multi-page job (and added a blank page for two-sided jobs). It now
     advertises face-down, and a three-page document arrives as pages 1, 2, 3.
     The Mac's own print system did not reverse pages even before the fix
     (checked on the MacBook), so this affected the receiver on Linux only.
   - **Copies and two-sided were lost.** The receiver now accepts them
     (`copies-supported` 1 to 99, all three `sides` values), saves them with
     the job (`job_<id>-<title>.json`, next to the PDF) and passes them on at
     release: `lp -n <copies> -o sides=... -o print-color-mode=...` for
     `LOCAL_PRINTER`, and IPP job attributes (or one stream per copy on an
     AppSocket printer) for `SERVER_PRINTER`.
   - **Jobs now wait instead of being dropped when the server is down.**
     `capture.py` checks the server and token every 5 seconds. While either
     fails, the printer reports "not accepting jobs" with a message such as
     "Waiting for the SecurePrint server", which shows in the computer's print
     queue, and answers job requests with `server-error-busy`. CUPS keeps the
     job and retries, and it is checked as soon as the server is back. The
     user gets one notification when jobs start waiting and one when the
     server is back. A job already captured when the server went away stays
     in the spool and is retried, and is given up (with a message) only after
     five failed uploads. Nothing is printed unchecked either way.
   - **Who printed it.** The account and computer from the print job, and the
     number of copies, are recorded in the audit trail ("Received payroll.pdf
     from the SecurePrint virtual printer (printed by vinu, 3 copies)"). A
     release by the capture is now audited as "released by the SecurePrint
     print capture to local printer ..." instead of "Web Analysis Mode".
   - **The spool is private.** The spool folder is `0700` and each captured
     file `0600`, because it holds the unmasked document until it is checked.
     The captured file is now uploaded straight from the spool, so a crash
     mid-upload leaves it there to be retried rather than in a work folder.
   - A job cancelled in the print queue before its data arrives is not saved.
   - The security alert shows the page count, copies and two-sided setting.

   - The watermark now names the document's own level. The default text was
     always "RESTRICTED", so turning the watermark on for Public pages
     stamped them "RESTRICTED".

   Tested with real CUPS 2.4 here (three-page payroll in order, two copies
   two-sided passed to a second CUPS printer, server stopped and restarted
   with a job waiting in the queue), plus 20 new automated tests. Then on the
   MacBook on 15 October 2026: all 138 tests pass; a three-page document came
   out as pages 1, 2, 3; the capture log showed copies=2, two-sided and the
   Mac user name; with the API stopped, a job waited in the macOS queue with
   "Waiting for the SecurePrint server" and was released 12 seconds after the
   API was started again; the audit log showed "printed by <mac user>,
   2 copies". After updating, run `bash apps/linux-agent/setup-printer-mac.sh`
   again so macOS recreates the printer with the new capabilities.
