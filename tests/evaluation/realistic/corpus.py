"""A realistic evaluation corpus for SecurePrint (proposal objective 14).

Unlike tests/evaluation/generate_dataset.py, whose fragments were written to
trigger exactly one rule each, these documents are written the way office
staff actually write them: varied labels ("NIC No.", "ID", "A/C"), varied
number formats (spaces, dashes, +94), tables, multi-page payroll sheets, and
plenty of harmless numbers that look sensitive (invoice and PO numbers, VAT
numbers, dates, serials, hotlines) plus everyday mentions of sensitive words
("reset your password", "salary review policy") that hold no actual secret.

Every sensitive value is annotated inline as {{category|value}}. The renderer
strips the markup and records each value, which gives value-level ground
truth for detection AND masking. Each document type also carries a
provisional classification assigned by the author from the meaning of the
levels in Table 3.1 (not from the risk weights). These are placeholders until
three human reviewers label the corpus (see calibrate_thresholds.py).

All personal data is synthetic. Card numbers are generated to pass the Luhn
check but are not real accounts.

Usage:
    python tests/evaluation/realistic/corpus.py            # main corpus (67 documents)
    python tests/evaluation/realistic/corpus.py holdout    # hold-out set (18 documents)
"""
from __future__ import annotations

import json
import random
import re
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF

REPO_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = REPO_ROOT / "tests" / "fixtures" / "realistic"

# Categories whose values must be masked when the user chooses "Mask and print".
# A classification marker ("CONFIDENTIAL" in a header) is a signal, not a value.
MASKABLE = {
    "nic", "card", "bank_account", "iban", "credential", "api_key",
    "passport", "salary", "employee_id", "email", "telephone",
}

MARK = re.compile(r"\{\{(\w+)\|(.+?)\}\}")

# --------------------------------------------------------------------------
# Synthetic people and values
# --------------------------------------------------------------------------

FIRST = ["Nimal", "Kumari", "Sunil", "Dilini", "Ruwan", "Tharushi", "Kasun", "Ishara", "Chamara", "Nadeesha",
         "Mohamed", "Fathima", "Arjun", "Priya", "Lahiru", "Sanduni", "Dinesh", "Hiruni", "Gayan", "Malsha"]
LAST = ["Perera", "Fernando", "Silva", "Jayawardena", "Bandara", "Wickramasinghe", "Rajapaksha", "Dissanayake",
        "Gunasekara", "Herath", "Rizvi", "Kumar", "Senanayake", "Wijesinghe", "Abeysekera"]
CITIES = ["Colombo 05", "Kandy", "Galle", "Nugegoda", "Kurunegala", "Negombo", "Matara", "Maharagama"]
BANKS = ["Commercial Bank", "Sampath Bank", "Bank of Ceylon", "People's Bank", "HNB", "NDB"]


