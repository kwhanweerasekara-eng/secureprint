"""Wires the top-level cybersecurity processing engine (services/document-analysis,
services/classification, services/document-processing, services/audit) into the
API process.

Those directories are intentionally named with hyphens to match the required
repository layout, which means they cannot be imported as normal Python
packages (`services.document-analysis` is not valid syntax). Instead we add
each directory to sys.path once, at import time, and import its modules by
filename. Module names inside the engine are unique across all four
directories, so this is unambiguous.
"""
from __future__ import annotations

import sys
from pathlib import Path

from apps.api.config import REPO_ROOT

_ENGINE_DIRS = [
    REPO_ROOT / "services" / "document-analysis",
    REPO_ROOT / "services" / "classification",
    REPO_ROOT / "services" / "document-processing",
    REPO_ROOT / "services" / "audit",
]

for _d in _ENGINE_DIRS:
    p = str(_d)
    if p not in sys.path:
        sys.path.insert(0, p)

# document-analysis
import extractor  # noqa: E402
import detector  # noqa: E402
import report  # noqa: E402

# classification
import scorer  # noqa: E402
import classifier  # noqa: E402
import policy as policy_engine  # noqa: E402

# document-processing
import redactor  # noqa: E402
import watermark  # noqa: E402
import footer  # noqa: E402
import orientation  # noqa: E402
import processor  # noqa: E402

# audit
import audit_service  # noqa: E402

__all__ = [
    "extractor",
    "detector",
    "report",
    "scorer",
    "classifier",
    "policy_engine",
    "redactor",
    "watermark",
    "footer",
    "orientation",
    "processor",
    "audit_service",
]
