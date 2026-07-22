import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import models
from app.database.db import SessionLocal

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def test_full_analyze_pipeline(client: TestClient, db_session):
    response = client.post(
        "/analyze",
        params={
            "repo_name": "encode/databases",
            "pr_number": 101,
            "dependency_name": "databases",
            "from_version": "0.7.0",
            "to_version": "0.8.0",
            "warn_on_unused_imports": True
        }
    )

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "success"
    assert "report_id" in data
    assert "priority_score" in data
    assert "risk_score" in data
    assert "formatted_markdown" in data

    markdown = data["formatted_markdown"]
    assert "MergeLens Dependency Impact Review" in markdown
    assert "`databases` upgrade `0.7.0` &rarr; `0.8.0`" in markdown

    # Verify Report record in database
    report = db_session.query(models.AnalysisReport).filter(
        models.AnalysisReport.id == data["report_id"]
    ).first()
    assert report is not None
    assert report.repository.name == "encode/databases"
    assert report.pr_number == 101
