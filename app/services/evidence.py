from typing import Dict, List, Any

class EvidenceBuilder:
    def __init__(self):
        pass

    def build_from_impact_report(
        self,
        impact_report: Dict[str, Any],
        release_fact: Any
    ) -> Dict[str, Any]:
        """
        Synthesizes output from RepositoryImpactEngine and ReleaseFact into a token-efficient
        structured evidence dictionary for the AI reasoner.
        """
        pkg_name = impact_report.get("package_name", "unknown")
        upgrade_path = impact_report.get("upgrade_path", "")
        parts = upgrade_path.split(" -> ")
        from_ver = parts[0] if len(parts) > 0 else "unknown"
        to_ver = parts[1] if len(parts) > 1 else "unknown"

        # Format Direct Impacts
        direct_impacts = impact_report.get("direct_impacts", [])
        formatted_direct = []
        for imp in direct_impacts:
            formatted_direct.append(
                f"File `{imp.get('file_path')}` (line {imp.get('line_number')}): "
                f"symbol `{imp.get('imported_symbol')}` - {imp.get('description', '')}"
            )

        # Format Import Warnings
        import_warnings = impact_report.get("import_warnings", [])
        formatted_warnings = [w.get("warning", "") for w in import_warnings]

        # Format Call Chains
        call_chains = impact_report.get("call_chains", [])
        formatted_chains = [" -> ".join(chain) for chain in call_chains]

        # Format Security Fixes
        sec_fixes = getattr(release_fact, "security_fixes_json", []) or []
        formatted_sec = []
        for s in sec_fixes:
            formatted_sec.append(
                f"CVE `{s.get('cve_id')}` (Severity: {s.get('severity', 'HIGH')}): {s.get('description', '')}"
            )

        # Raw Release Excerpt
        raw_notes = getattr(release_fact, "release_notes_raw", "") or ""
        notes_excerpt = raw_notes[:2000] if raw_notes else "No raw release notes."

        return {
            "repository": impact_report.get("repository", "unknown"),
            "package_name": pkg_name,
            "version_upgrade": {
                "from": from_ver,
                "to": to_ver
            },
            "calculated_risk_score": impact_report.get("risk_score", "low"),
            "evidence": {
                "direct_code_impacts": formatted_direct if formatted_direct else ["No direct broken symbol calls detected."],
                "unused_import_warnings": formatted_warnings if formatted_warnings else ["No import warnings."],
                "affected_files": impact_report.get("affected_files", []),
                "call_chains": formatted_chains if formatted_chains else ["No caller chains impacted."],
                "suggested_tests": impact_report.get("suggested_tests", []),
                "security_fixes": formatted_sec if formatted_sec else ["No known security vulnerabilities."],
                "release_notes_excerpt": notes_excerpt
            }
        }
