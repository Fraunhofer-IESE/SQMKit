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

from typing import override

from anyio import Path

from sqmkit.exceptions import MeasurementError
from sqmkit.measurements import EvaluationStatus, Measurement, MeasurementOutput
from sqmkit.tools import LizardRunner


class CodeDuplication(Measurement):
    def __init__(self, repo_path: Path):
        self.repo_path = repo_path

    @override
    async def execute(self) -> MeasurementOutput:
        lizard_runner = LizardRunner()
        tool_result = await lizard_runner.run(self.repo_path)

        # The LizardRunner marks the execution as failed when no duplication rate could be extracted. This is an execution error, not an inapplicable measurement, so the evaluator marks the node ERRORED.
        if tool_result.failure:
            raise MeasurementError("Lizard failed to analyze the repository.")

        if tool_result.output.get("total_nloc") == 0:
            return MeasurementOutput(
                status=EvaluationStatus.SKIPPED,
                score=0.0,
                reason="No analyzable source code found.",
            )

        # 0% duplication -> 1.0 (best), 100% duplication -> 0.0 (worst)
        duplicate_rate_pct = tool_result.output["duplicate_rate_pct"]
        score = 1.0 - duplicate_rate_pct / 100.0
        reason = (
            f"Lizard has calculated a duplication rate of {duplicate_rate_pct:.2f}%"
        )

        return MeasurementOutput(
            status=EvaluationStatus.EVALUATED,
            score=score,
            reason=reason,
        )
