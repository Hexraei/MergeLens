# MergeLens

MergeLens is an automated pull request intelligence platform that protects software codebases from breaking changes introduced by third-party dependency updates.

## Problem

Automated dependency update tools like Dependabot or Renovate notify development teams whenever a new library version is released. However, these tools operate without awareness of your codebase's internal structure. They open pull requests without indicating whether the upgrade will break existing functionality, which specific method calls will fail, or what code changes are necessary to adapt to the new version. As a result, engineering teams face significant overhead manually reviewing release notes, or they leave dependency pull requests unmerged, accumulating technical debt and exposing applications to security vulnerabilities.

## Solution

MergeLens bridges the gap between third-party package updates and your internal repository structure. By combining static Abstract Syntax Tree (AST) analysis, call graph blast-radius mapping, and automated release intelligence, MergeLens evaluates the exact impact of every dependency update before it is merged. It automatically identifies broken method calls, calculates risk and confidence scores, recommends targeted test suites, and synthesizes validated migration patches directly on the pull request.

## Core Features

### Abstract Syntax Tree Repository Indexing
MergeLens parses repository source code into detailed Abstract Syntax Trees and constructs call graphs to index every class, function, parameter signature, decorator, and external API usage across the codebase.

### Release & Security Intelligence
The platform queries package registries and security advisory databases to extract breaking API changes, deprecated method signatures, and CVE vulnerabilities, caching these facts to avoid redundant lookups.

### Blast Radius Calculation
MergeLens matches release facts against the indexed call graph to identify direct breaking API usages, trace indirect call chains, and measure codebase impact with precise risk and confidence scoring.

### Automatic Migration Patch Generation
For identified breaking changes, MergeLens generates code patches, validates them in a sandboxed execution environment with AST syntax checking and unit test suite verification, and publishes the fixes as GitHub Suggested Changes.

### Automated GitHub Integration
MergeLens integrates seamlessly into GitHub workflows via webhooks, posting consolidated reviews for multi-dependency pull requests and setting confidence-gated check run statuses to prevent risky code merges.

## Technology Stack

* **Core Framework:** Python 3.11, FastAPI, Uvicorn, Pydantic V2
* **Static Code Analysis:** Tree-sitter, NetworkX
* **Database & Persistence:** Neon Serverless PostgreSQL, SQLAlchemy 2.0, Alembic
* **AI & LLM Synthesis:** Google Gemini 3.6 Flash (`google-genai` SDK), OpenRouter API
* **Release Intelligence:** PyPI Metadata API, OSV.dev Vulnerability Advisory API
* **Testing & Sandboxed Validation:** Pytest, HTTPX Async Client