from fastapi import APIRouter, Depends, HTTPException, Header, Request, status, BackgroundTasks
from sqlalchemy.orm import Session
import json

from app.config import settings
from app.database.db import get_db
from app.database import models

router = APIRouter(prefix="", tags=["Endpoints"])

@router.post("/webhook")
@router.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_github_event: str = Header("pull_request"),
    x_hub_signature_256: str = Header(None),
    db: Session = Depends(get_db)
):
    """
    Receives incoming GitHub webhooks for pull_request events, parses dependency changes,
    runs full impact analysis, consolidates reports, and emits PR comments and Check Runs.
    """
    payload = await request.body()
    try:
        body_json = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )

    print(f"[Webhook] Received GitHub event: {x_github_event}")

    if x_github_event == "pull_request":
        action = body_json.get("action")
        pr = body_json.get("pull_request", {})
        repo_data = body_json.get("repository", {})

        if action in ["opened", "synchronize", "reopened"]:
            pr_title = pr.get("title", "")
            pr_number = pr.get("number") or body_json.get("number", 1)
            repo_name = repo_data.get("full_name", "unknown/repo")
            clone_url = repo_data.get("clone_url", f"https://github.com/{repo_name}.git")
            head_sha = pr.get("head", {}).get("sha", "main_sha")

            # Look up or create repository
            repo = db.query(models.Repository).filter(models.Repository.name == repo_name).first()
            if not repo:
                repo = models.Repository(
                    name=repo_name,
                    git_url=clone_url,
                    indexing_status="completed"
                )
                db.add(repo)
                db.commit()
                db.refresh(repo)

            # 1. Parse Dependency Changes from PR Diff / Title
            from app.services.pr_parser import PRDependencyParser
            diff_text = pr.get("diff_text", "")
            parser = PRDependencyParser()
            upgrades = parser.parse_requirements_diff(diff_text)

            # Fallback regex for PR title if diff_text wasn't directly in payload
            if not upgrades and pr_title:
                match = re.search(
                    r"(?:bump|update)\s+([a-zA-Z0-9_\-\.]+)\s+from\s+([a-zA-Z0-9_\-\.]+)\s+to\s+([a-zA-Z0-9_\-\.]+)",
                    pr_title,
                    re.IGNORECASE
                )
                if match:
                    upgrades.append({
                        "package_name": match.group(1).lower(),
                        "from_version": match.group(2),
                        "to_version": match.group(3)
                    })

            if not upgrades:
                return {
                    "status": "ignored",
                    "reason": "No dependency upgrades detected in PR diff or title",
                    "pr_number": pr_number
                }

            # 2. Run Full Pipeline for each upgraded dependency
            from app.services.release_intel import ReleaseIntelligenceEngine
            from app.services.impact_engine import RepositoryImpactEngine
            from app.services.evidence import EvidenceBuilder
            from app.services.ai_reasoner import AIReasonerService
            from app.services.report_formatter import ReportFormatter
            from app.services.github_client import GitHubClient

            release_engine = ReleaseIntelligenceEngine(db)
            impact_engine = RepositoryImpactEngine(db)
            builder = EvidenceBuilder()
            reasoner = AIReasonerService()
            formatter = ReportFormatter()
            github_client = GitHubClient()

            markdown_reports = []
            highest_risk = "low"
            lowest_confidence = 100

            risk_order = {"low": 1, "medium": 2, "high": 3, "critical": 4}

            for up in upgrades:
                pkg_name = up["package_name"]
                from_ver = up["from_version"]
                to_ver = up["to_version"]

                rel_fact = await release_engine.analyze_package_upgrade(pkg_name, from_ver, to_ver)
                imp_report = await impact_engine.analyze_impact(repo.id, pkg_name, from_ver, to_ver, warn_on_unused_imports=True)
                ev_payload = builder.build_from_impact_report(imp_report, rel_fact)
                ai_synth = await reasoner.synthesize_review(ev_payload)

                md = formatter.format_pr_comment(
                    repository_name=repo.name,
                    pr_number=pr_number,
                    dependency_name=pkg_name,
                    from_version=from_ver,
                    to_version=to_ver,
                    ai_synthesis=ai_synth,
                    impact_summary=imp_report
                )
                markdown_reports.append(md)

                # Save report record
                db_report = models.AnalysisReport(
                    repository_id=repo.id,
                    pr_number=pr_number,
                    dependency_name=pkg_name,
                    from_version=from_ver,
                    to_version=to_ver,
                    priority_score=ai_synth.get("priority_score", 50),
                    risk_score=ai_synth.get("risk_score", "low"),
                    confidence_score=ai_synth.get("confidence_score", 85),
                    recommendation=ai_synth.get("recommendation", "Review before merging."),
                    report_data={"impact_summary": imp_report, "ai_synthesis": ai_synth}
                )
                db.add(db_report)

                # Track highest risk & lowest confidence
                curr_risk = ai_synth.get("risk_score", "low").lower()
                if risk_order.get(curr_risk, 1) > risk_order.get(highest_risk, 1):
                    highest_risk = curr_risk
                curr_conf = ai_synth.get("confidence_score", 85)
                if curr_conf < lowest_confidence:
                    lowest_confidence = curr_conf

            db.commit()

            # 3. Consolidate PR Markdown Comments
            consolidated_markdown = "\n\n---\n\n".join(markdown_reports)

            # 4. Post Consolidated Comment & Create Check Run via GitHubClient
            await github_client.post_pr_comment(repo_name, pr_number, consolidated_markdown)

            check_run_result = await github_client.create_check_run(
                repo_full_name=repo_name,
                head_sha=head_sha,
                name="MergeLens Dependency Impact Guard",
                risk_score=highest_risk,
                confidence_score=lowest_confidence,
                title=f"MergeLens Guard: Risk={highest_risk.upper()}, Confidence={lowest_confidence}%",
                summary=f"Analyzed {len(upgrades)} dependency update(s)."
            )

            return {
                "status": "success",
                "repository": repo_name,
                "pr_number": pr_number,
                "upgrades_analyzed": len(upgrades),
                "highest_risk": highest_risk,
                "check_run": check_run_result
            }

    return {"status": "ignored", "event": x_github_event}


