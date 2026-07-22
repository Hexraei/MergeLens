import re
from typing import Dict, List, Any

class PRDependencyParser:
    def __init__(self):
        pass

    def parse_requirements_diff(self, diff_text: str) -> List[Dict[str, str]]:
        """
        Parses a requirements.txt diff text to detect upgraded packages.
        Matches pairs of deleted lines (-pkg==1.0) and added lines (+pkg==2.0).
        """
        if not diff_text:
            return []

        deletions: Dict[str, str] = {}
        additions: Dict[str, str] = {}

        # Regex pattern for requirements line: package_name==version or package_name>=version
        pattern = r"^[\+\-]\s*([a-zA-Z0-9_\-\.]+)\s*[=><~]=?\s*([a-zA-Z0-9_\-\.]+)"

        for line in diff_text.splitlines():
            line_str = line.strip()
            if line_str.startswith("---") or line_str.startswith("+++"):
                continue

            if line_str.startswith("-"):
                match = re.match(pattern, line_str)
                if match:
                    pkg_name = match.group(1).lower()
                    ver = match.group(2)
                    deletions[pkg_name] = ver
            elif line_str.startswith("+"):
                match = re.match(pattern, line_str)
                if match:
                    pkg_name = match.group(1).lower()
                    ver = match.group(2)
                    additions[pkg_name] = ver

        upgrades = []
        for pkg, to_ver in additions.items():
            from_ver = deletions.get(pkg, "0.0.0")
            if from_ver != to_ver:
                upgrades.append({
                    "package_name": pkg,
                    "from_version": from_ver,
                    "to_version": to_ver
                })

        return upgrades
