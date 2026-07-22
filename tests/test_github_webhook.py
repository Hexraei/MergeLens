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

def test_github_webhook_pull_request(client: TestClient, db_session):
    payload = {
        "action": "opened",
        "number": 105,
        "pull_request": {
            "title": "Bump databases from 0.7.0 to 0.8.0",
            "head": {"sha": "abc1234def"},
            "diff_text": "-databases==0.7.0\n+databases==0.8.0\n"
        },
        "repository": {
            "full_name": "encode/databases",
            "clone_url": "https://github.com/encode/databases.git"
        }
    }

    response = client.post(
        "/webhook/github",
        json=payload,
        headers={"X-GitHub-Event": "pull_request"}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "success"
    assert data["repository"] == "encode/databases"
    assert data["pr_number"] == 105
    assert data["upgrades_analyzed"] == 1
    assert "check_run" in data
    assert "conclusion" in data["check_run"]

    # Verify AnalysisReport was stored in database
    report = db_session.query(models.AnalysisReport).filter(
        models.AnalysisReport.pr_number == 105
    ).first()
    assert report is not None
    assert report.dependency_name == "databases"