@router.post("/analyze")
async def trigger_analysis(
    repo_name: str,
    pr_number: int,
    dependency_name: str,
    from_version: str,
    to_version: str,
    warn_on_unused_imports: bool = False,
    db: Session = Depends(get_db)
):
    """
    Triggers complete end-to-end dependency analysis:
    ReleaseIntel -> ImpactEngine -> EvidenceBuilder -> AIReasoner -> ReportFormatter -> DB
    """
    from app.services.release_intel import ReleaseIntelligenceEngine
    from app.services.impact_engine import RepositoryImpactEngine
    from app.services.evidence import EvidenceBuilder
    from app.services.ai_reasoner import AIReasonerService
    from app.services.report_formatter import ReportFormatter

    # 1. Look up or create repository
    repo = db.query(models.Repository).filter(models.Repository.name == repo_name).first()
    if not repo:
        repo = models.Repository(
            name=repo_name,
            git_url=f"https://github.com/{repo_name}.git",
            indexing_status="completed"
        )
        db.add(repo)
        db.commit()
        db.refresh(repo)

    # 2. Release Intelligence
    release_engine = ReleaseIntelligenceEngine(db)
    release_fact = await release_engine.analyze_package_upgrade(dependency_name, from_version, to_version)

    # 3. Repository Impact Analysis
    impact_engine = RepositoryImpactEngine(db)
    impact_report = await impact_engine.analyze_impact(
        repo.id, dependency_name, from_version, to_version, warn_on_unused_imports=warn_on_unused_imports
    )

    # 4. Build Evidence Payload
    builder = EvidenceBuilder()
    evidence_payload = builder.build_from_impact_report(impact_report, release_fact)

    # 5. AI Reasoning Synthesis
    reasoner = AIReasonerService()
    ai_synthesis = await reasoner.synthesize_review(evidence_payload)

    # 6. Format Markdown Report
    formatter = ReportFormatter()
    markdown_report = formatter.format_pr_comment(
        repository_name=repo.name,
        pr_number=pr_number,
        dependency_name=dependency_name,
        from_version=from_version,
        to_version=to_version,
        ai_synthesis=ai_synthesis,
        impact_summary=impact_report
    )

    # Combine full report data
    full_report_data = {
        "impact_summary": impact_report,
        "ai_synthesis": ai_synthesis,
        "formatted_markdown": markdown_report
    }

    report = models.AnalysisReport(
        repository_id=repo.id,
        pr_number=pr_number,
        dependency_name=dependency_name,
        from_version=from_version,
        to_version=to_version,
        priority_score=ai_synthesis.get("priority_score", 50),
        risk_score=ai_synthesis.get("risk_score", "low"),
        confidence_score=ai_synthesis.get("confidence_score", 85),
        recommendation=ai_synthesis.get("recommendation", "Review before merging."),
        report_data=full_report_data
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    return {
        "status": "success",
        "report_id": report.id,
        "priority_score": report.priority_score,
        "risk_score": report.risk_score,
        "confidence_score": report.confidence_score,
        "recommendation": report.recommendation,
        "formatted_markdown": markdown_report
    }


def run_indexing(repo_name: str, git_url: str):
    from app.database.db import SessionLocal
    from app.services.indexer import RepositoryIndexer
    db = SessionLocal()
    try:
        indexer = RepositoryIndexer(db)
        indexer.index_repository(repo_name, git_url)
    except Exception as e:
        print(f"[Background Indexer Exception] {e}")
    finally:
        db.close()


@router.post("/reindex")
async def trigger_reindex(
    repo_name: str,
    background_tasks: BackgroundTasks,
    git_url: str = None,
    db: Session = Depends(get_db)
):
    """
    Manually trigger re-indexing of a repository in the background.
    """
    if not git_url:
        git_url = f"https://github.com/{repo_name}.git"

    repo = db.query(models.Repository).filter(models.Repository.name == repo_name).first()
    if not repo:
        repo = models.Repository(
            name=repo_name,
            git_url=git_url,
            indexing_status="pending"
        )
        db.add(repo)
        db.commit()
        db.refresh(repo)

    repo.indexing_status = "indexing"
    db.commit()

    background_tasks.add_task(run_indexing, repo_name, git_url)

    return {
        "status": "indexing_started",
        "repo_name": repo.name,
        "message": "Repository indexing enqueued in background."
    }


@router.get("/report/{report_id}")
async def get_report(report_id: int, db: Session = Depends(get_db)):
    """
    Fetch a detailed analysis report by ID.
    """
    report = db.query(models.AnalysisReport).filter(models.AnalysisReport.id == report_id).first()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found"
        )
    return {
        "id": report.id,
        "repository_name": report.repository.name,
        "pr_number": report.pr_number,
        "dependency_name": report.dependency_name,
        "from_version": report.from_version,
        "to_version": report.to_version,
        "priority_score": report.priority_score,
        "risk_score": report.risk_score,
        "confidence_score": report.confidence_score,
        "recommendation": report.recommendation,
        "report_data": report.report_data,
        "created_at": report.created_at
    }