class Faker:
    def __init__(self, seed: int) -> None:
        self.r = random.Random(seed)

    def name(self) -> str:
        return f"{self.r.choice(FIRST)} {self.r.choice(LAST)}"

    def email(self, name: str, domain: str = "lankatrade.lk") -> str:
        first, last = name.lower().split(" ", 1)
        style = self.r.choice(["{f}.{l}", "{f}{l}", "{f0}{l}", "{f}_{l}"])
        return style.format(f=first, l=last.replace(" ", ""), f0=first[0]) + "@" + domain

    def nic(self) -> str:
        year = self.r.randint(1965, 2003)
        day = self.r.randint(1, 365) + self.r.choice([0, 500])
        serial = self.r.randint(1000, 9999)
        if year < 2000 and self.r.random() < 0.5:
            return f"{year % 100:02d}{day:03d}{serial:04d}" + self.r.choice(["V", "V", "X", "v"])
        return f"{year}{day:03d}0{serial:04d}"

    def phone(self) -> str:
        n = f"7{self.r.choice([0, 1, 2, 5, 6, 7, 8])}{self.r.randint(1000000, 9999999)}"
        style = self.r.choice(["0{a} {b} {c}", "0{n}", "+94 {a} {b} {c}", "0{a}-{b}{c}", "+94{n}"])
        return style.format(n=n, a=n[:2], b=n[2:5], c=n[5:])

    def landline(self) -> str:
        n = f"11{self.r.randint(2000000, 2999999)}"
        return self.r.choice([f"0{n}", f"011 {n[2:5]} {n[5:]}", f"011-{n[2:]}"])

    def account(self) -> str:
        digits = "".join(str(self.r.randint(0, 9)) for _ in range(self.r.choice([10, 12, 12, 14])))
        style = self.r.choice(["plain", "plain", "groups"])
        if style == "groups":
            return " ".join(digits[i:i + 4] for i in range(0, len(digits), 4))
        return digits

    def card(self) -> str:
        kind = self.r.choice(["visa", "visa", "mc", "amex"])
        if kind == "visa":
            body = "4" + "".join(str(self.r.randint(0, 9)) for _ in range(14))
        elif kind == "mc":
            body = str(self.r.randint(51, 55)) + "".join(str(self.r.randint(0, 9)) for _ in range(13))
        else:
            body = self.r.choice(["34", "37"]) + "".join(str(self.r.randint(0, 9)) for _ in range(12))
        full = body + str(_luhn_check_digit(body))
        if kind == "amex":
            return f"{full[:4]} {full[4:10]} {full[10:]}"
        sep = self.r.choice([" ", "-", ""])
        return sep.join(full[i:i + 4] for i in range(0, 16, 4))

    def passport(self) -> str:
        return self.r.choice(["N", "N", "M"]) + str(self.r.randint(1000000, 9999999))

    def emp_id(self) -> str:
        n = self.r.randint(100, 99999)
        return self.r.choice([f"EMP-{n:05d}", f"EMP{n:04d}", f"STAFF-{n}", f"SL/{n:05d}", f"E{n:05d}"])

    def amount(self, lo: int, hi: int) -> str:
        v = self.r.randint(lo, hi) * 50
        cents = self.r.choice([0, 0, 25, 50, 75])
        return f"{v:,}.{cents:02d}" if self.r.random() < 0.6 else f"{v:,}"

    def password(self) -> str:
        words = ["Winter", "Kandy", "Lotus", "Monsoon", "Tiger", "Ceylon", "Galle", "Sigiriya"]
        return f"{self.r.choice(words)}{self.r.choice(['@', '#', '!', '_'])}{self.r.randint(10, 2030)}"

    def digits(self, n: int) -> str:
        return "".join(str(self.r.randint(0, 9)) for _ in range(n))


def _luhn_check_digit(body: str) -> int:
    total = 0
    for i, ch in enumerate(reversed(body)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - total % 10) % 10


def v(category: str, value: str) -> str:
    return "{{" + category + "|" + value + "}}"


# --------------------------------------------------------------------------
# Document model and rendering
# --------------------------------------------------------------------------

@dataclass
class Doc:
    doc_type: str
    title: str
    provisional_classification: str
    blocks: list = field(default_factory=list)  # ("h"|"p"|"kv"|"table"|"mono", payload)


