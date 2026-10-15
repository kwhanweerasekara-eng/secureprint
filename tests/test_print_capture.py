"""The macOS/Ubuntu print capture (apps/linux-agent/capture.py) with the
server replaced by a stub, so each failure can be produced on demand."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "linux-agent"))
import capture  # noqa: E402


class StubApi:
    """Answers like the SecurePrint API, or fails the way it is told to."""

    def __init__(self):
        self.fail_with: capture.ApiError | None = None
        self.uploads: list[tuple[str, dict]] = []
        self.posts: list[tuple[str, dict | None]] = []
        self.job = {"id": "SP-1", "status": "READY", "classification": "PUBLIC", "risk_score": 0,
                    "original_filename": "rota.pdf", "page_count": 1, "detections": []}

    def upload(self, pdf, name, settings):
        if self.fail_with:
            raise self.fail_with
        self.uploads.append((name, settings))
        return {"id": self.job["id"]}

    def json(self, method, path, payload=None, timeout=90):
        if self.fail_with:
            raise self.fail_with
        if method == "POST":
            self.posts.append((path, payload))
        return self.job if path.startswith("/api/v1/jobs/") else {}

    def download(self, job_id, out):
        out.write_bytes(b"%PDF-1.4 masked")


class Notes(capture.Ui):
    def __init__(self):
        super().__init__("mask")
        self.notices: list[str] = []
        self.problems: list[str] = []

    def notify(self, message):
        self.notices.append(message)

    def problem(self, title, message):
        self.problems.append(message)


@pytest.fixture
def make(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "WORK_DIR", tmp_path / "work")

    def _make(**cfg):
        ui = Notes()
        c = capture.Capture({"SERVER_URL": "http://localhost:1", "API_TOKEN": "t", "IPP_PORT": "",
                             "SPOOL_DIR": str(tmp_path / "spool"), **cfg}, ui)
        c.api = c.watch.api = StubApi()
        return c, ui

    return _make


def spool_job(c, title="rota", settings=None) -> Path:
    pdf = c.spool / f"job_7-{title}.pdf"
    pdf.write_bytes(b"%PDF-1.4 captured")
    if settings is not None:
        pdf.with_suffix(".json").write_text(json.dumps(settings))
    return pdf


def test_spool_folder_is_private(make):
    c, _ = make()
    assert c.spool.stat().st_mode & 0o077 == 0


def test_job_waits_in_the_spool_while_the_server_is_unreachable(make):
    c, ui = make()
    pdf = spool_job(c, settings={"copies": 2})
    c.api.fail_with = capture.ApiError("the server could not be reached (refused)")

    assert c.handle(pdf) == "waiting"
    assert pdf.exists() and pdf.with_suffix(".json").exists()
    assert c.watch.problem == "Waiting for the SecurePrint server"
    assert ui.problems == []
    assert len(ui.notices) == 1  # told once, not on every retry
    c.handle(pdf)
    assert len(ui.notices) == 1


def test_server_coming_back_releases_the_hold_and_says_so(make):
    c, ui = make()
    c.watch.report(capture.ApiError("down"))
    c.watch.check()  # the stub answers again
    assert c.watch.problem is None
    assert "back" in ui.notices[-1]


def test_rejected_token_also_holds_jobs(make):
    c, ui = make()
    c.api.fail_with = capture.ApiError("the server refused it (401): Invalid token", 401)
    c.watch.check()
    assert "token" in c.watch.problem
    assert "Tokens page" in ui.notices[-1]


def test_a_job_the_server_refuses_is_dropped_not_retried(make):
    c, ui = make()
    pdf = spool_job(c)
    c.api.fail_with = capture.ApiError("the server refused it (400): not a PDF", 400)
    assert c.handle(pdf) == "not_checked"
    assert not pdf.exists()
    assert ui.problems


def test_a_job_that_keeps_failing_is_given_up_in_the_end(make):
    c, ui = make()
    pdf = spool_job(c)
    c.api.fail_with = capture.ApiError("timed out")
    outcomes = [c.handle(pdf) for _ in range(c.MAX_ATTEMPTS)]
    assert outcomes[:-1] == ["waiting"] * (c.MAX_ATTEMPTS - 1)
    assert outcomes[-1] == "not_checked"
    assert not pdf.exists() and not pdf.with_suffix(".json").exists()


def test_print_settings_reach_the_local_printer(make, monkeypatch):
    c, _ = make(LOCAL_PRINTER="Office_HP")
    pdf = spool_job(c, settings={"copies": 3, "sides": "two-sided-long-edge", "color": "monochrome",
                                 "user": "vinu", "host": "localhost"})
    calls = []
    monkeypatch.setattr(capture.subprocess, "run", lambda cmd, **kw: calls.append(cmd))

    assert c.handle(pdf) == "printed"
    lp = calls[0]
    assert lp[:3] == ["lp", "-d", "Office_HP"]
    assert lp[lp.index("-n") + 1] == "3"
    assert "sides=two-sided-long-edge" in lp and "print-color-mode=monochrome" in lp
    assert c.api.uploads[0][1]["user"] == "vinu"
    path, payload = c.api.posts[-1]
    assert path == "/api/v1/jobs/SP-1/print"
    assert payload == {"released_to": "local printer 'Office_HP'", "copies": 3, "sides": "two-sided-long-edge"}
    assert not pdf.exists() and not pdf.with_suffix(".json").exists()


def test_cups_pdf_jobs_without_settings_print_one_copy(tmp_path):
    pdf = tmp_path / "job_1-x.pdf"
    pdf.write_bytes(b"%PDF")
    assert capture.read_settings(pdf)["copies"] == 1
    pdf.with_suffix(".json").write_text('{"copies": 5000, "sides": "sideways"}')
    settings = capture.read_settings(pdf)
    assert settings["copies"] == 99 and settings["sides"] == "one-sided"
