from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app"] == "MergeLens"

def test_dashboard_endpoint():
    response = client.get("/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert "metrics" in data
    assert "latest_reports" in data

def test_webhook_ignored():
    response = client.post(
        "/webhook",
        headers={"x-github-event": "ping"},
        json={"zen": "Practicality beats purity."}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "pong"

def test_manual_analysis_and_report():
    # Trigger a manual analysis
    analyze_resp = client.post(
        "/analyze",
        params={
            "repo_name": "test/repo",
            "pr_number": 42,
            "dependency_name": "requests",
            "from_version": "2.31.0",
            "to_version": "2.32.0"
        }
    )
    assert analyze_resp.status_code == 200
    data = analyze_resp.json()
    assert data["status"] == "success"
    report_id = data["report_id"]

    # Retrieve the generated report
    report_resp = client.get(f"/report/{report_id}")
    assert report_resp.status_code == 200
    report_data = report_resp.json()
    assert report_data["dependency_name"] == "requests"
    assert report_data["from_version"] == "2.31.0"
    assert report_data["to_version"] == "2.32.0"
