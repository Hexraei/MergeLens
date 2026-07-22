import pytest
from unittest.mock import patch, AsyncMock
from app.database import models
from app.database.db import SessionLocal
from app.services.release_intel import ReleaseIntelligenceEngine

@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.mark.asyncio
async def test_release_intelligence_engine(db_session):
    db_session.query(models.ReleaseFact).filter(models.ReleaseFact.package_name == "mockpkg").delete()
    db_session.commit()

    engine = ReleaseIntelligenceEngine(db_session)

    mock_notes = (
        "Package: databases\n"
        "Upgrade: 0.7.0 -> 0.8.0\n"
        "REMOVED: `DatabaseConnection` method is removed.\n"
        "DEPRECATED: `execute_many` is deprecated.\n"
        "BREAKING CHANGE: connection timeout default changed to 30s."
    )
    mock_pypi_vulns = []
    mock_osv_vulns = [
        {"cve_id": "CVE-2024-5555", "severity": "HIGH", "description": "Buffer overflow", "source": "OSV.dev"}
    ]

    with patch.object(engine.pypi_client, "get_release_notes", new_callable=AsyncMock) as mock_get_notes, \
         patch.object(engine.pypi_client, "get_vulnerabilities", new_callable=AsyncMock) as mock_get_pypi_vulns, \
         patch.object(engine.osv_client, "query_vulnerabilities", new_callable=AsyncMock) as mock_query_osv:

        mock_get_notes.return_value = mock_notes
        mock_get_pypi_vulns.return_value = mock_pypi_vulns
        mock_query_osv.return_value = mock_osv_vulns

        # Execute analysis
        fact = await engine.analyze_package_upgrade("mockpkg", "1.0.0", "2.0.0")

        assert fact.id is not None
        assert fact.package_name == "mockpkg"
        assert len(fact.breaking_apis_json) == 2
        assert len(fact.security_fixes_json) == 1
        assert fact.security_fixes_json[0]["cve_id"] == "CVE-2024-5555"

        # Verify caching (second call should return cached record without invoking APIs)
        cached_fact = await engine.analyze_package_upgrade("mockpkg", "1.0.0", "2.0.0")
        assert cached_fact.id == fact.id
