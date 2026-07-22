import httpx
from typing import Dict, List, Any

class OSVClient:
    def __init__(self, base_url: str = "https://api.osv.dev"):
        self.base_url = base_url

    async def query_vulnerabilities(self, package_name: str, version: str) -> List[Dict[str, Any]]:
        """
        Queries OSV.dev API for security vulnerabilities associated with a PyPI package version.
        API URL: POST https://api.osv.dev/v1/query
        """
        url = f"{self.base_url}/v1/query"
        payload = {
            "package": {
                "name": package_name,
                "ecosystem": "PyPI"
            },
            "version": version
        }

        vulnerabilities = []
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(url, json=payload, timeout=15.0)
                if resp.status_code != 200:
                    print(f"[OSVClient Error] HTTP {resp.status_code} querying vulnerabilities for {package_name} {version}")
                    return vulnerabilities

                data = resp.json()
                vulns_raw = data.get("vulns", [])

                for item in vulns_raw:
                    vuln_id = item.get("id", "N/A")
                    aliases = item.get("aliases", [])
                    summary = item.get("summary", item.get("details", "No description provided."))

                    # Look for CVE alias if available
                    cve_id = vuln_id
                    for alias in aliases:
                        if alias.startswith("CVE-"):
                            cve_id = alias
                            break

                    # Extract database_specific or severity rating if present
                    severity = "HIGH"
                    if "database_specific" in item and "severity" in item["database_specific"]:
                        severity = item["database_specific"]["severity"].upper()

                    vulnerabilities.append({
                        "cve_id": cve_id,
                        "severity": severity,
                        "description": summary[:500] if summary else "Security vulnerability reported.",
                        "source": "OSV.dev"
                    })

            except Exception as e:
                print(f"[OSVClient Exception] Failed to query OSV.dev for {package_name} {version}: {e}")

        return vulnerabilities