def render(doc: Doc, path: Path) -> list[dict]:
    """Writes the PDF and returns the annotated values [{category, value, page}]."""
    pdf = fitz.open()
    page = pdf.new_page()
    annotations: list[dict] = []
    y = 60.0
    bottom = page.rect.height - 60

    def strip(text: str) -> str:
        def repl(m: re.Match) -> str:
            annotations.append({"category": m.group(1), "value": m.group(2), "page": pdf.page_count - 1})
            return m.group(2)
        return MARK.sub(repl, text)

    def need(height: float) -> None:
        nonlocal page, y
        if y + height > bottom:
            page = pdf.new_page()
            y = 60.0

    def line(text: str, x: float = 50, size: float = 10.5, font: str = "helv") -> None:
        nonlocal y
        need(size + 5)
        page.insert_text((x, y), strip(text), fontsize=size, fontname=font)
        y += size + 5

    for kind, payload in doc.blocks:
        if kind == "h":
            y += 4
            line(payload, size=14, font="hebo")
            y += 2
        elif kind == "p":
            # Wrap on the visible text, then re-attach markup: wrap per sentence
            # piece so annotations never get split across lines.
            pieces = re.split(r"(\{\{\w+\|.+?\}\})", payload)
            words: list[str] = []
            for piece in pieces:
                if MARK.fullmatch(piece):
                    words.append(piece)
                else:
                    words.extend(piece.split())
            current = ""
            for w in words:
                visible = MARK.sub(lambda m: m.group(2), current + " " + w)
                if len(visible) > 92 and current:
                    line(current)
                    current = w
                else:
                    current = (current + " " + w).strip()
            if current:
                line(current)
            y += 4
        elif kind == "kv":
            for label, value in payload:
                need(16)
                page.insert_text((50, y), strip(label), fontsize=10.5, fontname="hebo")
                page.insert_text((210, y), strip(value), fontsize=10.5, fontname="helv")
                y += 15.5
            y += 4
        elif kind == "table":
            header, rows, xs = payload
            need(18)
            for x, cell in zip(xs, header):
                page.insert_text((x, y), cell, fontsize=9, fontname="hebo")
            y += 14
            for row in rows:
                if y + 14 > bottom:
                    page = pdf.new_page()
                    y = 60.0
                    for x, cell in zip(xs, header):
                        page.insert_text((x, y), cell, fontsize=9, fontname="hebo")
                    y += 14
                for x, cell in zip(xs, row):
                    page.insert_text((x, y), strip(cell), fontsize=9, fontname="helv")
                y += 13
            y += 6
        elif kind == "newpage":
            page = pdf.new_page()
            y = 60.0
        elif kind == "mono":
            for text in payload.splitlines():
                line(text, size=9, font="cour")
            y += 4

    pdf.set_metadata({"title": doc.title, "creator": "SecurePrint realistic corpus"})
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.save(str(path))
    pdf.close()
    return annotations


# --------------------------------------------------------------------------
# Document types. Each takes a Faker and returns a Doc.
# --------------------------------------------------------------------------

def brochure(f: Faker) -> Doc:
    year = f.r.choice([2025, 2026])
    return Doc("marketing_brochure", "Lanka Trade Solutions - Services", "PUBLIC", [
        ("h", "Lanka Trade Solutions"),
        ("p", f"Since 1998 we have helped more than 1,200 small businesses across Sri Lanka manage stock, "
              f"invoicing and payroll. Our {year} packages start from Rs. 4,990 per month with no setup fee."),
        ("h", "Why choose us"),
        ("p", "Local support in Sinhala, Tamil and English. Cloud backups every night. Over 35 trained "
              "consultants in Colombo, Kandy and Galle. 98.7% of customers renew every year."),
        ("p", f"Call our hotline 1919 or {f.landline()}, or write to hello@lankatrade.lk. "
              "Visit us at No. 42, Galle Road, Colombo 03."),
    ])


def press_release(f: Faker) -> Doc:
    return Doc("press_release", "Press release", "PUBLIC", [
        ("h", "FOR IMMEDIATE RELEASE"),
        ("p", f"Colombo, {f.r.randint(1, 28)} March 2026 - Lanka Trade Solutions today announced the opening of "
              f"its fourth regional office in Kurunegala, creating {f.r.randint(20, 60)} new jobs. The company "
              f"reported revenue growth of {f.r.randint(8, 25)}% for the financial year 2025/26."),
        ("p", "Company registration PV 00012345. Listed on the CSE under ticker LTS.N0000."),
        ("p", f"Media contact: Corporate Communications, {f.landline()}, media@lankatrade.lk"),
    ])


def procedure(f: Faker) -> Doc:
    return Doc("internal_procedure", "IT procedure: workstation onboarding", "INTERNAL", [
        ("h", "Workstation onboarding procedure - INTERNAL USE ONLY"),
        ("p", "1. Collect the laptop from the IT store and record the asset tag (e.g. LTS-NB-0" + f.digits(3) + ") "
              "in the asset register."),
        ("p", "2. On first login the new staff member must change the temporary password. Passwords must be at "
              "least 12 characters and are rotated every 90 days under the password policy."),
        ("p", "3. Enrol the device in Intune and enable BitLocker. The recovery key is stored automatically in "
              "Entra ID; never write it down."),
        ("p", "4. Raise any issues on the service desk portal or call extension 2204."),
    ])