@router.get("/dashboard")
async def get_dashboard_metrics(db: Session = Depends(get_db)):
    """
    Return basic dashboard overview metrics.
    """
    total_repos = db.query(models.Repository).count()
    total_reports = db.query(models.AnalysisReport).count()
    total_dependencies = db.query(models.Dependency).count()
    total_symbols = db.query(models.Symbol).count()
    total_api_usages = db.query(models.ApiUsage).count()

    latest_reports = db.query(models.AnalysisReport).order_by(
        models.AnalysisReport.created_at.desc()
    ).limit(5).all()

    return {
        "metrics": {
            "total_repositories": total_repos,
            "total_analysis_reports": total_reports,
            "total_dependencies_tracked": total_dependencies,
            "total_symbols_indexed": total_symbols,
            "total_api_usages_indexed": total_api_usages
        },
        "latest_reports": [
            {
                "id": r.id,
                "repository": r.repository.name,
                "pr_number": r.pr_number,
                "dependency": r.dependency_name,
                "recommendation": r.recommendation,
                "created_at": r.created_at
            }
            for r in latest_reports
        ]
    }


@router.get("/release-intel")
async def get_release_intelligence(
    package_name: str,
    from_version: str,
    to_version: str,
    db: Session = Depends(get_db)
):
    """
    Fetch or extract Release Intelligence facts for a package version upgrade.
    """
    from app.services.release_intel import ReleaseIntelligenceEngine
    engine = ReleaseIntelligenceEngine(db)
    fact = await engine.analyze_package_upgrade(package_name, from_version, to_version)
    return {
        "id": fact.id,
        "package_name": fact.package_name,
        "from_version": fact.from_version,
        "to_version": fact.to_version,
        "breaking_apis": fact.breaking_apis_json,
        "behavior_changes": fact.behavior_changes_json,
        "security_fixes": fact.security_fixes_json,
        "created_at": fact.created_at
    }


