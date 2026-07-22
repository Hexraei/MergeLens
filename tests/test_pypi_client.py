import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.services.pypi_client import PyPIClient

@pytest.mark.asyncio
async def test_pypi_client_metadata():
    client = PyPIClient()
    mock_payload = {
        "info": {
            "name": "databases",
            "summary": "Async database support for Python.",
            "description": "DEPRECATED: OldEngine is removed in version 0.8.0.",
            "project_urls": {
                "Changelog": "https://github.com/encode/databases/docs/changelog.md"
            }
        },
        "vulnerabilities": [
            {
                "id": "PYSEC-2023-123",
                "aliases": ["CVE-2023-99999"],
                "summary": "SQL injection flaw in legacy connector",
                "details": "Full vulnerability explanation"
            }
        ]
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_payload
        mock_get.return_value = mock_resp

        metadata = await client.get_package_metadata("databases")
        assert metadata is not None
        assert metadata["info"]["name"] == "databases"

        notes = await client.get_release_notes("databases", "0.7.0", "0.8.0")
        assert "databases" in notes
        assert "Changelog URL:" in notes
        assert "DEPRECATED: OldEngine is removed" in notes

        vulns = await client.get_vulnerabilities("databases", "0.8.0")
        assert len(vulns) == 1
        assert vulns[0]["cve_id"] == "CVE-2023-99999"
