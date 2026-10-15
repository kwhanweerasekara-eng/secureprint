import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_TEST_DIR = Path(tempfile.mkdtemp(prefix="secureprint_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DIR / 'test.db'}"
os.environ["STORAGE_ROOT"] = str(_TEST_DIR / "storage")
os.environ["JWT_SECRET"] = "test-secret-not-for-production"

import fitz  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from apps.api.main import app  # noqa: E402
from apps.api.services import engine_loader as eng  # noqa: E402

ADMIN_PASSWORD = "admin123"
STAFF_PASSWORD = "staff123"


def make_pdf(path: Path, lines: list[str]) -> str:
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in lines:
        page.insert_text((50, y), line, fontsize=12, fontname="helv")
        y += 20
    doc.save(str(path))
    doc.close()
    return str(path)


def make_scanned_pdf(path: Path) -> str:
    """A page with no text layer at all - simulates a scanned/image-only document."""
    doc = fitz.open()
    doc.new_page()
    doc.save(str(path))
    doc.close()
    return str(path)


@pytest.fixture()
def pdf_factory(tmp_path):
    def _factory(lines: list[str], name: str = "doc.pdf") -> str:
        return make_pdf(tmp_path / name, lines)

    return _factory


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def staff_client():
    # Independent TestClient (own cookie jar) so a test requesting both
    # staff_client and admin_client doesn't have the second login silently
    # overwrite the first's session cookie on a shared client.
    with TestClient(app) as c:
        resp = c.post("/api/v1/auth/login", json={"username": "staff", "password": STAFF_PASSWORD})
        assert resp.status_code == 200
        yield c


@pytest.fixture()
def admin_client():
    with TestClient(app) as c:
        resp = c.post("/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
        assert resp.status_code == 200
        yield c


@pytest.fixture()
def engine():
    return eng
