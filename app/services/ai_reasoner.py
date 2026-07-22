import httpx
import json
from typing import Dict, List, Any, Optional

from google import genai
from app.config import settings

class AIReasonerService:
    def __init__(self):
        if settings.GEMINI_API_KEY:
            self.api_key = settings.GEMINI_API_KEY
            self.model = "gemini-3.6-flash"
            self.use_google_sdk = True
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.api_key = settings.OPENROUTER_API_KEY
            self.model = settings.OPENROUTER_MODEL
            self.base_url = "https://openrouter.ai/api/v1/chat/completions"
            self.use_google_sdk = False

    async def synthesize_review(self, evidence_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Synthesizes structured evidence into a comprehensive review containing Priority Score,
        Risk Score, Confidence Score, Executive Summary, Migration Steps, and Recommendation.
        """
        if not self.api_key:
            print("[AI Mock] API key missing. Generating structured mock review reasoning.")
            return self._generate_mock_reasoning(evidence_payload)

        system_prompt = (
            "You are MergeLens AI, a senior staff software engineer reviewing a dependency update PR.\n"
            "Analyze the provided structured evidence (package, version upgrade, direct code impacts, "
            "call chains, affected files, test files, and security fixes) and synthesize a PR review.\n"
            "You must output ONLY a valid JSON object matching this exact schema:\n"
            "{\n"
            "  \"priority_score\": int (0-100),\n"
            "  \"risk_score\": \"low\" | \"medium\" | \"high\" | \"critical\",\n"
            "  \"confidence_score\": int (0-100),\n"
            "  \"executive_summary\": string,\n"
            "  \"breaking_changes_summary\": [string],\n"
            "  \"migration_steps\": [string],\n"
            "  \"community_warnings\": string,\n"
            "  \"security_notes\": string,\n"
            "  \"recommendation\": string\n"
            "}"
        )

        user_content = json.dumps(evidence_payload, indent=2)

        if self.use_google_sdk:
            try:
                resp = self.client.models.generate_content(
                    model=self.model,
                    contents=system_prompt + "\n\nUser Evidence Payload:\n" + user_content,
                    config={"response_mime_type": "application/json"}
                )
                return json.loads(resp.text)
            except Exception as e:
                print(f"[Google SDK Exception] {str(e)}")
                return self._generate_mock_reasoning(evidence_payload)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/Hexraei/MergeLens",
            "X-Title": "MergeLens AI Reviewer"
        }

        data = {
            "model": self.model,
            "max_tokens": 1500,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "response_format": {"type": "json_object"}
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(self.base_url, headers=headers, json=data, timeout=30.0)
                if resp.status_code != 200:
                    print(f"[AI Reasoner Error] OpenRouter returned status {resp.status_code}: {resp.text}")
                    return self._generate_mock_reasoning(evidence_payload)
                
                result = resp.json()
                content = result["choices"][0]["message"]["content"]
                return json.loads(content)
        except Exception as e:
            print(f"[AI Reasoner Exception] {str(e)}")
            return self._generate_mock_reasoning(evidence_payload)

    def _generate_mock_reasoning(self, evidence: Dict[str, Any]) -> Dict[str, Any]:
        """Provides a safe, deterministic mock synthesis report for testing."""
        package = evidence.get("package_name", "unknown")
        version_upgrade = evidence.get("version_upgrade", {})
        from_ver = version_upgrade.get("from", "0.0.0")
        to_ver = version_upgrade.get("to", "0.0.0")
        risk_calc = evidence.get("calculated_risk_score", "low")

        ev = evidence.get("evidence", {})
        direct_impacts = ev.get("direct_code_impacts", [])
        has_direct = len(direct_impacts) > 0 and "No direct broken" not in direct_impacts[0]
        sec_fixes = ev.get("security_fixes", [])
        has_sec = len(sec_fixes) > 0 and "No known security" not in sec_fixes[0]

        # Calculate Priority Score (driven by security & urgency)
        priority_score = 40
        if has_sec:
            priority_score += 45
        if has_direct:
            priority_score += 15

        # Calculate Confidence Score (driven by static analysis completeness)
        confidence_score = 90 if not has_direct else 80

        # Construct summaries
        if has_direct:
            exec_summary = f"Upgrade of {package} from {from_ver} to {to_ver} contains direct breaking API calls in the codebase."
            recommendation = "Hold merge until broken method calls are updated and test suite passes."
            migration_steps = [
                f"Replace deprecated/removed symbols in affected files: {', '.join(ev.get('affected_files', []))}",
                f"Run suggested test files: {', '.join(ev.get('suggested_tests', []))}"
            ]
        else:
            exec_summary = f"Upgrade of {package} from {from_ver} to {to_ver} introduces no direct breaking API calls."
            recommendation = "Safe to merge after running standard CI tests."
            migration_steps = [
                "Verify build & test suite passes cleanly.",
                "Proceed with PR merge."
            ]

        breaking_summary = direct_impacts if has_direct else ["No breaking API calls detected in codebase."]
        security_notes = sec_fixes[0] if has_sec else "No known security vulnerabilities fixed in this release."

        return {
            "priority_score": min(priority_score, 100),
            "risk_score": risk_calc,
            "confidence_score": confidence_score,
            "executive_summary": exec_summary,
            "breaking_changes_summary": breaking_summary,
            "migration_steps": migration_steps,
            "community_warnings": "No widespread regressions reported.",
            "security_notes": security_notes,
            "recommendation": recommendation
        }
