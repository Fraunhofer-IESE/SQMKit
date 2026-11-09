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

from sqmkit.exceptions import MeasurementError
from sqmkit.measurements import EvaluationStatus, Measurement, MeasurementOutput
from sqmkit.measurements.repo_file_utils import RepositoryFile, find_file
from sqmkit.tools import ReuseRunner


class LicenseCoverage(Measurement):
    # Scoring: 0.5 for having a LICENSE file, plus up to 0.5 proportional to the share of checked files that carry a license header / matching license. Only header/attribution presence findings count towards coverage. Findings such as "missing license 'X'" merely mean the repository does not ship the license text under LICENSES/, which is not a header-coverage problem.
    _FINDING_MESSAGES = (
        "no license identifier",
        "no copyright notice",
        "no licensing information",
        "no copyright information",
    )
    _FINDING_RE = re.compile(r"^(?P<path>.+?): (?P<message>.+)$")

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path

    def _count_non_compliant_files(self, output: str) -> int:
        """Count distinct files ``reuse lint-file`` reported as non-compliant."""
        files: set[str] = set()
        for line in output.splitlines():
            match = LicenseCoverage._FINDING_RE.match(line.strip())
            if not match:
                continue
            message = match.group("message").lower()
            if message.startswith(LicenseCoverage._FINDING_MESSAGES):
                files.add(match.group("path"))
        return len(files)

    @override
    async def execute(self) -> MeasurementOutput:
        license_file = await find_file(self.repo_path, RepositoryFile.LICENSE)

        # no license file
        if license_file is None:
            return MeasurementOutput(
                status=EvaluationStatus.EVALUATED,
                score=0.0,
                reason="LICENSE file not found.",
            )

        if (await license_file.stat()).st_size == 0:
            return MeasurementOutput(
                status=EvaluationStatus.EVALUATED,
                score=0.0,
                reason="LICENSE file is empty.",
            )

        # check license headers with Reuse
        reuse_runner = ReuseRunner()
        tool_result = await reuse_runner.run(self.repo_path)

        if tool_result.failure:
            raise MeasurementError(
                f"Reuse failed for {self.repo_path}\n"
                f"stdout:\n{tool_result.output}\n\nstderr:\n{tool_result.error}"
            )

        checked_files = tool_result.checked_files or 0
        non_compliant = self._count_non_compliant_files(str(tool_result.output or ""))

        if checked_files > 0 and non_compliant == 0:
            return MeasurementOutput(
                status=EvaluationStatus.EVALUATED,
                score=1.0,
                reason="LICENSE file present and all files have a license header.",
            )

        if checked_files > 0:
            compliant = max(checked_files - non_compliant, 0)
            score = 0.5 + 0.5 * (compliant / checked_files)
        else:
            score = 0.5

        summary = (
            f"{non_compliant} of {checked_files} checked files are missing "
            "license headers."
        )
        reason = f"Files without a license header were found.\n{summary}\n{tool_result.output}"
        return MeasurementOutput(
            status=EvaluationStatus.EVALUATED,
            score=score,
            reason=reason,
        )
