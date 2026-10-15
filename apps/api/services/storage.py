"""Upload validation and safe on-disk file handling.

Every uploaded document is stored under a randomized UUID filename inside
storage/incoming - the original filename supplied by the browser is only ever
used for display, never as a path component, which rules out path traversal.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path

from fastapi import UploadFile

from apps.api.config import get_settings

settings = get_settings()

PDF_MAGIC = b"%PDF-"
MAX_UPLOAD_BYTES = settings.max_upload_mb * 1024 * 1024


class UploadValidationError(Exception):
    pass


def sanitize_display_filename(filename: str) -> str:
    name = Path(filename or "document.pdf").name  # strip any directory components
    name = re.sub(r"[^A-Za-z0-9._\- ]", "_", name)
    return name[:255] or "document.pdf"


async def save_upload(file: UploadFile) -> tuple[Path, str, str, int]:
    """Validates and persists an uploaded PDF.

    Returns (stored_path, display_filename, sha256_hex, size_bytes).
    Raises UploadValidationError on any validation failure.
    """
    if file.content_type not in ("application/pdf", "application/x-pdf", "application/octet-stream"):
        raise UploadValidationError("Only PDF files are accepted")

    display_filename = sanitize_display_filename(file.filename or "document.pdf")
    if not display_filename.lower().endswith(".pdf"):
        raise UploadValidationError("Only .pdf files are accepted")

    stored_name = f"{uuid.uuid4()}.pdf"
    stored_path = settings.incoming_dir / stored_name

    hasher = hashlib.sha256()
    size = 0
    first_chunk = True

    with open(stored_path, "wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            if first_chunk:
                if not chunk.startswith(PDF_MAGIC):
                    out.close()
                    stored_path.unlink(missing_ok=True)
                    raise UploadValidationError("File does not appear to be a valid PDF")
                first_chunk = False
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                out.close()
                stored_path.unlink(missing_ok=True)
                raise UploadValidationError(f"File exceeds maximum upload size of {settings.max_upload_mb}MB")
            hasher.update(chunk)
            out.write(chunk)

    if size == 0:
        stored_path.unlink(missing_ok=True)
        raise UploadValidationError("Uploaded file is empty")

    return stored_path, display_filename, hasher.hexdigest(), size
