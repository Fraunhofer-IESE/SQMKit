# Copyright (C) Fraunhofer IESE 2026 Matthias Gerbershagen, Jonathan Ullrich
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

from typing import Any
from unittest.mock import AsyncMock

import pytest
from anyio import Path

from sqmkit.clients.git_client import GitClient
from sqmkit.exceptions import MeasurementError, ToolNotFoundError
from sqmkit.measurements import EvaluationStatus
from sqmkit.measurements.operations.docker_best_practices import DockerBestPractices
from sqmkit.tools import ToolResult
from tests.support import GitClientFactory, RepoDir


def _tool_result(
    output: dict[str, Any],
    exit_code: int = 1,
) -> ToolResult:
    return ToolResult(
        output=output,
        error="tool failed" if exit_code > 1 else None,
    )


def _runner(output: dict[str, Any], exit_code: int = 1) -> AsyncMock:
    runner = AsyncMock()
    runner.run.return_value = _tool_result(output, exit_code)
    return runner


async def _run_with_output(make_git_client: GitClientFactory, output: dict[str, Any]):
    measurement = DockerBestPractices(
        make_git_client(),  # type: ignore[arg-type]
        trivy_runner=_runner(output),
        compose_lint_runner=AsyncMock(),
    )
    return await measurement.execute()


async def _run_with_sources(
    repo_dir: Path,
    trivy_output: dict[str, Any],
    compose_output: dict[str, Any] | None = None,
    compose_exit_code: int = 1,
):
    measurement = DockerBestPractices(
        GitClient(repo_dir),
        trivy_runner=_runner(trivy_output),
        compose_lint_runner=_runner(compose_output or {}, compose_exit_code),
    )
    return await measurement.execute()


@pytest.mark.anyio
async def test_no_dockerfile_or_compose(make_git_client: GitClientFactory) -> None:
    result = await _run_with_output(make_git_client, {"Results": []})

    assert result.status is EvaluationStatus.EVALUATED
    assert result.score == 0.0
    assert result.reason == "No Dockerfile or Docker Compose file found."


@pytest.mark.anyio
async def test_dockerfile_without_violations(
    make_git_client: GitClientFactory,
) -> None:
    output: dict[str, Any] = {
        "Results": [
            {
                "Target": "Dockerfile",
                "Class": "config",
                "Type": "dockerfile",
                "Misconfigurations": [],
            }
        ]
    }

    result = await _run_with_output(make_git_client, output)

    assert result.status is EvaluationStatus.EVALUATED
    assert result.score == 1.0


@pytest.mark.anyio
async def test_dockerfile_with_violations(
    make_git_client: GitClientFactory,
) -> None:
    output: dict[str, Any] = {
        "Results": [
            {
                "Target": "Dockerfile",
                "Class": "config",
                "Type": "dockerfile",
                "Misconfigurations": [
                    {"ID": "DS-0001", "Severity": "HIGH", "Status": "FAIL"},
                    {"ID": "DS-0002", "Severity": "MEDIUM", "Status": "FAIL"},
                    {"ID": "DS-0003", "Severity": "CRITICAL", "Status": "PASS"},
                ],
            }
        ]
    }

    result = await _run_with_output(make_git_client, output)

    assert result.status is EvaluationStatus.EVALUATED
    # HIGH (20) + MEDIUM (10) => penalty 30 => score 0.70
    assert result.score == pytest.approx(0.7)
    assert "1 high" in result.reason
    assert "1 medium" in result.reason


@pytest.mark.anyio
async def test_unknown_severity_is_reported_and_scored(
    make_git_client: GitClientFactory,
) -> None:
    output: dict[str, Any] = {
        "Results": [
            {
                "Type": "dockerfile",
                "Misconfigurations": [
                    {"ID": "DS-0001", "Severity": "UNKNOWN", "Status": "FAIL"},
                ],
            }
        ]
    }

    result = await _run_with_output(make_git_client, output)

    # UNKNOWN (1) => penalty 1 => score 0.99
    assert result.score == pytest.approx(0.99)
    assert "1 unknown" in result.reason


@pytest.mark.anyio
async def test_trivy_failure(make_git_client: GitClientFactory) -> None:
    measurement = DockerBestPractices(
        make_git_client(),  # type: ignore[arg-type]
        trivy_runner=_runner({}, exit_code=2),
        compose_lint_runner=AsyncMock(),
    )
    with pytest.raises(MeasurementError, match="Trivy failed"):
        await measurement.execute()


