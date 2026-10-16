"""Compliance report: a one-click PDF summary of print activity for a date range,
the evidence a manager would show that personal data on paper is controlled.

It reports counts, categories and outcomes only, never a detected value.
"""
from __future__ import annotations

import html
import io
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import fitz  # PyMuPDF
from sqlalchemy.orm import Session

from apps.api.models.detection import DetectionSummary
from apps.api.models.enums import JobAction, JobStatus
from apps.api.models.print_job import PrintJob
from apps.api.models.user import User

LEVELS = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]

CATEGORY_LABELS = {
    "nic": "National identity numbers",
    "bank_account": "Bank account numbers",
    "iban": "IBANs",
    "card": "Payment card numbers",
    "credential": "Passwords and credentials",
    "api_key": "API keys and secrets",
    "passport": "Passport numbers",
    "salary": "Salary information",
    "employee_id": "Employee IDs",
    "email": "Email addresses",
    "telephone": "Telephone numbers",
    "classification_marker": "Classification markers",
    "health": "Health information",
}


@dataclass
class ReportData:
    date_from: date
    date_to: date
    organisation: str
    total: int = 0
    by_level: dict[str, int] = field(default_factory=dict)
    masked: int = 0
    released: int = 0
    cancelled: int = 0
    blocked: int = 0
    waiting: int = 0
    categories: list[tuple[str, int, int]] = field(default_factory=list)  # (category, documents, values)
    per_user: list[tuple[str, int, int, int, int]] = field(default_factory=list)  # (user, jobs, restricted, masked, cancelled)
    recent_restricted: list[tuple[str, str, str, str, str]] = field(default_factory=list)  # (when, job, file, user, outcome)


def _outcome(job: PrintJob) -> str:
    if job.status == JobStatus.BLOCKED:
        return "Blocked"
    if job.status == JobStatus.CANCELLED:
        return "Cancelled"
    if job.status == JobStatus.AWAITING_DECISION:
        return "Waiting for decision"
    if job.action == JobAction.MASK_AND_PRINT:
        return "Masked and printed"
    if job.status in (JobStatus.COMPLETED, JobStatus.READY, JobStatus.PRINTING):
        return "Printed"
    return job.status.value.replace("_", " ").capitalize()


def collect(db: Session, date_from: date, date_to: date, organisation: str) -> ReportData:
    start = datetime.combine(date_from, datetime.min.time())
    end = datetime.combine(date_to + timedelta(days=1), datetime.min.time())
    jobs = (
        db.query(PrintJob)
        .filter(PrintJob.created_at >= start, PrintJob.created_at < end)
        .order_by(PrintJob.created_at.desc())
        .all()
    )
    users = {u.id: u.username for u in db.query(User).all()}
    data = ReportData(date_from=date_from, date_to=date_to, organisation=organisation, total=len(jobs))

    levels = Counter(j.classification.value if j.classification else "NOT CLASSIFIED" for j in jobs)
    data.by_level = {lvl: levels.get(lvl, 0) for lvl in LEVELS}
    if levels.get("NOT CLASSIFIED"):
        data.by_level["NOT CLASSIFIED"] = levels["NOT CLASSIFIED"]

    data.masked = sum(1 for j in jobs if j.action == JobAction.MASK_AND_PRINT and j.status not in (JobStatus.CANCELLED, JobStatus.BLOCKED))
    data.released = sum(1 for j in jobs if j.status == JobStatus.COMPLETED)
    data.cancelled = sum(1 for j in jobs if j.status == JobStatus.CANCELLED)
    data.blocked = sum(1 for j in jobs if j.status in (JobStatus.BLOCKED, JobStatus.FAILED))
    data.waiting = sum(1 for j in jobs if j.status == JobStatus.AWAITING_DECISION)

    job_ids = [j.id for j in jobs]
    docs: Counter[str] = Counter()
    values: Counter[str] = Counter()
    if job_ids:
        for d in db.query(DetectionSummary).filter(DetectionSummary.job_id.in_(job_ids)).all():
            if d.count > 0:
                docs[d.category] += 1
                values[d.category] += d.count
    data.categories = sorted(((c, docs[c], values[c]) for c in docs), key=lambda r: (-r[1], -r[2]))[:8]

    per_user: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for j in jobs:
        row = per_user[users.get(j.user_id, "unknown")]
        row[0] += 1
        row[1] += j.classification is not None and j.classification.value == "RESTRICTED"
        row[2] += j.action == JobAction.MASK_AND_PRINT and j.status not in (JobStatus.CANCELLED, JobStatus.BLOCKED)
        row[3] += j.status == JobStatus.CANCELLED
    data.per_user = sorted(((u, *r) for u, r in per_user.items()), key=lambda r: -r[1])

    restricted = [j for j in jobs if j.classification is not None and j.classification.value == "RESTRICTED"][:15]
    data.recent_restricted = [
        (j.created_at.strftime("%d %b %Y %H:%M"), j.id, j.original_filename, users.get(j.user_id, "unknown"), _outcome(j))
        for j in restricted
    ]
    return data