def minutes(f: Faker) -> Doc:
    chair, sec = f.name(), f.name()
    attendees = [f.name() for _ in range(4)]
    return Doc("meeting_minutes", "Minutes - operations meeting", "INTERNAL", [
        ("h", "Minutes of the Operations Committee meeting"),
        ("kv", [("Date", f"{f.r.randint(1, 28)}/0{f.r.randint(1, 9)}/2026"), ("Venue", "Board room, Level 4"),
                ("Chair", chair), ("Minutes", sec)]),
        ("p", "Present: " + ", ".join(attendees) + "."),
        ("p", f"1. Q3 delivery targets were reviewed. Dispatch volume rose to {f.r.randint(3000, 9000):,} "
              f"orders. PO 4500{f.digits(6)} to be closed by month end."),
        ("p", "2. The salary review policy will be discussed at the next HR committee; no figures were tabled."),
        ("p", f"3. Action: {attendees[0]} to circulate the revised roster to "
              f"{v('email', f.email(attendees[0]))} distribution list by Friday."),
    ])


def asset_list(f: Faker, with_wifi: bool) -> Doc:
    rows = []
    for _ in range(f.r.randint(6, 10)):
        mac = ":".join(f"{f.r.randint(0, 255):02X}" for _ in range(6))
        rows.append([f"LTS-NB-{f.digits(4)}", f.r.choice(["Dell Latitude 5440", "HP ProBook 450", "Lenovo T14"]),
                     f"SN{f.digits(10)}", mac, f.name()])
    blocks = [
        ("h", "IT asset handover register - Finance floor"),
        ("table", (["Asset tag", "Model", "Serial", "MAC address", "Assigned to"], rows, [50, 125, 240, 330, 445])),
    ]
    doc_class = "INTERNAL"
    if with_wifi:
        blocks.append(("kv", [("Guest Wi-Fi SSID", "LTS-Guest"),
                              ("Wi-Fi password", v("credential", f.password()))]))
        doc_class = "RESTRICTED"
    return Doc("it_asset_register", "IT asset register", doc_class, blocks)


def employee_record(f: Faker) -> Doc:
    name = f.name()
    label_nic = f.r.choice(["NIC No.", "National ID", "NIC", "Identity card no."])
    label_tel = f.r.choice(["Mobile", "Telephone", "Contact no.", "Phone"])
    return Doc("employee_record", "Employee personal record", "CONFIDENTIAL", [
        ("h", "Employee Personal Record"),
        ("kv", [("Full name", name),
                ("Employee no.", v("employee_id", f.emp_id())),
                (label_nic, v("nic", f.nic())),
                ("Date of birth", f"{f.r.randint(1, 28):02d}-{f.r.randint(1, 12):02d}-{f.r.randint(1970, 2002)}"),
                ("Address", f"No. {f.r.randint(3, 220)}, Temple Road, {f.r.choice(CITIES)}"),
                (label_tel, v("telephone", f.phone())),
                ("Personal email", v("email", f.email(name, f.r.choice(["gmail.com", "yahoo.com"])))),
                ("Emergency contact", f"{f.name()} ({v('telephone', f.phone())})"),
                ("Department", f.r.choice(["Finance", "Logistics", "Sales", "IT"])),
                ("Date joined", f"0{f.r.randint(1, 9)}/2021")]),
    ])


def payroll(f: Faker, people: int) -> Doc:
    rows = []
    for _ in range(people):
        rows.append([
            v("employee_id", f.emp_id()),
            f.name(),
            v("nic", f.nic()),
            f.r.choice(BANKS),
            v("bank_account", f.account()),
            v("salary", f.amount(1200, 9000)),
            v("salary", f.amount(1000, 7500)),
        ])
    month = f.r.choice(["July", "August", "September"])
    return Doc("payroll_sheet", f"Payroll {month} 2026", "RESTRICTED", [
        ("h", f"Payroll register - {month} 2026"),
        ("p", "Prepared by Finance. Bank transfer file to be uploaded by the 25th."),
        ("table", (["Emp no.", "Name", "NIC", "Bank", "Account no.", "Gross pay", "Net pay"],
                   rows, [40, 100, 200, 285, 360, 455, 520])),
        ("p", f"Total employees: {people}. Approved by the Finance Manager."),
    ])


