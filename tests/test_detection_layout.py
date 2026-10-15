"""Detection in tables and forms, where a value's label is in a column header
or the cell to its left rather than on the same text line, plus the other
fixes from the first realistic evaluation run (docs/evaluation-results.md)."""
import fitz
import pytest

from tests.test_detection import load_rules_and_keywords, run_detection


def run_layout(engine, tmp_path, cells):
    """cells: [(x, y, text)] placed exactly, as Word/Excel tables come out."""
    doc = fitz.open()
    page = doc.new_page()
    for x, y, text in cells:
        page.insert_text((x, y), text, fontsize=10, fontname="helv")
    path = tmp_path / "layout.pdf"
    doc.save(str(path))
    doc.close()
    extraction = engine.extractor.extract_document(str(path))
    rules, keywords = load_rules_and_keywords(engine)
    detections = engine.detector.detect(extraction, rules, keywords)
    return detections


def regex_values(detections, category):
    return [d.value for d in detections if d.category == category and d.source == "regex"]


def test_salary_amounts_under_a_column_header_are_detected(engine, tmp_path):
    cells = [(50, 72, "Name"), (300, 72, "Gross pay"), (420, 72, "Net pay")]
    for i, (gross, net) in enumerate([("285,000.00", "241,350.50"), ("172,500", "150,100")]):
        y = 90 + 14 * i
        cells += [(50, y, f"Person {i}"), (300, y, gross), (420, y, net)]
    values = regex_values(run_layout(engine, tmp_path, cells), "salary")
    assert sorted(values) == sorted(["285,000.00", "241,350.50", "172,500", "150,100"])


def test_account_number_beside_its_form_label_is_detected(engine, tmp_path):
    detections = run_layout(engine, tmp_path, [(50, 72, "Account number"), (210, 72, "0012 3456 7890")])
    assert regex_values(detections, "bank_account") == ["0012 3456 7890"]


def test_password_in_a_table_column_is_detected(engine, tmp_path):
    cells = [(50, 72, "System"), (200, 72, "Password"),
             (50, 86, "Payroll server"), (200, 86, "Tiger#336"),
             (50, 100, "Firewall"), (200, 100, "Lotus_1924")]
    values = regex_values(run_layout(engine, tmp_path, cells), "credential")
    assert sorted(values) == ["Lotus_1924", "Tiger#336"]


def test_a_label_value_line_does_not_lend_its_label_to_the_line_below(engine, tmp_path):
    # "Bank Account Number: ..." already has its value; the phone number on the
    # next line must stay a phone number, not become a second account number.
    detections, categories = run_detection(
        engine, tmp_path, ["Bank Account Number: 123400001045", "Telephone: 0770001045"])
    assert categories.get("telephone") == 1
    assert regex_values(detections, "bank_account") == ["123400001045"]


def test_salary_label_at_the_end_of_a_wrapped_line_counts(engine, tmp_path):
    detections, _ = run_detection(
        engine, tmp_path, ["We are pleased to confirm that your basic salary", "will be 285,000 per month."])
    assert regex_values(detections, "salary") == ["285,000"]


@pytest.mark.parametrize("number", ["077 123 4567", "077-1234567", "+94 77 123 4567", "011-2345678", "0771234567"])
def test_common_telephone_formats(engine, tmp_path, number):
    detections, _ = run_detection(engine, tmp_path, [f"Contact: {number}"])
    assert regex_values(detections, "telephone") == [number]


def test_environment_file_password_is_detected(engine, tmp_path):
    detections, _ = run_detection(engine, tmp_path, ["DB_PASSWORD=Kandy#77"])
    assert regex_values(detections, "credential") == ["PASSWORD=Kandy#77"]


def test_organisation_employee_number_formats_with_a_label(engine, tmp_path):
    detections = run_layout(engine, tmp_path, [(50, 72, "Employee no."), (210, 72, "SL/04512")])
    assert regex_values(detections, "employee_id") == ["SL/04512"]


def test_purchase_order_number_is_not_a_nic(engine, tmp_path):
    # 4500... can't be a birth year, so this 12-digit number is not a new-format NIC.
    _, categories = run_detection(engine, tmp_path, ["PO no. 450012345678"])
    assert categories.get("nic") is None


def test_price_is_not_a_salary(engine, tmp_path):
    _, categories = run_detection(engine, tmp_path, ["Total due: Rs. 327,700.00 within 30 days."])
    assert categories.get("salary") is None


def test_keywords_match_whole_words_only(engine, tmp_path):
    _, categories = run_detection(engine, tmp_path, ["Accounts Executive, Ceylon Packaging (2021 - present)"])
    assert categories.get("bank_account") is None


def test_unedited_builtin_rule_is_upgraded_and_edited_rule_is_kept(client):  # client: app started and seeded
    from apps.api.database.session import SessionLocal
    from apps.api.models.rule import DetectionRule
    from apps.api.services import seed

    db = SessionLocal()
    try:
        tel = db.query(DetectionRule).filter(DetectionRule.name == "telephone").one()
        cred = db.query(DetectionRule).filter(DetectionRule.name == "credential").one()
        current_tel, current_cred = tel.pattern, cred.pattern

        tel.pattern = seed._SUPERSEDED_PATTERNS["telephone"]  # as an older install left it
        cred.pattern = r"(?i)password:\s*\S+"  # an admin's own edit
        db.commit()

        seed.upgrade_builtin_rules(db)
        db.refresh(tel)
        db.refresh(cred)
        assert tel.pattern == current_tel
        assert cred.pattern == r"(?i)password:\s*\S+"
    finally:
        cred.pattern = current_cred
        db.commit()
        db.close()


def test_card_security_code_beside_its_label_is_detected(engine, tmp_path):
    detections = run_layout(engine, tmp_path, [(50, 72, "CVV"), (210, 72, "113"),
                                               (50, 88, "Amount"), (210, 88, "Rs. 59,880.00")])
    assert regex_values(detections, "card") == ["113"]
