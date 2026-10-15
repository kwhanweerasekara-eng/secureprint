"""The printer receiver used by the macOS/Ubuntu print capture
(apps/linux-agent/ipp_receiver.py), driven with the same IPP encoder the
server uses to talk to real printers."""
import json
import socket
import sys
from pathlib import Path

import fitz
import pytest
import requests

from apps.api.services import printing

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "linux-agent"))
import ipp_receiver  # noqa: E402


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def receiver(tmp_path):
    r = ipp_receiver.Receiver(tmp_path, free_port())
    r.start()
    yield r
    r.stop()


def post(receiver, body: bytes) -> dict:
    resp = requests.post(f"http://127.0.0.1:{receiver.port}/ipp/print", data=body,
                         headers={"Content-Type": "application/ipp"}, timeout=5)
    assert resp.status_code == 200
    return printing._parse_response(resp.content)


def a_pdf() -> bytes:
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Basic salary: Rs. 285,000")
    return doc.tobytes()


def test_printer_advertises_pdf_so_cups_sends_pdf(receiver):
    uri = f"ipp://127.0.0.1:{receiver.port}/ipp/print"  # answers with the address it was reached on
    parsed = post(receiver, printing._build_request(printing.OP_GET_PRINTER_ATTRIBUTES, uri))
    assert parsed["status_code"] == 0
    assert parsed["attributes"]["document-format-supported"] == [b"application/pdf"]
    assert parsed["attributes"]["printer-uri-supported"] == [uri.encode()]


def test_print_job_lands_in_the_spool_folder_with_its_title(receiver, tmp_path):
    uri = f"ipp://localhost:{receiver.port}/ipp/print"
    pdf = a_pdf()
    parsed = post(receiver, printing._build_print_job(uri, "Salary letter.docx") + pdf)
    assert parsed["status_code"] == 0
    files = list(tmp_path.glob("*.pdf"))
    assert len(files) == 1 and files[0].name.endswith("-Salary letter.pdf")
    assert files[0].read_bytes() == pdf
    assert not list(tmp_path.glob("*.part"))


def test_a_job_that_is_not_pdf_is_refused_and_not_saved(receiver, tmp_path):
    uri = f"ipp://localhost:{receiver.port}/ipp/print"
    parsed = post(receiver, printing._build_print_job(uri, "x", "application/postscript") + b"%!PS-Adobe-3.0\n")
    assert parsed["status_code"] == ipp_receiver.FORMAT_NOT_SUPPORTED
    assert not list(tmp_path.iterdir())


def test_title_is_made_safe_for_a_file_name():
    assert ipp_receiver.safe_title("../../etc/passwd") == "etc_passwd"
    assert ipp_receiver.safe_title("Q3 report.pdf") == "Q3 report"
    assert ipp_receiver.safe_title("") == "document"


def _job_request(op: int, uri: str, attrs: bytes = b"") -> bytes:
    return printing._build_request(op, uri, attrs)


def _job_attrs(name: str, copies: int = 1, sides: str = "one-sided") -> bytes:
    a = printing._pack_attr(printing.TAG_NAME_WITHOUT_LANGUAGE, "job-name", name.encode())
    a += bytes([printing.JOB_ATTRIBUTES_TAG])
    a += printing._pack_attr(printing.TAG_INTEGER, "copies", copies.to_bytes(4, "big"))
    a += printing._pack_attr(printing.TAG_KEYWORD, "sides", sides.encode())
    return a


def test_printer_is_face_down_so_cups_keeps_page_order(receiver):
    # With face-up, CUPS reverses the pages so a paper stack comes out right,
    # and the released PDF would be backwards.
    uri = f"ipp://127.0.0.1:{receiver.port}/ipp/print"
    attrs = post(receiver, printing._build_request(printing.OP_GET_PRINTER_ATTRIBUTES, uri))["attributes"]
    assert attrs["output-bin-default"] == [b"face-down"]
    assert attrs["output-bin-supported"] == [b"face-down"]


