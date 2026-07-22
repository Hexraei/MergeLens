import json
from typing import Dict, List, Any, Optional
import networkx as nx
from sqlalchemy.orm import Session

from app.database import models
from app.services.release_intel import ReleaseIntelligenceEngine

class RepositoryImpactEngine:
    def __init__(self, db: Session):
        self.db = db
        self.release_intel = ReleaseIntelligenceEngine(db)

    async def analyze_impact(
        self,
        repo_id: int,
        package_name: str,
        from_version: str,
        to_version: str,
        warn_on_unused_imports: bool = False
    ) -> Dict[str, Any]:
        """
        Calculates codebase impact and blast radius for a dependency upgrade.
        """
        pkg_clean = package_name.lower().strip()

        # 1. Fetch Repository from Database
        repo = self.db.query(models.Repository).filter(models.Repository.id == repo_id).first()
        if not repo:
            raise ValueError(f"Repository with id {repo_id} not found.")

        # 2. Obtain Release Intelligence Facts
        release_fact = await self.release_intel.analyze_package_upgrade(pkg_clean, from_version, to_version)
        breaking_apis = release_fact.breaking_apis_json or []
        behavior_changes = release_fact.behavior_changes_json or []
        security_fixes = release_fact.security_fixes_json or []

        # 3. Fetch API usages for this package in the repository
        usages = self.db.query(models.ApiUsage).filter(
            models.ApiUsage.repository_id == repo.id,
            models.ApiUsage.package_name == pkg_clean
        ).all()

        # Direct Usage Matching
        direct_impacts = []
        impacted_file_paths = set()
        impacted_symbol_names = set()

        def is_symbol_match(b_name: str, u_sym: str) -> bool:
            if not b_name or b_name == "unspecified_symbol":
                return True
            if not u_sym:
                return False
            return b_name == u_sym or b_name.endswith("." + u_sym) or u_sym.endswith("." + b_name)

        for usage in usages:
            imported_symbol = usage.imported_symbol or ""
            # Check if usage matches any declared breaking API
            for b_api in breaking_apis:
                b_name = b_api.get("name", "")
                if is_symbol_match(b_name, imported_symbol):
                    direct_impacts.append({
                        "file_path": usage.file_path,
                        "line_number": usage.line_number,
                        "imported_symbol": usage.imported_symbol,
                        "change_type": b_api.get("change_type", "breaking"),
                        "description": b_api.get("description", "Breaking API change")
                    })
                    impacted_file_paths.add(usage.file_path)
                    if usage.imported_symbol:
                        impacted_symbol_names.add(usage.imported_symbol)

        # Toggleable Import Warnings
        import_warnings = []
        if warn_on_unused_imports:
            # Find all files importing this package
            files_importing_pkg = {u.file_path for u in usages}
            for f_path in files_importing_pkg:
                if f_path not in impacted_file_paths:
                    import_warnings.append({
                        "file_path": f_path,
                        "warning": f"File imports '{pkg_clean}' which has breaking changes in version {to_version}, but no direct broken method calls were detected."
                    })

        # 4. Reconstruct Graphs & Trace Call Chains
        call_chains = []
        affected_modules = set()

        if repo.call_graph_json:
            try:
                call_graph = nx.node_link_graph(repo.call_graph_json)
                # Find symbols defined in impacted files
                repo_symbols = self.db.query(models.Symbol).filter(
                    models.Symbol.repository_id == repo.id,
                    models.Symbol.file_path.in_(list(impacted_file_paths))
                ).all()

                for sym in repo_symbols:
                    func_node = sym.name
                    if call_graph.has_node(func_node):
                        # Find ancestor callers in call graph
                        ancestors = list(nx.ancestors(call_graph, func_node))
                        for anc in ancestors:
                            if nx.has_path(call_graph, anc, func_node):
                                try:
                                    path = nx.shortest_path(call_graph, anc, func_node)
                                    if len(path) > 1 and path not in call_chains:
                                        call_chains.append(path)
                                except nx.NetworkXNoPath:
                                    pass
            except Exception as e:
                print(f"[ImpactEngine Warning] Failed to parse call graph: {e}")

        if repo.dependency_graph_json:
            try:
                dep_graph = nx.node_link_graph(repo.dependency_graph_json)
                for f_path in impacted_file_paths:
                    mod_name = f_path.replace("/", ".").replace(".py", "")
                    if dep_graph.has_node(mod_name):
                        ancestors = list(nx.ancestors(dep_graph, mod_name))
                        affected_modules.update(ancestors)
                        affected_modules.add(mod_name)
            except Exception as e:
                print(f"[ImpactEngine Warning] Failed to parse dependency graph: {e}")

        # 5. Map Affected Test Files
        suggested_tests = []
        all_test_symbols = self.db.query(models.Symbol).filter(
            models.Symbol.repository_id == repo.id
        ).all()

        for sym in all_test_symbols:
            is_test_file = "test" in sym.file_path.lower()
            is_test_func = sym.name.startswith("test_") or "test" in sym.name.lower()
            if is_test_file or is_test_func:
                # Check if this test file or function intersects with affected modules or files
                if sym.file_path not in suggested_tests:
                    suggested_tests.append(sym.file_path)

        # 6. Calculate Risk Score based on Call Chains & Reach
        num_chains = len(call_chains)
        num_files = len(impacted_file_paths)

        if num_files == 0 and len(import_warnings) == 0 and len(breaking_apis) == 0:
            risk_score = "low"
        elif num_files == 0 and len(import_warnings) > 0:
            risk_score = "low"
        elif num_chains == 0 and num_files <= 2:
            risk_score = "medium"
        elif num_chains <= 3 or num_files <= 4:
            risk_score = "high"
        else:
            risk_score = "critical"

        return {
            "repository": repo.name,
            "package_name": pkg_clean,
            "upgrade_path": f"{from_version} -> {to_version}",
            "risk_score": risk_score,
            "direct_impacts": direct_impacts,
            "import_warnings": import_warnings,
            "affected_files": list(impacted_file_paths),
            "affected_modules": list(affected_modules),
            "call_chains": call_chains,
            "suggested_tests": suggested_tests,
            "breaking_apis_count": len(breaking_apis),
            "security_fixes_count": len(security_fixes)
        }
