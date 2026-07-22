import pytest
import networkx as nx
from unittest.mock import patch, AsyncMock
from sqlalchemy.orm import Session

from app.database import models
from app.database.db import SessionLocal
from app.services.impact_engine import RepositoryImpactEngine

@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture
def sample_repo(db_session: Session):
    # Clean up existing record if present to avoid UNIQUE constraint errors
    existing = db_session.query(models.Repository).filter(models.Repository.name == "test/impact-repo").first()
    if existing:
        db_session.delete(existing)
        db_session.commit()

    # 1. Create Repository
    repo = models.Repository(
        name="test/impact-repo",
        git_url="https://github.com/test/impact-repo.git",
        indexing_status="completed"
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    # 2. Add Symbols
    sym1 = models.Symbol(
        repository_id=repo.id,
        name="main_func",
        type="function",
        file_path="app/main.py",
        start_line=1,
        end_line=10,
        metadata_json={"docstring": "main"}
    )
    sym2 = models.Symbol(
        repository_id=repo.id,
        name="handler_func",
        type="function",
        file_path="app/handler.py",
        start_line=1,
        end_line=10,
        metadata_json={"docstring": "handler"}
    )
    sym3 = models.Symbol(
        repository_id=repo.id,
        name="test_handler",
        type="function",
        file_path="tests/test_handler.py",
        start_line=1,
        end_line=10,
        metadata_json={"docstring": "test"}
    )
    db_session.add_all([sym1, sym2, sym3])

    # 3. Add ApiUsage
    usage1 = models.ApiUsage(
        repository_id=repo.id,
        package_name="databases",
        imported_symbol="Database.connect",
        file_path="app/handler.py",
        line_number=5
    )
    usage2 = models.ApiUsage(
        repository_id=repo.id,
        package_name="databases",
        imported_symbol="Database",
        file_path="app/unused_import.py",
        line_number=1
    )
    db_session.add_all([usage1, usage2])

    # 4. Construct Call Graph & Dependency Graph
    call_g = nx.DiGraph()
    call_g.add_edge("main_func", "handler_func")

    dep_g = nx.DiGraph()
    dep_g.add_edge("app.main", "app.handler")

    repo.call_graph_json = nx.node_link_data(call_g)
    repo.dependency_graph_json = nx.node_link_data(dep_g)
    db_session.commit()

    return repo

@pytest.mark.asyncio
async def test_repository_impact_engine(db_session: Session, sample_repo):
    engine = RepositoryImpactEngine(db_session)

    mock_release_fact = models.ReleaseFact(
        id=1,
        package_name="databases",
        from_version="0.7.0",
        to_version="0.8.0",
        breaking_apis_json=[
            {"name": "Database.connect", "change_type": "removed", "description": "connect method dropped"}
        ],
        behavior_changes_json=[],
        security_fixes_json=[]
    )

    with patch.object(engine.release_intel, "analyze_package_upgrade", new_callable=AsyncMock) as mock_analyze:
        mock_analyze.return_value = mock_release_fact

        # Test without import warnings
        report = await engine.analyze_impact(
            sample_repo.id, "databases", "0.7.0", "0.8.0", warn_on_unused_imports=False
        )

        assert report["repository"] == "test/impact-repo"
        assert report["package_name"] == "databases"
        assert len(report["direct_impacts"]) == 1
        assert report["direct_impacts"][0]["file_path"] == "app/handler.py"
        assert report["direct_impacts"][0]["imported_symbol"] == "Database.connect"
        assert "app/handler.py" in report["affected_files"]
        assert len(report["import_warnings"]) == 0
        assert len(report["suggested_tests"]) > 0

        # Test with import warnings toggle enabled
        report_warn = await engine.analyze_impact(
            sample_repo.id, "databases", "0.7.0", "0.8.0", warn_on_unused_imports=True
        )

        assert len(report_warn["import_warnings"]) == 1
        assert report_warn["import_warnings"][0]["file_path"] == "app/unused_import.py"