CSS = """
* { font-family: sans-serif; color: #000; }
body { font-size: 10pt; }
h1 { font-size: 18pt; margin: 0 0 4pt 0; }
h2 { font-size: 12pt; margin: 16pt 0 6pt 0; border-bottom: 1px solid #000; padding-bottom: 2pt; }
p { margin: 0 0 4pt 0; }
.muted { color: #444; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #000; padding: 3pt 5pt; text-align: left; }
th { font-weight: bold; }
td.n, th.n { text-align: right; }
"""


def _table(headers: list[str], rows: list[list], numeric: set[int]) -> str:
    def cell(tag: str, i: int, v) -> str:
        cls = ' class="n"' if i in numeric else ""
        return f"<{tag}{cls}>{html.escape(str(v))}</{tag}>"

    head = "".join(cell("th", i, h) for i, h in enumerate(headers))
    body = "".join("<tr>" + "".join(cell("td", i, v) for i, v in enumerate(r)) + "</tr>" for r in rows)
    return f'<table cellspacing="0" cellpadding="0" width="100%" style="width: 100%"><tr>{head}</tr>{body}</table>'


def render_pdf(data: ReportData, generated_at: datetime | None = None) -> bytes:
    generated_at = generated_at or datetime.utcnow()
    period = f"{data.date_from.strftime('%d %b %Y')} to {data.date_to.strftime('%d %b %Y')}"
    parts = [
        "<h1>SecurePrint Compliance Report</h1>",
        f"<p>{html.escape(data.organisation)}</p>",
        f"<p class='muted'>Period: {period}. Generated {generated_at.strftime('%d %b %Y %H:%M')} UTC.</p>",
        "<p class='muted'>This report lists counts, categories and outcomes only. It contains no detected values.</p>",
        "<h2>Summary</h2>",
        _table(
            ["Measure", "Count"],
            [
                ["Documents checked", data.total],
                ["Masked before printing", data.masked],
                ["Printed and released", data.released],
                ["Cancelled by the user at the alert", data.cancelled],
                ["Blocked by SecurePrint", data.blocked],
                ["Waiting for a decision", data.waiting],
            ],
            {1},
        ),
        "<h2>Documents by classification level</h2>",
        _table(
            ["Level", "Documents", "Share"],
            [[lvl, n, f"{(100 * n / data.total):.0f}%" if data.total else "0%"] for lvl, n in data.by_level.items()],
            {1, 2},
        ),
        "<h2>Most common sensitive data</h2>",
        _table(
            ["Kind of data", "Documents", "Values masked or found"],
            [[CATEGORY_LABELS.get(c, c), d, v] for c, d, v in data.categories] or [["None found", 0, 0]],
            {1, 2},
        ),
        "<h2>Print jobs per user</h2>",
        _table(
            ["User", "Jobs", "Restricted", "Masked", "Cancelled"],
            [list(r) for r in data.per_user] or [["No print jobs", 0, 0, 0, 0]],
            {1, 2, 3, 4},
        ),
        "<h2>Recent restricted documents</h2>",
        _table(
            ["When (UTC)", "Job", "Document", "User", "Outcome"],
            [list(r) for r in data.recent_restricted] or [["None", "", "", "", ""]],
            set(),
        ),
    ]
    story = fitz.Story(html="".join(parts), user_css=CSS)
    buf = io.BytesIO()
    writer = fitz.DocumentWriter(buf)
    page = fitz.paper_rect("a4")
    area = page + (50, 50, -50, -60)
    more = True
    while more:
        device = writer.begin_page(page)
        more, _ = story.place(area)
        story.draw(device)
        writer.end_page()
    writer.close()

    # Page numbers and a footer line on every page.
    doc = fitz.open("pdf", buf.getvalue())
    for i, p in enumerate(doc, start=1):
        p.insert_text((50, page.height - 30), f"SecurePrint Compliance Report. {period}. Page {i} of {doc.page_count}.", fontsize=8, fontname="helv")
    out = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return out
