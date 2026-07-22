import pytest
from app.services.github_client import GitHubClient

@pytest.mark.asyncio
async def test_github_client_check_run_gating():
    client = GitHubClient()  # Token is None -> Mock mode

    # High risk, high confidence -> action_required
    res1 = await client.create_check_run(
        "encode/databases", "sha123", "Guard", "HIGH", 85, "Title", "Summary"
    )
    assert res1["conclusion"] == "action_required"

    # Critical risk, high confidence -> action_required
    res2 = await client.create_check_run(
        "encode/databases", "sha123", "Guard", "CRITICAL", 90, "Title", "Summary"
    )
    assert res2["conclusion"] == "action_required"

    # High risk, LOW confidence (< 75%) -> neutral (prevent false positive CI block)
    res3 = await client.create_check_run(
        "encode/databases", "sha123", "Guard", "HIGH", 60, "Title", "Summary"
    )
    assert res3["conclusion"] == "neutral"

    # Low risk, high confidence -> success
    res4 = await client.create_check_run(
        "encode/databases", "sha123", "Guard", "LOW", 90, "Title", "Summary"
    )
    assert res4["conclusion"] == "success"