@pytest.mark.anyio
async def test_missing_trivy_is_reported_with_compose(repo_dir: RepoDir) -> None:
    await repo_dir.add_file("docker-compose.yml", "services: {}")
    trivy = AsyncMock()
    trivy.run.side_effect = ToolNotFoundError("trivy not found")

    measurement = DockerBestPractices(
        GitClient(repo_dir),
        trivy_runner=trivy,
        compose_lint_runner=_runner({}),
    )
    result = await measurement.execute()

    assert result.score == pytest.approx(1.0)
    assert "Trivy is not installed; the Dockerfile was not checked." in result.reason


@pytest.mark.anyio
async def test_compose_only(repo_dir: RepoDir) -> None:
    await repo_dir.add_file("docker-compose.yml", "services: {}")

    result = await _run_with_sources(
        repo_dir,
        {"Results": []},
        {"findings": [{"severity": "critical", "suppressed": False}]},
    )

    assert result.status is EvaluationStatus.EVALUATED
    # CRITICAL (40) => penalty 40 => score 0.60
    assert result.score == pytest.approx(0.6)
    assert "1 critical" in result.reason


@pytest.mark.anyio
async def test_dockerfile_and_compose_average(repo_dir: RepoDir) -> None:
    await repo_dir.add_file("docker-compose.yml", "services: {}")
    dockerfile_output: dict[str, Any] = {
        "Results": [
            {"Type": "dockerfile", "Misconfigurations": []},
        ]
    }

    result = await _run_with_sources(
        repo_dir,
        dockerfile_output,
        {"findings": [{"severity": "critical", "suppressed": False}]},
    )

    # Dockerfile 1.0 and Compose 0.60 => average 0.80
    assert result.score == pytest.approx(0.8)
    assert "average" in result.reason


@pytest.mark.anyio
async def test_compose_findings_ignore_suppressed(repo_dir: RepoDir) -> None:
    await repo_dir.add_file("docker-compose.yml", "services: {}")

    result = await _run_with_sources(
        repo_dir,
        {"Results": []},
        {
            "findings": [
                {"severity": "critical", "suppressed": True},
                {"severity": "high", "suppressed": False},
            ]
        },
    )

    # Only the non-suppressed HIGH (20) counts => 0.80
    assert result.score == pytest.approx(0.8)


@pytest.mark.anyio
async def test_compose_lint_failure(repo_dir: RepoDir) -> None:
    await repo_dir.add_file("docker-compose.yml", "services: {}")

    measurement = DockerBestPractices(
        GitClient(repo_dir),
        trivy_runner=_runner({"Results": []}),
        compose_lint_runner=_runner({}, exit_code=2),
    )
    with pytest.raises(MeasurementError, match="compose-lint failed"):
        await measurement.execute()


@pytest.mark.anyio
async def test_invalid_compose_scores_zero(repo_dir: RepoDir) -> None:
    await repo_dir.add_file("docker-compose.yml", "not-a-compose-file")

    measurement = DockerBestPractices(
        GitClient(repo_dir),
        trivy_runner=_runner({"Results": []}),
        compose_lint_runner=_runner({"errors": [{"kind": "parse"}]}, exit_code=2),
    )
    result = await measurement.execute()

    assert result.status is EvaluationStatus.EVALUATED
    assert result.score == 0.0
    assert "not a valid Compose file" in result.reason


@pytest.mark.anyio
async def test_invalid_compose_lowers_average(repo_dir: RepoDir) -> None:
    await repo_dir.add_file("docker-compose.yml", "not-a-compose-file")
    dockerfile_output: dict[str, Any] = {
        "Results": [{"Type": "dockerfile", "Misconfigurations": []}]
    }

    measurement = DockerBestPractices(
        GitClient(repo_dir),
        trivy_runner=_runner(dockerfile_output),
        compose_lint_runner=_runner({"errors": [{"kind": "parse"}]}, exit_code=2),
    )
    result = await measurement.execute()

    # Dockerfile 1.0 and invalid Compose 0.0 => 0.50
    assert result.score == pytest.approx(0.5)


@pytest.mark.anyio
async def test_nested_compose_is_discovered(repo_dir: RepoDir) -> None:
    await repo_dir.add_file("apps/api/compose.yml", "services: {}")

    result = await _run_with_sources(
        repo_dir,
        {"Results": []},
        {"findings": [{"severity": "critical", "suppressed": False}]},
    )

    assert result.score == pytest.approx(0.6)
    assert "apps/api/compose.yml" in result.reason


@pytest.mark.anyio
async def test_example_compose_is_ignored(repo_dir: RepoDir) -> None:
    await repo_dir.add_file("examples/demo/compose.yml", "services: {}")

    result = await _run_with_sources(repo_dir, {"Results": []}, {})

    assert result.score == 0.0
    assert result.reason == "No Dockerfile or Docker Compose file found."
