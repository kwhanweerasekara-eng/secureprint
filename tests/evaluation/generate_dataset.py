"""Generates a synthetic evaluation dataset (spec section 51): 50+ PDFs spread
across PUBLIC/INTERNAL/CONFIDENTIAL/RESTRICTED with known ground truth, so
detection and classification accuracy can be measured objectively rather than
eyeballed.

Ground truth for each document is the set of sensitive-data categories it was
constructed to contain, plus the classification that should follow from the
default risk weights/thresholds (config/weights.json, config/policies.json).

Usage:
    python tests/evaluation/generate_dataset.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services" / "document-analysis"))

import fitz  # noqa: E402

OUTPUT_DIR = REPO_ROOT / "tests" / "fixtures" / "synthetic"

# Content fragments per category - each is guaranteed to trigger exactly one
# category in the default detection rules (config/patterns.json / keywords.json).
FRAGMENTS = {
    "email": "Contact: employee.{n}@example.com",
    "telephone": "Telephone: 077{n:07d}",
    "nic": "NIC: 20001{n:07d}",
    "employee_id": "Employee ID: EMP-{n:05d}",
    "salary": "Basic Salary: LKR {n:03d},000",
    "bank_account": "Bank Account Number: 1234{n:08d}",
    "credential": "password: Sup3rSecret{n}!",
    "card": "Card Number: 4111 1111 1111 1111",  # well-known Luhn-valid test Visa number
    "classification_marker": "CONFIDENTIAL",
    "api_key": "AWS_ACCESS_KEY_ID: AKIAIOSFODNN7EXAMPLE",  # AWS's own documented example key
    "iban": "IBAN: GB29NWBK60161331926819",  # well-known example IBAN (Wikipedia/ISO docs)
    "passport": "Passport No: N{n:07d}",
}

FILLER = [
    "SecurePrint Demo Organisation",
    "Internal Memo",
    "Please review the attached information before the end of the week.",
    "Thank you for your attention to this matter.",
]

# (label, category_combo, expected_classification)
# A real credential, API key or card number makes a document RESTRICTED
# whatever its score (category floors in config/weights.json, proposal T05).
# Weights: api_key 45, credential 40, card 40, bank_account 30, iban 30, nic 30,
#          passport 30, salary 20, classification_marker 20, employee_id 15,
#          email 10, telephone 10
SCENARIOS = [
    ("public_plain", [], "PUBLIC"),
    ("public_email_only", ["email"], "PUBLIC"),
    ("public_telephone_only", ["telephone"], "PUBLIC"),
    ("public_email_telephone", ["email", "telephone"], "PUBLIC"),
    ("internal_nic_only", ["nic"], "INTERNAL"),
    ("internal_passport_only", ["passport"], "INTERNAL"),
    ("internal_iban_only", ["iban"], "INTERNAL"),
    ("internal_salary_email", ["salary", "email"], "INTERNAL"),
    ("internal_marker_email", ["classification_marker", "email"], "INTERNAL"),
    ("internal_empid_email_tel", ["employee_id", "email", "telephone"], "INTERNAL"),
    ("confidential_nic_salary", ["nic", "salary"], "CONFIDENTIAL"),
    ("confidential_bank_email_tel", ["bank_account", "email", "telephone"], "CONFIDENTIAL"),
    ("confidential_nic_empid_email", ["nic", "employee_id", "email"], "CONFIDENTIAL"),
    ("restricted_floor_credential_email", ["credential", "email"], "RESTRICTED"),
    ("confidential_iban_salary", ["iban", "salary"], "CONFIDENTIAL"),
    ("confidential_passport_nic", ["passport", "nic"], "CONFIDENTIAL"),
    ("restricted_floor_api_key_alone", ["api_key"], "RESTRICTED"),
    ("restricted_credential_nic_bank", ["credential", "nic", "bank_account"], "RESTRICTED"),
    ("restricted_nic_bank_salary_email", ["nic", "bank_account", "salary", "email"], "RESTRICTED"),
    ("restricted_credential_card", ["credential", "card"], "RESTRICTED"),
    ("restricted_full_payroll", ["nic", "bank_account", "credential", "salary", "employee_id"], "RESTRICTED"),
    ("restricted_api_key_credential", ["api_key", "credential"], "RESTRICTED"),
    ("restricted_api_key_passport_nic", ["api_key", "passport", "nic"], "RESTRICTED"),
]


def render(categories: list[str], seed: int) -> list[str]:
    lines = list(FILLER)
    for cat in categories:
        template = FRAGMENTS[cat]
        lines.append(template.format(n=seed, single=(seed % 10)))
    return lines


def make_pdf(path: Path, lines: list[str]) -> None:
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in lines:
        page.insert_text((50, y), line, fontsize=12, fontname="helv")
        y += 20
    doc.save(str(path))
    doc.close()


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    doc_index = 0
    variants_per_scenario = 4  # 16 scenarios x 4 = 64 documents (>= the required 50)

    for label, categories, expected_classification in SCENARIOS:
        for variant in range(variants_per_scenario):
            doc_index += 1
            seed = 1000 + doc_index
            filename = f"{doc_index:03d}_{label}_v{variant}.pdf"
            lines = render(categories, seed)
            make_pdf(OUTPUT_DIR / filename, lines)
            manifest.append(
                {
                    "filename": filename,
                    "scenario": label,
                    "expected_categories": sorted(set(categories)),
                    "expected_classification": expected_classification,
                }
            )

    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"Generated {len(manifest)} synthetic documents in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
