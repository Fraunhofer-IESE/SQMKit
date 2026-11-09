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

from types import MappingProxyType
from typing import Any, override

from sqmkit.clients.git_client import GitClient
from sqmkit.exceptions import MeasurementError, ToolNotFoundError
from sqmkit.measurements import EvaluationStatus, Measurement, MeasurementOutput
from sqmkit.measurements.repo_file_utils import RepositoryFile, find_files
from sqmkit.tools import ComposeLintRunner, TrivyRunner


class DockerBestPractices(Measurement):
    """Evaluates Dockerfile (Trivy) and Docker Compose (compose-lint) quality. Trivy's misconfiguration scanner handles Dockerfiles; Docker Compose files are not covered by Trivy and are assessed with ``compose-lint`` instead. When both are present the score is the average of the two results. Trivy is not a hard requirement: without it the Dockerfile is skipped and the Compose files are still assessed."""

    _SEVERITY_WEIGHTS = MappingProxyType(
        {
            "CRITICAL": 40.0,
            "HIGH": 20.0,
            "MEDIUM": 10.0,
            "LOW": 2.5,
            "UNKNOWN": 1.0,
        }
    )

    def __init__(
        self,
        git_client: GitClient,
        trivy_runner: TrivyRunner | None = None,
        compose_lint_runner: ComposeLintRunner | None = None,
    ) -> None:
        self.git_client = git_client
        self.repo_path = git_client.repo_path
        self.trivy = trivy_runner if trivy_runner is not None else TrivyRunner()
        self.compose_lint = (
            compose_lint_runner
            if compose_lint_runner is not None
            else ComposeLintRunner()
        )

    @override
    async def execute(self) -> MeasurementOutput:
        compose = await self._score_compose_files()

        # Trivy is an external binary; when it is missing we can still assess Docker Compose files, but the Dockerfile cannot be scanned.
        dockerfile: list[tuple[float, str]] = []
        trivy_missing = False
        try:
            tool_result = await self.trivy.run(self.repo_path)
        except ToolNotFoundError:
            trivy_missing = True
        else:
            if tool_result.failure:
                raise MeasurementError(f"Trivy failed: {tool_result.error}.")
            dockerfile = self._score_dockerfile(tool_result.output or {})

        scores = [score for score, _ in dockerfile]
        scores.extend(score for _, score, _ in compose)
        if not scores:
            if trivy_missing:
                return MeasurementOutput(
                    status=EvaluationStatus.SKIPPED,
                    score=0.0,
                    reason=(
                        "Trivy is not installed, so the Dockerfile cannot be "
                        "assessed, and no Docker Compose file was found."
                    ),
                )
            return MeasurementOutput(
                status=EvaluationStatus.EVALUATED,
                score=0.0,
                reason="No Dockerfile or Docker Compose file found.",
            )

        score = sum(scores) / len(scores)
        reasons = [reason for _, reason in dockerfile]
        reasons.extend(reason for _, _, reason in compose)
        if trivy_missing:
            reasons.append("Trivy is not installed; the Dockerfile was not checked.")
        if dockerfile and compose:
            reasons.append(
                "Score is the average of the Dockerfile and Docker Compose results."
            )
        return MeasurementOutput(
            status=EvaluationStatus.EVALUATED,
            score=score,
            reason=" ".join(reasons),
        )

    def _score_dockerfile(self, output: dict[str, Any]) -> list[tuple[float, str]]:
        """Score the Dockerfile via Trivy, or return an empty list if there is none."""
        has_dockerfile = any(
            result.get("Type") == "dockerfile" for result in output.get("Results", [])
        )
        if not has_dockerfile:
            return []

        severities = self._extract_dockerfile_findings(output)
        if not severities:
            return [(1.0, "Dockerfile: no best-practice violations detected.")]

        counts = self._count(severities)
        return [
            (
                self._score_from_severities(severities),
                f"Dockerfile: {self._format_counts(counts)}.",
            )
        ]

    async def _score_compose_files(self) -> list[tuple[str, float, str]]:
        """Score every Docker Compose file in the repository with compose-lint."""
        try:
            compose_files = await find_files(
                self.git_client, RepositoryFile.DOCKER_COMPOSE, recursive=True
            )
        except OSError:
            return []

        results: list[tuple[str, float, str]] = []
        for compose_file in compose_files:
            relative = compose_file.relative_to(self.repo_path).as_posix()
            tool_result = await self.compose_lint.run(compose_file)

            if tool_result.failure:
                error_kinds = self._compose_error_kinds(tool_result.output)
                # A matched file that is not valid Compose (parse error) is not a failure: score it 0 so it still lowers the overall score.
                if error_kinds and error_kinds <= {"parse"}:
                    results.append(
                        (
                            relative,
                            0.0,
                            f"{relative}: not a valid Compose file (score 0).",
                        )
                    )
                    continue
                raise MeasurementError(
                    f"compose-lint failed for {relative}: {tool_result.error}."
                )

            severities = self._extract_compose_findings(tool_result.output)
            if not severities:
                results.append((relative, 1.0, f"{relative}: no findings."))
                continue

            counts = self._count(severities)
            results.append(
                (
                    relative,
                    self._score_from_severities(severities),
                    f"{relative}: {self._format_counts(counts)}.",
                )
            )
        return results

    @staticmethod
    def _compose_error_kinds(output: object) -> set[str]:
        """The ``kind`` values of the errors in a compose-lint envelope."""
        if not isinstance(output, dict):
            return set()
        return {str(entry.get("kind", "")) for entry in output.get("errors", []) or []}

    def _extract_dockerfile_findings(self, output: dict[str, Any]) -> list[str]:
        """Return the severities of all failing Dockerfile misconfigurations."""
        severities: list[str] = []
        for result in output.get("Results", []):
            if result.get("Type") != "dockerfile":
                continue
            for misconfiguration in result.get("Misconfigurations", []):
                if misconfiguration.get("Status") != "FAIL":
                    continue
                severities.append(misconfiguration.get("Severity", "UNKNOWN"))
        return severities

    @staticmethod
    def _extract_compose_findings(output: object) -> list[str]:
        """Return the severities of all non-suppressed compose-lint findings."""
        if not isinstance(output, dict):
            return []
        severities: list[str] = []
        for finding in output.get("findings", []) or []:
            if finding.get("suppressed"):
                continue
            severity = str(finding.get("severity", "")).upper() or "UNKNOWN"
            severities.append(severity)
        return severities

    @classmethod
    def _score_from_severities(cls, severities: list[str]) -> float:
        penalty = min(
            sum(cls._SEVERITY_WEIGHTS.get(severity, 0.0) for severity in severities),
            100.0,
        )
        return (100.0 - penalty) / 100.0

    @staticmethod
    def _count(severities: list[str]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for severity in severities:
            counts[severity] = counts.get(severity, 0) + 1
        return counts

    @staticmethod
    def _format_counts(counts: dict[str, int]) -> str:
        return (
            f"{counts.get('CRITICAL', 0)} critical, "
            f"{counts.get('HIGH', 0)} high, "
            f"{counts.get('MEDIUM', 0)} medium, "
            f"{counts.get('LOW', 0)} low and "
            f"{counts.get('UNKNOWN', 0)} unknown severity issues"
        )
