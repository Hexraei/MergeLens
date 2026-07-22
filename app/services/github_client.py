import httpx
from typing import Dict, List, Any, Optional

from app.config import settings

class GitHubClient:
    def __init__(self, token: Optional[str] = None):
        self.token = token or settings.GITHUB_TOKEN
        self.base_url = "https://api.github.com"

    async def post_pr_comment(
        self, repo_full_name: str, pr_number: int, comment_body: str
    ) -> bool:
        """
        Posts a markdown review comment to a GitHub PR (Issue comments API).
        Fallback to mock printing if no token is configured.
        """
        if not self.token:
            print(f"[GitHub Client Mock] Emitting PR comment to {repo_full_name}#{pr_number}:\n{comment_body[:200]}...\n")
            return True

        url = f"{self.base_url}/repos/{repo_full_name}/issues/{pr_number}/comments"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }
        payload = {"body": comment_body}

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, headers=headers, json=payload, timeout=15.0)
                if resp.status_code in (200, 201):
                    print(f"[GitHub Client] Comment posted successfully to {repo_full_name}#{pr_number}")
                    return True
                else:
                    print(f"[GitHub Client Error] HTTP {resp.status_code} posting comment: {resp.text}")
                    return False
        except Exception as e:
            print(f"[GitHub Client Exception] {e}")
            return False

    async def create_check_run(
        self,
        repo_full_name: str,
        head_sha: str,
        name: str,
        risk_score: str,
        confidence_score: int,
        title: str,
        summary: str
    ) -> Dict[str, Any]:
        """
        Creates a GitHub Check Run.
        Sets conclusion to 'action_required' if risk is HIGH/CRITICAL and confidence >= 75%.
        If confidence < 75%, sets conclusion to 'neutral' to prevent false positive CI blocks.
        """
        risk_clean = risk_score.lower().strip()
        if risk_clean in ("high", "critical"):
            if confidence_score >= 75:
                conclusion = "action_required"
            else:
                conclusion = "neutral"
        else:
            conclusion = "success"

        if not self.token:
            print(
                f"[GitHub Client Mock] Check Run '{name}' for {head_sha[:7]}: "
                f"risk={risk_score}, confidence={confidence_score}% -> conclusion={conclusion}"
            )
            return {"status": "completed", "conclusion": conclusion}

        url = f"{self.base_url}/repos/{repo_full_name}/check-runs"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }
        payload = {
            "name": name,
            "head_sha": head_sha,
            "status": "completed",
            "conclusion": conclusion,
            "output": {
                "title": title,
                "summary": summary
            }
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, headers=headers, json=payload, timeout=15.0)
                if resp.status_code in (200, 201):
                    print(f"[GitHub Client] Check Run '{name}' created with conclusion={conclusion}")
                    return resp.json()
                else:
                    print(f"[GitHub Client Error] HTTP {resp.status_code} creating check run: {resp.text}")
                    return {"status": "error", "conclusion": conclusion}
        except Exception as e:
            print(f"[GitHub Client Exception] {e}")
            return {"status": "error", "conclusion": conclusion}
