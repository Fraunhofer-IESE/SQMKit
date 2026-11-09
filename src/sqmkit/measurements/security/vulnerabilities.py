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

from typing import Any, override

from anyio import Path

from sqmkit.exceptions import MeasurementError
from sqmkit.measurements import (
    EvaluationStatus,
    Measurement,
    MeasurementOutput,
    Requirement,
)
from sqmkit.tools import TrivyRunner


class Vulnerability(Measurement):
    requires = (Requirement.TRIVY,)

    def __init__(
        self, repo_path: Path, trivy_runner: TrivyRunner | None = None
    ) -> None:
        self.repo_path = repo_path
        self.trivy = trivy_runner if trivy_runner is not None else TrivyRunner()

    def _extract_severity(self, vulnerability: dict[str, Any]) -> str | None:
        cvss = vulnerability.get("CVSS")
        if not cvss:
            return None
        # Prefer nvd score, fall back to ghsa, then redhat
        for source in ("nvd", "ghsa", "redhat"):
            source_data = cvss.get(source)
            if source_data:
                score = source_data.get("V3Score") or source_data.get("V40Score")
                if score is not None:
                    return str(score)
        return None

    def _extract_results(self, output: dict[str, Any] | None) -> dict[str, list[str]]:
        vulnerable_packages: dict[str, list[str]] = {}
        if not output:
            return vulnerable_packages
        results: list[dict[str, Any]] = output.get("Results", [])
        if not results:
            return vulnerable_packages
        for result in results:
            vulnerabilities: list[dict[str, Any]] = result.get("Vulnerabilities", [])
            for vulnerability in vulnerabilities:
                name = vulnerability.get("PkgName", "")
                vuln_id = vulnerability.get("VulnerabilityID", "")
                fixed_version = vulnerability.get("FixedVersion", "")
                severity = self._extract_severity(vulnerability)
                severity_str = severity if severity else ""
                key = f"{name}|{vuln_id}|{severity_str}"
                fixed_versions = [fixed_version] if fixed_version else []
                vulnerable_packages[key] = fixed_versions
        return vulnerable_packages

    @override
    async def execute(self) -> MeasurementOutput:
        tool_result = await self.trivy.run(self.repo_path)

        if tool_result.failure:
            raise MeasurementError(f"Trivy failed: {tool_result.error}.")

        output: dict[str, Any] = tool_result.output or {}
        results = self._extract_results(output)

        if not results:
            return MeasurementOutput(
                status=EvaluationStatus.EVALUATED,
                score=1.0,
                reason="No dependencies with security vulnerabilities were found.",
            )

        reason = "Dependencies with security vulnerabilities were found:"
        for key, fixed_versions in results.items():
            parts = key.split("|")
            name = parts[0]
            vuln_id = parts[1] if len(parts) > 1 else ""
            severity = parts[2] if len(parts) > 2 and parts[2] else None
            severity_str = f" (Criticality: {severity})" if severity else ""
            if not fixed_versions:
                reason += f"\n{name} {vuln_id}{severity_str}"
            else:
                reason += f"\n{name} {vuln_id}{severity_str} (fixed in versions {','.join(fixed_versions)})"

        return MeasurementOutput(
            status=EvaluationStatus.EVALUATED,
            score=0.0,
            reason=reason,
        )