def increment_letter(f: Faker) -> Doc:
    name = f.name()
    old = f.amount(1500, 4000)
    new = f.amount(4100, 6000)
    return Doc("salary_letter", "Salary revision letter", "CONFIDENTIAL", [
        ("h", "PRIVATE AND CONFIDENTIAL"),
        ("p", f"Dear {name},"),
        ("p", f"Employee number: {v('employee_id', f.emp_id())}"),
        ("p", f"Following your annual performance review we are pleased to confirm that your basic salary "
              f"will be revised from Rs. {v('salary', old)} to Rs. {v('salary', new)} per month with effect "
              f"from 1 October 2026. All other terms of employment remain unchanged."),
        ("p", "Yours sincerely,"),
        ("p", f"{f.name()}, Head of Human Resources"),
    ])


def credential_sheet(f: Faker) -> Doc:
    systems = [("Core ERP (admin)", "erpadmin"), ("Payroll server", "pay_svc"), ("Firewall", "fwadmin"),
               ("Backup NAS", "backup"), ("Office 365 break-glass", "bg-admin@lankatrade.lk")]
    rows = [[s, u, v("credential", f.password()), f"10.10.{f.r.randint(1, 30)}.{f.r.randint(2, 250)}"]
            for s, u in f.r.sample(systems, 4)]
    return Doc("credential_list", "Server access handover", "RESTRICTED", [
        ("h", "System access handover - do not distribute"),
        ("p", "Handed over to the incoming IT administrator. Change every password within 24 hours."),
        ("table", (["System", "Username", "Password", "Host"], rows, [50, 200, 320, 450])),
    ])


def customer_list(f: Faker, with_nic: bool) -> Doc:
    rows = []
    for _ in range(f.r.randint(8, 14)):
        name = f.name()
        row = [f"C{f.digits(5)}", name, v("telephone", f.phone()), v("email", f.email(name, "gmail.com"))]
        if with_nic:
            row.append(v("nic", f.nic()))
        rows.append(row)
    header = ["Cust. ID", "Name", "Phone", "Email"] + (["NIC"] if with_nic else [])
    xs = [40, 95, 195, 300] + ([470] if with_nic else [])
    return Doc("customer_list", "Customer contact list", "CONFIDENTIAL", [
        ("h", "Loyalty programme - customer contact list"),
        ("table", (header, rows, xs)),
        ("p", f"Exported from CRM on {f.r.randint(1, 28)}/09/2026 for the outbound call campaign."),
    ])


def supplier_contract(f: Faker) -> Doc:
    return Doc("supplier_contract", "Supply agreement", "CONFIDENTIAL", [
        ("h", "CONFIDENTIAL - Supply Agreement"),
        ("p", f"This agreement is made on {f.r.randint(1, 28)} June 2026 between Lanka Trade Solutions (Pvt) Ltd "
              f"(PV 00012345) and Ceylon Packaging (Pvt) Ltd (VAT reg. 1{f.digits(8)}-7000)."),
        ("p", f"1. The supplier shall deliver {f.r.randint(10, 90)},000 units per quarter at Rs. "
              f"{f.r.randint(20, 90)}.50 per unit, invoiced monthly."),
        ("p", "2. Payment within 45 days of invoice to the supplier's account below."),
        ("kv", [("Bank", f.r.choice(BANKS)), ("Account name", "Ceylon Packaging (Pvt) Ltd"),
                ("Account number", v("bank_account", f.account())), ("Branch code", f.digits(3))]),
        ("p", "3. Pricing in this agreement is confidential and must not be disclosed to third parties."),
    ])


def invoice(f: Faker) -> Doc:
    return Doc("invoice", "Tax invoice", "INTERNAL", [
        ("h", "TAX INVOICE"),
        ("kv", [("Invoice no.", f"INV-2026-{f.digits(6)}"), ("PO no.", f"4500{f.digits(8)}"),
                ("Date", f"{f.r.randint(1, 28)}/08/2026"), ("VAT reg.", f"1{f.digits(8)}-7000")]),
        ("table", (["Item", "Qty", "Unit price", "Amount"],
                   [["A4 copy paper (ream)", "120", "1,450.00", "174,000.00"],
                    ["Toner cartridge 26A", "8", "18,900.00", "151,200.00"],
                    ["Delivery", "1", "2,500.00", "2,500.00"]], [50, 280, 350, 450])),
        ("p", f"Total due: Rs. 327,700.00 within 30 days. Please remit to {f.r.choice(BANKS)}, "
              f"A/C {v('bank_account', f.account())}. Queries: accounts@ceylonpack.lk or {f.landline()}."),
    ])


