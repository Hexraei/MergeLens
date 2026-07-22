from app.services.report_formatter import ReportFormatter

def test_report_formatter():
    formatter = ReportFormatter()

    mock_ai_synthesis = {
        "priority_score": 80,
        "risk_score": "low",
        "confidence_score": 95,
        "executive_summary": "Clean dependency upgrade with zero breaking changes.",
        "migration_steps": ["Run test suite", "Merge PR"],
        "security_notes": "Fixes CVE-2024-0001",
        "recommendation": "Safe to merge."
    }

    mock_impact_summary = {
        "direct_impacts": [],
        "import_warnings": [],
        "affected_files": [],
        "call_chains": [],
        "suggested_tests": ["tests/test_main.py"]
    }

    markdown = formatter.format_pr_comment(
        repository_name="encode/databases",
        pr_number=42,
        dependency_name="databases",
        from_version="0.7.0",
        to_version="0.8.0",
        ai_synthesis=mock_ai_synthesis,
        impact_summary=mock_impact_summary
    )

    assert "## MergeLens Dependency Impact Review" in markdown
    assert "`databases` upgrade `0.7.0` &rarr; `0.8.0`" in markdown
    assert "**80 / 100**" in markdown
    assert "**LOW**" in markdown
    assert "Safe to merge." in markdown
    assert "`tests/test_main.py`" in markdown
