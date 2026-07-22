import re
import json
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session

from app.database import models
from app.services.pypi_client import PyPIClient
from app.services.osv_client import OSVClient
from app.services.ai_reasoner import AIReasonerService

class ReleaseIntelligenceEngine:
    def __init__(self, db: Session):
        self.db = db
        self.pypi_client = PyPIClient()
        self.osv_client = OSVClient()
        self.ai_reasoner = AIReasonerService()

    def _extract_regex_facts(self, raw_text: str) -> Dict[str, List[Any]]:
        """
        Deterministic regex-based parser that scans release notes for standard keyword patterns.
        """
        breaking_apis = []
        behavior_changes = []

        lines = raw_text.splitlines()
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            # Check for breaking API removals/deprecations
            if re.search(r"\b(REMOVED|DEPRECATED|DROPPED)\b", line_str, re.IGNORECASE):
                # Try to extract function/method/class names using backticks or quotes
                symbols_found = re.findall(r"`([^`]+)`|'([^']+)'|\"([^\"]+)\"", line_str)
                symbol_name = "unspecified_symbol"
                for match_tuple in symbols_found:
                    for s in match_tuple:
                        if s:
                            symbol_name = s
                            break

                change_type = "deprecated" if "deprecated" in line_str.lower() else "removed"
                breaking_apis.append({
                    "name": symbol_name,
                    "change_type": change_type,
                    "description": line_str[:250]
                })

            # Check for general breaking behavioral changes
            elif re.search(r"\b(BREAKING|CHANGE|BEHAVIOR|RENAMED)\b", line_str, re.IGNORECASE):
                behavior_changes.append({
                    "description": line_str[:250]
                })

        return {
            "breaking_apis": breaking_apis,
            "behavior_changes": behavior_changes
        }

    async def analyze_package_upgrade(
        self, package_name: str, from_version: str, to_version: str
    ) -> models.ReleaseFact:
        """
        Executes the release intelligence pipeline:
        1. Checks database cache for existing ReleaseFact.
        2. Fetches PyPI release notes and OSV security advisories.
        3. Extracts deterministic facts via Regex and AI reasoning synthesis.
        4. Persists and returns the ReleaseFact database record.
        """
        pkg_clean = package_name.lower().strip()
        
        # 1. Check local database cache
        cached_fact = self.db.query(models.ReleaseFact).filter(
            models.ReleaseFact.package_name == pkg_clean,
            models.ReleaseFact.from_version == from_version,
            models.ReleaseFact.to_version == to_version
        ).first()

        if cached_fact:
            print(f"[ReleaseIntel] Cache hit for {pkg_clean} ({from_version} -> {to_version})")
            return cached_fact

        print(f"[ReleaseIntel] Analyzing release intelligence for {pkg_clean} ({from_version} -> {to_version})...")

        # 2. Fetch raw release notes from PyPI
        raw_notes = await self.pypi_client.get_release_notes(pkg_clean, from_version, to_version)

        # 3. Fetch security advisories from PyPI and OSV.dev (deduplicated by CVE/ID)
        pypi_vulns = await self.pypi_client.get_vulnerabilities(pkg_clean, to_version)
        osv_vulns = await self.osv_client.query_vulnerabilities(pkg_clean, to_version)

        security_fixes_dict = {}
        for v in pypi_vulns + osv_vulns:
            cve_id = v["cve_id"]
            if cve_id not in security_fixes_dict:
                security_fixes_dict[cve_id] = v

        security_fixes = list(security_fixes_dict.values())

        # 4. Extract deterministic facts using regex
        regex_facts = self._extract_regex_facts(raw_notes)

        breaking_apis = regex_facts["breaking_apis"]
        behavior_changes = regex_facts["behavior_changes"]

        # 5. AI Synthesis fallback / enhancement if raw notes exist
        # We can construct evidence payload to get AI reasoning if OpenRouter API is configured
        if len(raw_notes) > 50 and self.ai_reasoner.api_key:
            try:
                ai_payload = {
                    "package": pkg_clean,
                    "version_upgrade": {"from": from_version, "to": to_version},
                    "release_notes": raw_notes[:3000]
                }
                ai_result = await self.ai_reasoner.analyze_upgrade(ai_payload)
                # If AI returned specific migration steps, add to behavior changes
                if "migration_steps" in ai_result:
                    for step in ai_result["migration_steps"]:
                        behavior_changes.append({"description": step})
            except Exception as e:
                print(f"[ReleaseIntel Warning] AI extraction failed, falling back to regex: {e}")

        # 6. Save to Database
        fact_record = models.ReleaseFact(
            package_name=pkg_clean,
            from_version=from_version,
            to_version=to_version,
            release_notes_raw=raw_notes[:10000],  # Cap raw notes to fit DB column nicely
            breaking_apis_json=breaking_apis,
            behavior_changes_json=behavior_changes,
            security_fixes_json=security_fixes
        )
        self.db.add(fact_record)
        self.db.commit()
        self.db.refresh(fact_record)

        print(f"[ReleaseIntel] Analysis complete. Created ReleaseFact id={fact_record.id}")
        return fact_record
