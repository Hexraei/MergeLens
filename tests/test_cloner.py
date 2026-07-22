import os
import pytest
from app.services.cloner import GitCloner

def test_cloner_lifecycle():
    cloner = GitCloner()
    # Use a small known repo
    test_repo = "https://github.com/hexraei/mergelens.git"
    
    local_path = None
    try:
        local_path = cloner.clone_repo(test_repo)
        assert os.path.exists(local_path)
        assert os.path.isdir(local_path)
        
        # Verify it has files we expect
        readme_path = os.path.join(local_path, "README.md")
        assert os.path.exists(readme_path)
        
    finally:
        if local_path:
            cloner.cleanup(local_path)
            assert not os.path.exists(local_path)
