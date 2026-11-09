# SQMKit

A software quality model kit for automated assessment of software repositories
using static analysis and LLMs. SQMKit ships with a quality model for
**open-source adoption readiness**.

## Features

- Combines static analysis (Trivy, REUSE, etc.) with  LLM-based measurement using auto-regressive LLMs (OpenAI-compatible API/ Anthropic) or decision models (System One API)
- Evaluates multiple repositories in one run and aggregates their results
- Combines multiple LLM judges by averaging their Likert scores per criterion
- Assesses remote Git repositories (GitHub, GitLab) or local repositories or  
plain directories
- Quality models are declarative JSON files

- Table output for humans, JSON for tooling

## Prerequisites

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Optional: [Trivy](https://trivy.dev/) for vulnerability, license, and
Dockerfile scanning
- Optional: a GitHub and/or GitLab API key for issue-related measurements
- Optional: Model-provider credentials for LLM-based measurements

## Installation

```bash
cd SQMKit
uv sync
```

## Usage

Copy `.env.example` to `.env` and fill in what you need (API keys, LLM configuration), then:

```bash
uv run sqmkit run https://github.com/owner/repo # evaluate remote repository

uv run sqmkit run oss-adoption ./path/to/repo # evaluate local repository

uv run sqmkit run oss-adoption ./repo-a ./repo-b # evaluate multiple repositories in one run

uv run sqmkit run --json https://github.com/owner/repo > report.json # JSON output

uv run sqmkit quality-models # list bundled quality models

uv run sqmkit run --help # command help

uv run sqmkit run ./my-quality-model.json ./repo # runs custom quality model
```