@router.post("/generate-patch")
async def generate_migration_patch(
    repo_name: str,
    pr_number: int,
    dependency_name: str,
    from_version: str,
    to_version: str,
    test_scope: str = "full",
    db: Session = Depends(get_db)
):
    """
    Optional endpoint to synthesize and validate an automated code patch for breaking API changes.
    """
    from app.services.impact_engine import RepositoryImpactEngine
    from app.services.patch_synthesizer import PatchSynthesizer
    from app.services.patch_validator import PatchValidator
    from app.services.github_patch_publisher import GitHubPatchPublisher
    from app.services.github_client import GitHubClient

    # Look up repository
    repo = db.query(models.Repository).filter(models.Repository.name == repo_name).first()
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found. Please index it first.")

    # 1. Run Impact Engine
    impact_engine = RepositoryImpactEngine(db)
    impact_report = await impact_engine.analyze_impact(repo.id, dependency_name, from_version, to_version)

    # 2. Synthesize Patch
    synthesizer = PatchSynthesizer()
    patch_items = await synthesizer.generate_patch(".", impact_report)

    if not patch_items:
        return {
            "status": "skipped",
            "message": "No direct breaking API impacts found requiring code patches."
        }

    # 3. Sandboxed Patch Validation
    validator = PatchValidator()
    val_result = validator.validate_patch(
        repo_dir=".",
        patch_items=patch_items,
        test_scope=test_scope,
        target_test_files=impact_report.get("suggested_tests")
    )

    # 4. Self-Correction Attempt if validation failed
    if not val_result.get("success", False):
        print("[Patch Pipeline] Initial validation failed. Running self-correction pass...")
        corrected_items = await synthesizer.generate_correction_patch(patch_items, val_result.get("logs", ""))
        val_result_2 = validator.validate_patch(
            repo_dir=".",
            patch_items=corrected_items,
            test_scope=test_scope,
            target_test_files=impact_report.get("suggested_tests")
        )
        if val_result_2.get("success", False):
            patch_items = corrected_items
            val_result = val_result_2

    # 5. Format & Publish GitHub Comment
    publisher = GitHubPatchPublisher()
    patch_markdown = publisher.format_suggested_changes_comment(patch_items, val_result)

    github_client = GitHubClient()
    await github_client.post_pr_comment(repo_name, pr_number, patch_markdown)

    return {
        "status": "success",
        "repository": repo_name,
        "pr_number": pr_number,
        "patch_items": patch_items,
        "validation_result": val_result,
        "formatted_markdown": patch_markdown
    }
