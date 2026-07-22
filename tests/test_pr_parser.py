from app.services.pr_parser import PRDependencyParser

def test_pr_dependency_parser():
    parser = PRDependencyParser()

    diff_text = (
        "--- a/requirements.txt\n"
        "+++ b/requirements.txt\n"
        "@@ -1,4 +1,4 @@\n"
        "-databases==0.7.0\n"
        "+databases==0.8.0\n"
        "-requests==2.30.0\n"
        "+requests==2.31.0\n"
        " fastapi==0.100.0\n"
    )

    upgrades = parser.parse_requirements_diff(diff_text)
    assert len(upgrades) == 2

    pkg_names = {u["package_name"] for u in upgrades}
    assert "databases" in pkg_names
    assert "requests" in pkg_names

    db_up = next(u for u in upgrades if u["package_name"] == "databases")
    assert db_up["from_version"] == "0.7.0"
    assert db_up["to_version"] == "0.8.0"
