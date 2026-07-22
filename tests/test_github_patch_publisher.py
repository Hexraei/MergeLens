from app.services.github_patch_publisher import GitHubPatchPublisher

def test_github_patch_publisher():
    publisher = GitHubPatchPublisher()

    mock_items = [
        {
            "file_path": "app/db.py",
            "original_snippet": "db.connect(url)",
            "replacement_snippet": "db.connect(url, timeout=30)"
        }
    ]
    mock_val = {"success": True}

    md = publisher.format_suggested_changes_comment(mock_items, mock_val)

    assert "## MergeLens Automated Migration Patch" in md
    assert "PASSED (All Tests Verified)" in md
    assert "`app/db.py`" in md
    assert "- db.connect(url)" in md
    assert "+ db.connect(url, timeout=30)" in md
