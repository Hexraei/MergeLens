import os
import shutil
import tempfile
import pytest
from sqlalchemy.orm import Session
from unittest.mock import patch

from app.database import models
from app.database.db import SessionLocal
from app.services.indexer import RepositoryIndexer

@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture
def mock_repo_directory():
    # Create a temporary directory with mock codebase files
    temp_dir = tempfile.mkdtemp(prefix="mock_repo_")
    
    # 1. requirements.txt
    with open(os.path.join(temp_dir, "requirements.txt"), "w", encoding="utf-8") as f:
        f.write("fastapi==0.110.0\npandas>=2.0.0\n")
        
    # 2. app/ package
    app_dir = os.path.join(temp_dir, "app")
    os.makedirs(app_dir)
    
    # 3. app/__init__.py
    with open(os.path.join(app_dir, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("")
        
    # 4. app/main.py
    main_code = """
import pandas as pd
from fastapi import FastAPI
from app.utils import helper_func

app = FastAPI()

class MainHandler:
    \"\"\"Main handler class\"\"\"
    def handle(self) -> None:
        helper_func()
        pd.read_csv("data.csv")
"""
    with open(os.path.join(app_dir, "main.py"), "w", encoding="utf-8") as f:
        f.write(main_code)
        
    # 5. app/utils.py
    utils_code = """
def helper_func() -> str:
    \"\"\"Helper utility function\"\"\"
    print("Helping")
    return "done"
"""
    with open(os.path.join(app_dir, "utils.py"), "w", encoding="utf-8") as f:
        f.write(utils_code)

    yield temp_dir
    
    # Clean up
    shutil.rmtree(temp_dir)

@patch("app.services.cloner.GitCloner.clone_repo")
@patch("app.services.cloner.GitCloner.cleanup")
def test_indexer_pipeline(mock_cleanup, mock_clone_repo, mock_repo_directory, db_session: Session):
    # Mock clone_repo to return our local test directory path
    mock_clone_repo.return_value = mock_repo_directory
    
    indexer = RepositoryIndexer(db_session)
    
    repo = indexer.index_repository("test/mock-repo", "https://github.com/test/mock-repo.git")
    
    # Assert repository record state
    assert repo.indexing_status == "completed"
    assert repo.dependency_graph_json is not None
    assert repo.call_graph_json is not None
    
    # Assert dependencies indexed
    dependencies = db_session.query(models.Dependency).filter(models.Dependency.repository_id == repo.id).all()
    assert len(dependencies) == 2
    dep_names = [d.name for d in dependencies]
    assert "fastapi" in dep_names
    assert "pandas" in dep_names
    
    # Assert symbols indexed
    symbols = db_session.query(models.Symbol).filter(models.Symbol.repository_id == repo.id).all()
    # Expect: MainHandler (class), MainHandler.handle (method), helper_func (function)
    assert len(symbols) == 3
    sym_types = {s.name: s.type for s in symbols}
    assert sym_types["MainHandler"] == "class"
    assert sym_types["MainHandler.handle"] == "method"
    assert sym_types["helper_func"] == "function"
    
    # Verify metadata JSON docstring
    handler_sym = [s for s in symbols if s.name == "MainHandler"][0]
    assert handler_sym.metadata_json["docstring"] == "Main handler class"
    
    helper_sym = [s for s in symbols if s.name == "helper_func"][0]
    assert helper_sym.metadata_json["docstring"] == "Helper utility function"
    assert helper_sym.metadata_json["return_type"] == "str"

    # Assert external API usages indexed
    api_usages = db_session.query(models.ApiUsage).filter(models.ApiUsage.repository_id == repo.id).all()
    # Expect calls to: FastAPI() (fastapi), read_csv() (pandas)
    # Note: helper_func call is within the repo so it's not indexed as external API usage (or it is if not filtered).
    # In indexer.py, we extract all api calls and parse. Let's inspect them:
    resolved_usages = [u.package_name for u in api_usages]
    assert "fastapi" in resolved_usages
    assert "pandas" in resolved_usages
    
    # Verify mock cleanup was called
    mock_cleanup.assert_called_once_with(mock_repo_directory)