def cv(f: Faker) -> Doc:
    name = f.name()
    return Doc("job_application", "Curriculum vitae", "CONFIDENTIAL", [
        ("h", name),
        ("p", f"{v('telephone', f.phone())}  |  {v('email', f.email(name, 'gmail.com'))}  |  "
              f"No. {f.r.randint(5, 150)}, Lake Road, {f.r.choice(CITIES)}"),
        ("p", f"NIC: {v('nic', f.nic())}   Date of birth: {f.r.randint(1, 28)}/{f.r.randint(1, 12)}/"
              f"{f.r.randint(1988, 2001)}   Marital status: Single"),
        ("h", "Experience"),
        ("p", f"Accounts Executive, Ceylon Packaging (2021 - present). Managed a ledger of 400+ suppliers and "
              f"reduced month-end close from 9 to 5 days."),
        ("h", "Education"),
        ("p", "BSc (Hons) Accounting and Finance, University of Sri Jayewardenepura, Second Class Upper."),
        ("p", f"Expected salary: Rs. {v('salary', f.amount(2000, 3500))} per month."),
    ])


def card_form(f: Faker) -> Doc:
    name = f.name()
    return Doc("card_authorisation", "Card payment authorisation", "RESTRICTED", [
        ("h", "Credit card payment authorisation form"),
        ("p", "I authorise Lanka Trade Solutions to charge the card below for the annual subscription."),
        ("kv", [("Cardholder name", name), ("Card number", v("card", f.card())),
                ("Expiry", f"{f.r.randint(1, 12):02d}/{f.r.randint(27, 31)}"),
                ("CVV", v("card", f.digits(3))), ("Amount", "Rs. 59,880.00"),
                ("Contact", v("telephone", f.phone()))]),
        ("p", "Signature: ______________________   Date: ____/____/2026"),
    ])


def travel_request(f: Faker) -> Doc:
    name = f.name()
    return Doc("travel_request", "Overseas travel request", "CONFIDENTIAL", [
        ("h", "Overseas travel request"),
        ("kv", [("Traveller", name), ("Employee ID", v("employee_id", f.emp_id())),
                ("Passport number", v("passport", f.passport())),
                ("Passport expiry", f"{f.r.randint(1, 28)}/{f.r.randint(1, 12)}/20{f.r.randint(27, 34)}"),
                ("Destination", f.r.choice(["Singapore", "Dubai", "Chennai", "Kuala Lumpur"])),
                ("Dates", f"{f.r.randint(1, 10)}-{f.r.randint(11, 20)} November 2026"),
                ("Flight", f"UL {f.r.randint(100, 899)}"),
                ("Mobile while abroad", v("telephone", f.phone()))]),
        ("p", "Per diem as per the travel policy. Approved by the department head."),
    ])


