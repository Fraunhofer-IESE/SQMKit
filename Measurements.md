# Measurements

SQMKit defines the following measurements that can be used in software quality
models (e.g., `src/sqmkit/quality_models/oss-adoption.json`). 

---

## Operations

### Docker Best Practices

- **Description**
Evaluates Dockerfile quality against container best practices, and Docker Compose security when a Compose file is present.
- **Input**
  - Dockerfile
  - Docker Compose file
- **Uses**
  - Trivy (Dockerfile)
  - compose-lint (Docker Compose)

---

### SBOM Availability

- **Description**
Checks whether a Software Bill of Materials (SBOM) is provided.
- **Input**
  - SBOM files (CycloneDX or SPDX; JSON, XML, RDF or YAML)

---

### Installation Guide

- **Description**
Assesses installation and setup instructions for completeness, structure, clarity and understandability. It considers the README, CONTRIBUTING, standalone `INSTALL` documents and common files under `docs/`.
- **Input**
  - README
  - CONTRIBUTING
  - `INSTALL`, `INSTALL.md`, `INSTALL.rst`, `INSTALL.txt`
  - `docs/installation.md`, `docs/install.md`, `docs/setup.md`, `docs/getting-started.md`, `docs/quickstart.md`
- **Uses**
  - LLM/ Decision model

---

## Legal

### License Compliance

- **Description**
Checks whether the project's own license and its dependency licenses are OpenCode-compatible.
- **Input**
  - LICENSE file
  - Dependency licenses
- **Uses**
  - Trivy
  - openCode allow-list of standardised open source licenses: [https://opencode.de/en/knowledge/general-conditions/standardised-open-source-licenses](https://opencode.de/en/knowledge/general-conditions/standardised-open-source-licenses)

---

### License Coverage

- **Description**
Checks whether the source files carry license headers.
- **Input**
  - Source files
- **Uses**
  - REUSE

---

## Security

### Security Policy

- **Description**
Checks the presence and quality of a SECURITY.md disclosure policy.
- **Input**
  - SECURITY.md
- **Uses**
  - LLM/ Decision model

---

### Vulnerabilities

- **Description**
Detects known vulnerabilities in project dependencies.
- **Input**
  - Dependency manifests
- **Uses**
  - Trivy

---

## Code Quality

### Project Structure

- **Description**
Evaluates the repository structure against ecosystem norms.
- **Input**
  - File tree
- **Uses**
  - LLM/ Decision model

---

### Code Duplication

- **Description**
Measures the share of duplicated code across the repository.
- **Input**
  - Source files
- **Uses**
  - Lizard

---

## Maintenance and Support

### Solved Issues

- **Description**
Measures the share of closed issues in the last 6 months.
- **Input**
  - Issue state and close times (GitHub/GitLab)
- **Uses**
  - GitHub/GitLab API

---

### Commit Trend

- **Description**
Evaluates activity trends over time (commit frequency, recency).
- **Input**
  - Local commit history
- **Uses**
  - Local git repository

---

### Project Description

- **Description**
Evaluates whether the README describes the project's purpose, setup, status and maintainers.
- **Input**
  - README.md (repository root)
- **Uses**
  - LLM/ Decision model

---

### Community Guidelines

- **Description**
Checks whether common governance files exist at the repository root.
- **Input**
  - CODE_OF_CONDUCT
  - CONTRIBUTING

---

### Community Discussions

- **Description**
Analyzes tone and collaboration quality in issue discussions.
- **Input**
  - Issue comments from the last 6 months (GitHub/GitLab)
- **Uses**
  - GitHub/GitLab API
  - LLM/ Decision model

---

### Bus Factor

- **Description**
Estimates risk concentration by analyzing the contributor distribution.
- **Input**
  - Local commit history
- **Uses**
  - Local git repository