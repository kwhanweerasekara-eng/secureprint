"""The job keeps how its score was built: the points each category added and,
when a category floor raised the level, which category did it. The job page's
"Why this score?" panel reads these from the audit events."""
from tests.test_virtual_printer_flow import SETTLED, _agent_headers, _capture, _poll


def _event(detail, event_type):
    return next(e for e in detail["events"] if e["event_type"] == event_type)


def test_score_is_explained_by_the_points_of_each_category(client, staff_client, tmp_path):
    headers = _agent_headers(staff_client)
    job_id = _capture(
        client,
        headers,
        tmp_path,
        ["NIC: 200012345678", "Bank Account Number: 123456789012", "Salary: 285,000"],
    )
    detail = _poll(client, headers, job_id, SETTLED)

    scored = _event(detail, "RISK_SCORED")["event_metadata"]
    contributions = scored["contributions"]
    assert {"nic", "bank_account", "salary"} <= set(contributions)
    assert scored["uncapped_score"] == sum(contributions.values())
    assert detail["risk_score"] == min(100, scored["uncapped_score"])
    # Counts never multiply the score: each category adds its weight once.
    assert all(isinstance(v, int) for v in contributions.values())

    classified = _event(detail, "CLASSIFIED")["event_metadata"]
    assert classified["raised_by"] == []


def test_a_floor_records_which_category_raised_the_level(client, staff_client, tmp_path):
    headers = _agent_headers(staff_client)
    job_id = _capture(client, headers, tmp_path, ["Server handover", "password: Winter@2026"])
    detail = _poll(client, headers, job_id, SETTLED)

    classified = _event(detail, "CLASSIFIED")["event_metadata"]
    assert detail["classification"] == "RESTRICTED"
    assert classified["score_classification"] != "RESTRICTED"
    assert classified["raised_by"] == ["credential"]
