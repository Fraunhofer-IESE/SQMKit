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

import re
from typing import override

from anyio import Path
from license_expression import (
    LicenseSymbol,
    LicenseWithExceptionSymbol,
    Licensing,
)

from sqmkit.config import settings
from sqmkit.exceptions import MeasurementError
from sqmkit.measurements import (
    EvaluationStatus,
    Measurement,
    MeasurementOutput,
    Requirement,
)
from sqmkit.measurements.repo_file_utils import RepositoryFile, find_file
from sqmkit.tools import TrivyRunner


class LicenseCompliance(Measurement):
    requires = (Requirement.TRIVY,)

    _MAX_FILE_SIZE = 10 * 1024 * 1024
    _LICENSING = Licensing()

    def __init__(
        self, repo_path: Path, trivy_runner: TrivyRunner | None = None
    ) -> None:
        self.repo_path = repo_path
        self.trivy = trivy_runner if trivy_runner is not None else TrivyRunner()

    @staticmethod
    def _canonical_license(name: str) -> str:
        """Normalize an SPDX identifier for allow-list comparison. Drops a trailing ``+`` and the ``-only``/``-or-later`` suffix, so that e.g. ``AGPL-3.0``, ``AGPL-3.0-only`` and ``GPL-2.0+`` compare against the corresponding allow-list entries."""
        return re.sub(r"(\+|-only|-or-later)$", "", name.strip().lower())

    def _is_compliant(self, name: str, allowed: set[str]) -> bool:
        """Whether a reported license (list, expression, ``WITH``) is allowed. Unparseable strings (e.g. ``SEE LICENSE IN LICENSE.txt`` or ``unknown``) are treated as non-compliant, never skipped."""
        try:
            expression = LicenseCompliance._LICENSING.parse(name)
        except Exception:
            return False
        return self._evaluate_expression(expression, allowed)

    def _evaluate_expression(self, expression: object, allowed: set[str]) -> bool:
        if isinstance(expression, LicenseSymbol):
            return self._canonical_license(expression.key) in allowed
        if isinstance(expression, LicenseWithExceptionSymbol):
            # Only the base license matters; the exception (e.g. LLVM-exception) is not a license on its own.
            return self._evaluate_expression(expression.license_symbol, allowed)

        args = getattr(expression, "args", ())
        operator = getattr(expression, "operator", " AND ").strip()
        if operator == "OR":
            return any(self._evaluate_expression(arg, allowed) for arg in args)
        return all(self._evaluate_expression(arg, allowed) for arg in args)

    async def _load_allowed_licenses(self) -> set[str]:
        """Load the normalized allow-list of OpenCoDE-compatible license ids. Uses the bundled ``openCode_allowed_licenses.txt`` unless ``LICENSE_ALLOWLIST_PATH`` points at a custom file. Blank lines and ``#`` comments are ignored."""
        override = settings.license_allowlist_path
        if override:
            allowed_licenses_file = Path(override)
        else:
            allowed_licenses_file = (
                Path(__file__).parent / "openCode_allowed_licenses.txt"
            )

        try:
            async with await allowed_licenses_file.open("r", encoding="utf-8") as f:
                lines = await f.readlines()
        except OSError as error:
            source = (
                f"LICENSE_ALLOWLIST_PATH ({override})"
                if override
                else "the bundled license allow-list"
            )
            raise MeasurementError(f"Could not read {source}: {error}") from error

        return {
            self._canonical_license(line)
            for line in lines
            if line.strip() and not line.lstrip().startswith("#")
        }

    @staticmethod
    def _reported_licenses(output: object) -> list[str]:
        """Collect every license name Trivy reported (project and dependencies)."""
        if not isinstance(output, dict):
            return []
        names: list[str] = []
        for result in output.get("Results", []) or []:
            for entry in result.get("Licenses", []) or []:
                name = entry.get("Name", "")
                if name:
                    names.append(name)
        return names

    @override
    async def execute(self) -> MeasurementOutput:
        declared_license_file = await find_file(self.repo_path, RepositoryFile.LICENSE)
        # no license file
        if declared_license_file is None:
            return MeasurementOutput(
                status=EvaluationStatus.EVALUATED,
                score=0.0,
                reason="LICENSE file not found.",
            )

        # license file empty or too big
        size = (await declared_license_file.stat()).st_size
        if size == 0 or size > LicenseCompliance._MAX_FILE_SIZE:
            return MeasurementOutput(
                status=EvaluationStatus.EVALUATED,
                score=0.0,
                reason="License file too large or empty",
            )

        allowed_licenses = await self._load_allowed_licenses()

        # Trivy reports the project's own license (as a "license-file" result) and the dependency licenses in a structured form, so it is the single source of truth for both checks.
        tool_result = await self.trivy.run(self.repo_path)
        if tool_result.failure:
            raise MeasurementError(
                f"Trivy failed for {self.repo_path}\n"
                f"stdout:\n{tool_result.output}\n\nstderr:\n{tool_result.error}"
            )

        reported_licenses = self._reported_licenses(tool_result.output)
        if not reported_licenses:
            return MeasurementOutput(
                status=EvaluationStatus.EVALUATED,
                score=0.0,
                reason="No license information could be determined by Trivy.",
            )

        non_compliant = sorted(
            {
                name
                for name in reported_licenses
                if not self._is_compliant(name, allowed_licenses)
            }
        )

        if non_compliant:
            reason = (
                f"Non-OpenCode-compatible license(s) found: {', '.join(non_compliant)}"
            )
            return MeasurementOutput(
                status=EvaluationStatus.EVALUATED,
                score=0.0,
                reason=reason,
            )

        return MeasurementOutput(
            status=EvaluationStatus.EVALUATED,
            score=1.0,
            reason="Project is licensed OpenCode compatible.",
        )
