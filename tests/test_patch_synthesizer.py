import pytest
from app.services.patch_synthesizer import PatchSynthesizer

@pytest.mark.asyncio
async def test_patch_synthesizer():
    synthesizer = PatchSynthesizer()

    mock_impact_report = {
        "package_name": "databases",
        "upgrade_path": "0.7.0 -> 0.8.0",
        "direct_impacts": [
            {
                "file_path": "app/db.py",
                "line_number": 5,
                "imported_symbol": "Database.connect",
                "description": "Database.connect removed in version 0.8.0"
            }
        ]
    }

    patches = await synthesizer.generate_patch(".", mock_impact_report)
    assert len(patches) == 1
    assert patches[0]["file_path"] == "app/db.py"
    assert "full_patched_file" in patches[0]

    # Test correction patch
    corrected = await synthesizer.generate_correction_patch(patches, "Pytest assertion error")
    assert len(corrected) == 1
    assert "SELF-CORRECTION" in corrected[0]["full_patched_file"]
