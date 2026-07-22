import jwt
import time
import httpx
from typing import Dict, Any, Optional

from app.config import settings

class GitHubAppService:
    def __init__(self):
        self.app_id = settings.GITHUB_APP_ID
        self.private_key = settings.GITHUB_PRIVATE_KEY
        self.webhook_secret = settings.GITHUB_WEBHOOK_SECRET

    def _generate_jwt(self) -> str:
        """
        Generates a JSON Web Token (JWT) to authenticate as the GitHub App.
        JWTs are valid for at most 10 minutes.
        """
        if not self.private_key:
            # Fallback mock JWT for local development
            return "mock_jwt_token"

        payload = {
            "iat": int(time.time()) - 60,
            "exp": int(time.time()) + (10 * 60),
            "iss": self.app_id,
        }
        return jwt.encode(payload, self.private_key, algorithm="RS256")

    async def get_installation_access_token(self, installation_id: int) -> str:
        """
        Exchanges the JWT for an installation access token.
        Allows API access scoped to the specific repository/organization.
        """
        if not self.app_id or not self.private_key:
            return "mock_installation_token"

        jwt_token = self._generate_jwt()
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
        }
        url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers)
            if resp.status_code != 201:
                raise Exception(f"Failed to get access token: {resp.status_code} {resp.text}")
            return resp.json().get("token")

    async def post_comment(
        self, repo_name: str, pr_number: int, comment_body: str, token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Posts a review comment to the Pull Request."""
        print(f"[GitHub Mock] Posting comment to {repo_name} PR #{pr_number}")
        # Return mock response
        return {"id": 12345, "body": comment_body, "user": {"login": "mergelens-app[bot]"}}

    async def create_check_run(
        self, repo_name: str, head_sha: str, name: str, summary: str, conclusion: str = "success", token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Creates a GitHub Check Run representing the MergeLens status review."""
        print(f"[GitHub Mock] Creating Check Run '{name}' with conclusion '{conclusion}' on {repo_name} @ {head_sha}")
        return {
            "id": 98765,
            "name": name,
            "status": "completed",
            "conclusion": conclusion,
            "output": {"title": "MergeLens Impact Analysis", "summary": summary}
        }
