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

def test_generate_patch_pipeline(client: TestClient, db_session):
    response = client.post(
        "/generate-patch",
        params={
            "repo_name": "encode/databases",
            "pr_number": 101,
            "dependency_name": "databases",
            "from_version": "0.7.0",
            "to_version": "0.8.0",
            "test_scope": "targeted"
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    if data["status"] == "success":
        assert "patch_items" in data
        assert "validation_result" in data
        assert "formatted_markdown" in data
