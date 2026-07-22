import os
import shutil
import subprocess
import tempfile
import stat
from typing import Optional

class GitCloner:
    def __init__(self, base_temp_dir: Optional[str] = None):
        if base_temp_dir is None:
            # Use a local temp folder or the system temp
            self.base_temp_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../temp"))
        else:
            self.base_temp_dir = os.path.abspath(base_temp_dir)
        
        os.makedirs(self.base_temp_dir, exist_ok=True)

    def _normalize_git_url(self, repo_url: str) -> str:
        """Normalizes GitHub shortnames (owner/repo) to full HTTPS git URLs."""
        if not repo_url.startswith("http://") and not repo_url.startswith("https://") and not repo_url.startswith("git@"):
            return f"https://github.com/{repo_url}.git"
        return repo_url

    def clone_repo(self, repo_url: str) -> str:
        """
        Clones a git repository with depth=1 to a unique temporary directory.
        Returns the absolute path to the cloned repository.
        """
        normalized_url = self._normalize_git_url(repo_url)
        # Create a unique directory name inside base_temp_dir
        temp_dir = tempfile.mkdtemp(prefix="repo_", dir=self.base_temp_dir)
        
        print(f"[GitCloner] Cloning {normalized_url} to {temp_dir}...")
        
        # Execute shallow clone
        cmd = ["git", "clone", "--depth", "1", normalized_url, temp_dir]
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            print(f"[GitCloner] Cloning completed successfully.")
            return temp_dir
        except subprocess.CalledProcessError as e:
            # Attempt to clean up directory if clone failed
            self.cleanup(temp_dir)
            raise RuntimeError(f"Git clone failed: {e.stderr.strip()}") from e

    def cleanup(self, local_path: str):
        """Recursively deletes the local directory, removing read-only flags first."""
        if not os.path.exists(local_path):
            return

        def remove_readonly(func, path, excinfo):
            # Clear the read-only bit and re-run the removal function
            os.chmod(path, stat.S_IWRITE)
            func(path)

        print(f"[GitCloner] Cleaning up directory {local_path}...")
        try:
            shutil.rmtree(local_path, onerror=remove_readonly)
        except Exception as e:
            print(f"[GitCloner Error] Failed to delete {local_path}: {e}")
