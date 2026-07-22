import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.services.osv_client import OSVClient

@pytest.mark.asyncio
async def test_osv_client_query():
    client = OSVClient()
    mock_payload = {
        "vulns": [
            {
                "id": "GHSA-1234-abcd-5678",
                "aliases": ["CVE-2024-11111"],
                "summary": "Remote code execution vulnerability",
                "database_specific": {"severity": "CRITICAL"}
            }
        ]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_payload
        mock_post.return_value = mock_resp

        vulns = await client.query_vulnerabilities("requests", "2.31.0")
        assert len(vulns) == 1
        assert vulns[0]["cve_id"] == "CVE-2024-11111"
        assert vulns[0]["severity"] == "CRITICAL"
        assert vulns[0]["source"] == "OSV.dev"
