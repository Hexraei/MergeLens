import pytest
from app.services.evidence import EvidenceBuilder

def test_evidence_builder():
    builder = EvidenceBuilder()

    mock_impact_report = {
        "repository": "encode/databases",
        "package_name": "databases",
        "upgrade_path": "0.7.0 -> 0.8.0",
        "risk_score": "low",
        "direct_impacts": [],
        "import_warnings": [{"file_path": "tests/test_db.py", "warning": "Unused import warning"}],
        "affected_files": [],
        "call_chains": [],
        "suggested_tests": ["tests/test_db.py"]
    }

    class MockReleaseFact:
        security_fixes_json = [{"cve_id": "CVE-2024-0001", "severity": "HIGH", "description": "Fix SQL injection"}]
        release_notes_raw = "Databases version 0.8.0 release notes."

    evidence = builder.build_from_impact_report(mock_impact_report, MockReleaseFact())

    assert evidence["package_name"] == "databases"
    assert evidence["version_upgrade"]["from"] == "0.7.0"
    assert evidence["version_upgrade"]["to"] == "0.8.0"
    assert len(evidence["evidence"]["security_fixes"]) == 1
    assert "CVE-2024-0001" in evidence["evidence"]["security_fixes"][0]
