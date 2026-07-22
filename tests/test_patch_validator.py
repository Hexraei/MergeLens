import os
import pytest
from app.services.patch_validator import PatchValidator

def test_patch_validator_ast_pass():
    validator = PatchValidator()

    valid_patch = [
        {
            "file_path": "app/sample.py",
            "original_snippet": "x = 1",
            "replacement_snippet": "x = 2",
            "full_patched_file": "def foo():\n    return 2\n"
        }
    ]

    res = validator.validate_patch(".", valid_patch, test_scope="targeted")
    assert "success" in res
    assert res.get("error_type") != "SyntaxError"

def test_patch_validator_ast_syntax_error():
    validator = PatchValidator()

    invalid_patch = [
        {
            "file_path": "app/broken.py",
            "original_snippet": "x = 1",
            "replacement_snippet": "def broken_code(",
            "full_patched_file": "def broken_code(\n"
        }
    ]

    res = validator.validate_patch(".", invalid_patch, test_scope="targeted")
    assert res["success"] is False
    assert res["error_type"] == "SyntaxError"
