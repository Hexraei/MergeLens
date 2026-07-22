import os
import re
import json
import datetime
from typing import List, Dict, Any, Optional
import networkx as nx
from sqlalchemy.orm import Session

from app.database import models
from app.services.cloner import GitCloner
from app.indexer.parser import PythonParser
from app.indexer.graph import DependencyGraph, CallGraph

class RepositoryIndexer:
    def __init__(self, db: Session):
        self.db = db
        self.cloner = GitCloner()
        self.parser = PythonParser()

    def _parse_requirements_txt(self, content: str) -> List[Dict[str, str]]:
        """Parses requirements.txt into a list of dictionaries with name and version."""
        deps = []
        for line in content.splitlines():
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#") or line.startswith("-r"):
                continue
            # Simple regex to split package name and versions/constraints
            match = re.match(r"^([a-zA-Z0-9_\-\[\]]+)\s*(?:==|>=|<=|>|<|~=)?\s*([0-9a-zA-Z\.\-\*]+)?", line)
            if match:
                pkg_name = match.group(1).strip()
                # Remove extras like [security]
                pkg_name = re.sub(r'\[.*\]', '', pkg_name)
                version = match.group(2).strip() if match.group(2) else "latest"
                deps.append({"name": pkg_name.lower(), "version": version})
        return deps

    def _convert_path_to_module(self, repo_path: str, file_path: str) -> str:
        """Converts a local file path inside the repo to a Python module name."""
        rel_path = os.path.relpath(file_path, repo_path)
        base_name, _ = os.path.splitext(rel_path)
        # Convert path separators to dots
        parts = base_name.split(os.sep)
        # If it ends with __init__, drop it (e.g. package/__init__.py -> package)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts)

    def index_repository(self, repo_name: str, git_url: str) -> models.Repository:
        """
        Executes the full indexing pipeline: shallow clone, dependency parsing,
        syntactic parsing (AST symbols & api usages), call/import graph construction,
        and database storage.
        """
        # Look up or create repository record
        repo = self.db.query(models.Repository).filter(models.Repository.name == repo_name).first()
        if not repo:
            repo = models.Repository(
                name=repo_name,
                git_url=git_url,
                indexing_status="pending"
            )
            self.db.add(repo)
            self.db.commit()
            self.db.refresh(repo)

        repo.indexing_status = "indexing"
        self.db.commit()

        local_path = None
        try:
            # Step 1: Clone repo
            local_path = self.cloner.clone_repo(git_url)

            # Clear old indexed records for this repo in case of re-indexing
            self.db.query(models.Dependency).filter(models.Dependency.repository_id == repo.id).delete()
            self.db.query(models.Symbol).filter(models.Symbol.repository_id == repo.id).delete()
            self.db.query(models.ApiUsage).filter(models.ApiUsage.repository_id == repo.id).delete()
            self.db.commit()

            # Step 2: Parse tracked dependencies (requirements.txt)
            req_path = os.path.join(local_path, "requirements.txt")
            if os.path.exists(req_path):
                with open(req_path, "r", encoding="utf-8", errors="ignore") as f:
                    req_content = f.read()
                parsed_deps = self._parse_requirements_txt(req_content)
                for dep in parsed_deps:
                    db_dep = models.Dependency(
                        repository_id=repo.id,
                        name=dep["name"],
                        version=dep["version"],
                        file_path="requirements.txt"
                    )
                    self.db.add(db_dep)
                self.db.commit()

            # Initialize graphs
            dep_graph = DependencyGraph()
            call_graph = CallGraph()

            # Keep a mapping of file path -> parsed alias map for call graph resolution
            file_alias_maps = {}
            # Keep a mapping of module name -> file path for lookups
            module_file_map = {}

            # Step 3: Scan and parse Python files
            py_files = []
            for root, _, files in os.walk(local_path):
                # Ignore common virtual envs, git, and tox folders
                if any(x in root for x in [".git", "venv", ".tox", "__pycache__"]):
                    continue
                for file in files:
                    if file.endswith(".py"):
                        full_path = os.path.join(root, file)
                        py_files.append(full_path)
                        
                        module_name = self._convert_path_to_module(local_path, full_path)
                        module_file_map[module_name] = os.path.relpath(full_path, local_path)
                        dep_graph.add_module(module_name)

            print(f"[Indexer] Found {len(py_files)} Python files to index.")

            # First Pass: Extract symbols, imports, and build dependency graph
            for file_path in py_files:
                rel_path = os.path.relpath(file_path, local_path)
                module_name = self._convert_path_to_module(local_path, file_path)

                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    source_code = f.read()

                tree = self.parser.parse_code(source_code.encode("utf-8"))

                # Index Symbols
                symbols = self.parser.extract_symbols(tree, source_code)
                for sym in symbols:
                    db_sym = models.Symbol(
                        repository_id=repo.id,
                        name=sym["name"],
                        type=sym["type"],
                        file_path=rel_path,
                        start_line=sym["start_line"],
                        end_line=sym["end_line"],
                        metadata_json=sym["metadata"]
                    )
                    self.db.add(db_sym)

                    # Populate function nodes in CallGraph
                    call_graph.add_function(sym["name"], rel_path)

                # Parse Imports & Aliases
                imports, alias_map = self.parser.extract_imports_and_aliases(tree, source_code)
                file_alias_maps[file_path] = alias_map

                # Add dependencies to graph
                for imp in imports:
                    imported_module = imp.get("module")
                    if imported_module:
                        # Add module-level dependency in graph
                        dep_graph.add_dependency(module_name, imported_module)

            self.db.commit()

            # Second Pass: Extract API calls and resolve them
            for file_path in py_files:
                rel_path = os.path.relpath(file_path, local_path)
                alias_map = file_alias_maps.get(file_path, {})

                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    source_code = f.read()

                tree = self.parser.parse_code(source_code.encode("utf-8"))

                # API calls
                calls = self.parser.extract_api_calls(tree, source_code, alias_map)
                
                # Group calls by line to save multiple calls on same line or verify
                for call in calls:
                    resolved = call["resolved_name"]
                    parts = resolved.split(".")
                    package = parts[0]
                    symbol = ".".join(parts[1:]) if len(parts) > 1 else None

                    # Index external usage
                    db_usage = models.ApiUsage(
                        repository_id=repo.id,
                        package_name=package.lower(),
                        imported_symbol=symbol,
                        file_path=rel_path,
                        line_number=call["line"]
                    )
                    self.db.add(db_usage)

            self.db.commit()

            # Step 4: Serialize and save graphs
            repo.dependency_graph_json = nx.node_link_data(dep_graph.graph)
            repo.call_graph_json = nx.node_link_data(call_graph.graph)
            
            repo.indexing_status = "completed"
            repo.last_indexed_at = datetime.datetime.utcnow()
            self.db.commit()
            print(f"[Indexer] Indexing completed successfully for {repo_name}.")

        except Exception as e:
            repo.indexing_status = "failed"
            self.db.commit()
            print(f"[Indexer Error] Indexing failed for {repo_name}: {str(e)}")
            raise e
        finally:
            # Step 5: Cleanup cloned files
            if local_path:
                self.cloner.cleanup(local_path)

        return repo
