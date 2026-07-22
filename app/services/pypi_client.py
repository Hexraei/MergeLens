import httpx
from typing import Dict, List, Any, Optional

class PyPIClient:
    def __init__(self, base_url: str = "https://pypi.org"):
        self.base_url = base_url

    async def get_package_metadata(self, package_name: str) -> Optional[Dict[str, Any]]:
        """
        Fetches the complete JSON metadata for a package from PyPI.
        URL format: https://pypi.org/pypi/<package_name>/json
        """
        url = f"{self.base_url}/pypi/{package_name}/json"
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url, timeout=15.0)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 404:
                    print(f"[PyPIClient] Package '{package_name}' not found on PyPI.")
                    return None
                else:
                    print(f"[PyPIClient Error] HTTP {resp.status_code} fetching metadata for {package_name}")
                    return None
            except Exception as e:
                print(f"[PyPIClient Exception] Failed to fetch PyPI metadata for {package_name}: {e}")
                return None

    async def get_release_notes(
        self, package_name: str, from_version: str, to_version: str
    ) -> str:
        """
        Retrieves release descriptions or project documentation from PyPI metadata.
        """
        metadata = await self.get_package_metadata(package_name)
        if not metadata:
            return f"No PyPI release metadata available for package '{package_name}'."

        info = metadata.get("info", {})
        description = info.get("description", "")
        summary = info.get("summary", "")

        # Collect project URLs (e.g. Changelog URL, Repository URL)
        project_urls = info.get("project_urls") or {}
        changelog_url = None
        for key, value in project_urls.items():
            if "changelog" in key.lower() or "changes" in key.lower() or "release" in key.lower():
                changelog_url = value
                break

        notes = [
            f"Package: {package_name}",
            f"Upgrade path: {from_version} -> {to_version}",
            f"Summary: {summary}",
        ]
        if changelog_url:
            notes.append(f"Changelog URL: {changelog_url}")

        if description:
            # Append description text (capped to 5000 characters to stay concise)
            notes.append("\nProject Description & Changelog Excerpt:")
            notes.append(description[:5000])

        return "\n".join(notes)

    async def get_vulnerabilities(self, package_name: str, version: str) -> List[Dict[str, Any]]:
        """
        Extracts PyPI native vulnerability disclosures for the given package version.
        """
        metadata = await self.get_package_metadata(package_name)
        if not metadata:
            return []

        vulnerabilities_raw = metadata.get("vulnerabilities", [])
        vulnerabilities = []

        for vuln in vulnerabilities_raw:
            # Filter vulnerabilities that apply to this version if details exist
            vuln_id = vuln.get("id", "N/A")
            summary = vuln.get("summary", "Security advisory published on PyPI")
            details = vuln.get("details", "")
            aliases = vuln.get("aliases", [])

            cve_id = vuln_id
            for alias in aliases:
                if alias.startswith("CVE-"):
                    cve_id = alias
                    break

            vulnerabilities.append({
                "cve_id": cve_id,
                "severity": "HIGH",  # Default severity if unspecified
                "summary": summary,
                "description": details[:500] if details else summary,
                "source": "PyPI Native Vulnerabilities"
            })

        return vulnerabilities