def test_printer_takes_copies_and_two_sided_itself(receiver):
    # Otherwise CUPS repeats pages for copies and pads with blank pages for
    # two-sided before the document reaches SecurePrint.
    uri = f"ipp://127.0.0.1:{receiver.port}/ipp/print"
    attrs = post(receiver, printing._build_request(printing.OP_GET_PRINTER_ATTRIBUTES, uri))["attributes"]
    low, high = attrs["copies-supported"][0][:4], attrs["copies-supported"][0][4:]
    assert int.from_bytes(low, "big") == 1 and int.from_bytes(high, "big") >= 10
    assert set(attrs["sides-supported"]) >= {b"one-sided", b"two-sided-long-edge"}


def test_print_settings_and_user_are_saved_next_to_the_pdf(receiver, tmp_path):
    uri = f"ipp://localhost:{receiver.port}/ipp/print"
    created = post(receiver, _job_request(0x0005, uri, _job_attrs("Payroll.xlsx", copies=3, sides="two-sided-long-edge")))
    assert created["status_code"] == 0
    job_id = created["attributes"]["job-id"][0]
    send = printing._pack_attr(printing.TAG_INTEGER, "job-id", job_id)
    send += printing._pack_attr(0x22, "last-document", b"\x01")
    assert post(receiver, _job_request(0x0006, uri, send) + a_pdf())["status_code"] == 0

    pdf = next(tmp_path.glob("*.pdf"))
    settings = json.loads(pdf.with_suffix(".json").read_text())
    assert settings["copies"] == 3
    assert settings["sides"] == "two-sided-long-edge"
    assert settings["user"] == printing.REQUESTING_USER  # the account that printed
    # Both files hold or describe an unmasked document: owner only.
    assert pdf.stat().st_mode & 0o077 == 0
    assert pdf.with_suffix(".json").stat().st_mode & 0o077 == 0


def test_jobs_wait_in_the_print_queue_while_the_server_is_down(tmp_path):
    problem = {"text": "Waiting for the SecurePrint server"}
    r = ipp_receiver.Receiver(tmp_path, free_port(), gate=lambda: problem["text"])
    r.start()
    try:
        uri = f"ipp://127.0.0.1:{r.port}/ipp/print"
        attrs = post(r, printing._build_request(printing.OP_GET_PRINTER_ATTRIBUTES, uri))["attributes"]
        assert attrs["printer-is-accepting-jobs"] == [b"\x00"]
        assert attrs["printer-state-message"] == [b"Waiting for the SecurePrint server"]
        # CUPS retries a busy printer later and keeps the job meanwhile.
        refused = post(r, printing._build_print_job(uri, "Salary letter") + a_pdf())
        assert refused["status_code"] == ipp_receiver.BUSY
        assert not list(tmp_path.iterdir())

        problem["text"] = None
        assert post(r, printing._build_print_job(uri, "Salary letter") + a_pdf())["status_code"] == 0
        assert len(list(tmp_path.glob("*.pdf"))) == 1
    finally:
        r.stop()


def test_a_job_cancelled_before_its_document_arrives_is_not_saved(receiver, tmp_path):
    uri = f"ipp://localhost:{receiver.port}/ipp/print"
    job_id = post(receiver, _job_request(0x0005, uri, _job_attrs("x")))["attributes"]["job-id"][0]
    ref = printing._pack_attr(printing.TAG_INTEGER, "job-id", job_id)
    assert post(receiver, _job_request(0x0008, uri, ref))["status_code"] == 0
    late = post(receiver, _job_request(0x0006, uri, ref + printing._pack_attr(0x22, "last-document", b"\x01")) + a_pdf())
    assert late["status_code"] == ipp_receiver.NOT_FOUND
    assert not list(tmp_path.iterdir())