def config_printout(f: Faker) -> Doc:
    gh = "ghp_" + "".join(f.r.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789") for _ in range(36))
    stripe = "sk_live_" + "".join(f.r.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(24))
    db_pw = f.password()
    return Doc("config_printout", "Deployment notes", "RESTRICTED", [
        ("h", "Deployment notes - billing service"),
        ("p", "Production environment file as deployed on 12 September. Keep with the change record."),
        ("mono", "\n".join([
            "APP_ENV=production",
            "DB_HOST=10.20.4.15",
            "DB_USER=billing_app",
            f"DB_PASSWORD={v('credential', db_pw)}",
            f"STRIPE_SECRET_KEY={v('api_key', stripe)}",
            f"GITHUB_TOKEN={v('api_key', gh)}",
            "LOG_LEVEL=info",
        ])),
        ("p", "Rollback: redeploy tag v2.14.3 from the release pipeline."),
    ])


def leave_form(f: Faker) -> Doc:
    name = f.name()
    return Doc("leave_application", "Leave application", "INTERNAL", [
        ("h", "Leave application"),
        ("kv", [("Name", name), ("Emp. no.", v("employee_id", f.emp_id())),
                ("Leave type", f.r.choice(["Annual", "Casual", "Medical"])),
                ("From / to", f"{f.r.randint(1, 14)}/10/2026 - {f.r.randint(15, 28)}/10/2026"),
                ("Contactable on", v("telephone", f.phone())),
                ("Covering officer", f.name())]),
        ("p", "Handover notes attached. Recommended by supervisor."),
    ])


def bank_transfer(f: Faker) -> Doc:
    iban = "GB" + f.digits(2) + "BARC" + f.digits(14)
    return Doc("bank_transfer", "Payment instruction", "RESTRICTED", [
        ("h", "Payment instruction to bank"),
        ("p", f"Please debit our current account no. {v('bank_account', f.account())} and remit USD 18,450.00 "
              "to the beneficiary below in settlement of invoice EX-2026-0331."),
        ("kv", [("Beneficiary", "Northbridge Components Ltd, Leeds, UK"),
                ("IBAN", v("iban", iban)), ("SWIFT", "BARCGB22"),
                ("Purpose", "Import of spare parts")]),
        ("p", "Authorised signatories: Director and Finance Manager."),
    ])


def newsletter(f: Faker) -> Doc:
    return Doc("staff_newsletter", "Staff newsletter", "INTERNAL", [
        ("h", "The Lanka Trade Monthly - October 2026"),
        ("p", f"Congratulations to the Galle branch for hitting {f.r.randint(105, 130)}% of target. The annual "
              f"sports meet will be held on {f.r.randint(1, 28)} November at the Sugathadasa stadium."),
        ("p", "Reminder: never share your password with anyone, including IT staff. IT will never ask for it."),
        ("p", "The new canteen menu starts on Monday. Vegetarian options are available every day."),
    ])


# --------------------------------------------------------------------------
# Hold-out document types. Written after the first evaluation run and used
# only to measure; the rules were not adjusted against them.
# --------------------------------------------------------------------------

def loan_application(f: Faker) -> Doc:
    name = f.name()
    return Doc("loan_application", "Staff loan application", "CONFIDENTIAL", [
        ("h", "Staff Welfare Loan - Application"),
        ("p", f"I, {name}, holder of national identity card {v('nic', f.nic())}, apply for a staff loan of "
              f"Rs. 350,000 repayable over 24 months by deduction from my salary."),
        ("kv", [("Designation", f.r.choice(["Senior Executive", "Store Keeper", "Accountant"])),
                ("Present monthly salary", v("salary", "Rs. " + f.amount(1500, 5000))),
                ("Salary account", v("bank_account", f.account()) + f" ({f.r.choice(BANKS)})"),
                ("Mobile", v("telephone", f.phone()))]),
        ("p", f"Guarantor: {f.name()}, NIC {v('nic', f.nic())}."),
    ])


def disciplinary_letter(f: Faker) -> Doc:
    name = f.name()
    return Doc("hr_letter", "Show cause letter", "CONFIDENTIAL", [
        ("h", "STRICTLY PRIVATE"),
        ("p", f"To: {name}   Employee number {v('employee_id', f.emp_id())}"),
        ("p", f"Ref: HR/DISC/2026/{f.digits(3)}   Date: {f.r.randint(1, 28)} September 2026"),
        ("p", "It has been reported that on three occasions in August you left the stores unattended during "
              "working hours. You are required to show cause in writing within seven days why disciplinary "
              "action should not be taken against you."),
        ("p", "Manager - Human Resources"),
    ])


def vendor_form(f: Faker) -> Doc:
    contact = f.name()
    return Doc("vendor_registration", "Vendor registration form", "CONFIDENTIAL", [
        ("h", "New vendor registration"),
        ("table", (["Field", "Details"], [
            ["Company name", "Island Office Supplies (Pvt) Ltd"],
            ["Business reg. no.", f"PV {f.digits(6)}"],
            ["Contact person", contact],
            ["Contact number", v("telephone", f.phone())],
            ["Email", v("email", f.email(contact, "islandoffice.lk"))],
            ["Bank and branch", f"{f.r.choice(BANKS)}, {f.r.choice(CITIES)}"],
            ["Account number", v("bank_account", f.account())],
        ], [50, 220])),
        ("p", "Attach a copy of the business registration and a cancelled cheque."),
    ])


def vpn_email(f: Faker) -> Doc:
    name = f.name()
    user = name.lower().replace(" ", ".")
    return Doc("account_setup_email", "Your remote access account", "RESTRICTED", [
        ("p", f"From: IT Service Desk   To: {v('email', f.email(name))}"),
        ("p", "Subject: Your VPN account is ready"),
        ("p", f"Hi {name.split()[0]}, your remote access account has been created."),
        ("kv", [("Username", user), ("Temporary password", v("credential", f.password())),
                ("Server", "vpn.lankatrade.lk")]),
        ("p", "You will be asked to set a new password the first time you connect. Do not forward this email."),
    ])


def insurance_claim(f: Faker) -> Doc:
    name = f.name()
    return Doc("insurance_claim", "Medical claim form", "CONFIDENTIAL", [
        ("h", "Group medical insurance - claim form"),
        ("kv", [("Policy no.", f"GMI/{f.digits(4)}/2026"), ("Member name", name),
                ("Member NIC", v("nic", f.nic())), ("Staff ID", v("employee_id", f.emp_id())),
                ("Hospital", "Asiri Central, Colombo 10"), ("Claim amount", "Rs. 84,600.00"),
                ("Reimburse to a/c", v("bank_account", f.account())), ("Phone", v("telephone", f.phone()))]),
        ("p", "Diagnosis and bills attached. I declare the above information is true and correct."),
    ])


def event_flyer(f: Faker) -> Doc:
    return Doc("event_flyer", "Blood donation campaign", "PUBLIC", [
        ("h", "Blood Donation Campaign 2026"),
        ("p", f"Join us on {f.r.randint(1, 28)} November from 8.30 am to 2.00 pm at the Lanka Trade head office, "
              f"No. 42, Galle Road, Colombo 03, in partnership with the National Blood Centre."),
        ("p", f"Last year 214 donors took part. Register at the reception or call {f.landline()}. "
              "Light refreshments will be provided."),
    ])


HOLDOUT_PLAN = [(loan_application, 3), (disciplinary_letter, 3), (vendor_form, 3), (vpn_email, 3),
                (insurance_claim, 3), (event_flyer, 3)]


# --------------------------------------------------------------------------
# Build the corpus
# --------------------------------------------------------------------------

MAIN_PLAN = [
    (brochure, 4), (press_release, 3), (procedure, 3), (minutes, 4), (newsletter, 3),
    (lambda f: asset_list(f, False), 2), (lambda f: asset_list(f, True), 2),
    (employee_record, 5), (lambda f: payroll(f, f.r.randint(8, 15)), 4), (increment_letter, 4),
    (credential_sheet, 3), (lambda f: customer_list(f, False), 2), (lambda f: customer_list(f, True), 2),
    (supplier_contract, 3), (invoice, 4), (cv, 4), (card_form, 3), (travel_request, 3),
    (config_printout, 3), (leave_form, 3), (bank_transfer, 3),
]

CORPORA = {
    "main": (MAIN_PLAN, 20260, OUTPUT_DIR),
    "holdout": (HOLDOUT_PLAN, 90210, REPO_ROOT / "tests" / "fixtures" / "realistic-holdout"),
}


def build(plan, seed: int) -> list[tuple[str, Doc]]:
    docs: list[tuple[str, Doc]] = []
    for maker, count in plan:
        for _ in range(count):
            seed += 1
            doc = maker(Faker(seed))
            docs.append((f"{len(docs) + 1:03d}_{doc.doc_type}.pdf", doc))
    return docs


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "main"
    plan, seed, out_dir = CORPORA[name]
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.pdf"):
        old.unlink()
    manifest = []
    for filename, doc in build(plan, seed):
        values = render(doc, out_dir / filename)
        manifest.append({
            "filename": filename,
            "doc_type": doc.doc_type,
            "title": doc.title,
            "provisional_classification": doc.provisional_classification,
            "expected_categories": sorted({a["category"] for a in values}),
            "values": values,
        })
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    counts: dict[str, int] = {}
    for m in manifest:
        counts[m["provisional_classification"]] = counts.get(m["provisional_classification"], 0) + 1
    print(f"Wrote {len(manifest)} documents to {out_dir}")
    print("Provisional labels: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    print(f"Annotated sensitive values: {sum(len(m['values']) for m in manifest)}")


if __name__ == "__main__":
    sys.exit(main())
