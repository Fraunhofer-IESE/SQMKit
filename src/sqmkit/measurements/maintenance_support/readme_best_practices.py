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

from collections.abc import Sequence
from typing import override

from anyio import Path

from sqmkit.clients.model_client import ModelClient
from sqmkit.clients.model_client.model_evaluation import (
    LikertCriterion,
    get_normalized_likert_score,
)
from sqmkit.measurements import EvaluationStatus, MeasurementOutput, ModelMeasurement
from sqmkit.measurements.repo_file_utils import RepositoryFile, find_file


class ReadmeBestPractices(ModelMeasurement):
    _MAX_FILE_SIZE = 10 * 1024 * 1024

    # roughly follows https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes
    _CRITERIA: Sequence[LikertCriterion] = (
        LikertCriterion(
            name="project_purpose",
            description="The README describes the project's purpose and why it is useful.",
        ),
        LikertCriterion(
            name="setup_instructions",
            description="The README describes the setup instructions.",
        ),
        LikertCriterion(
            name="info_project_status",
            description="The README describes the project's status (active development, no longer maintained, etc.).",
        ),
        LikertCriterion(
            name="info_maintainer",
            description="The README describes who maintains and contributes to the project.",
        ),
    )

    def __init__(self, repo_path: Path, model_client: ModelClient):
        """Initialize the measurement for a repository path."""
        self.repo_path = repo_path
        self.model_client = model_client

    @override
    async def evaluate(self) -> MeasurementOutput:
        readme_file = await find_file(self.repo_path, RepositoryFile.README)

        if not readme_file:
            return MeasurementOutput(
                status=EvaluationStatus.EVALUATED,
                score=0.0,
                reason="README file not found in root folder.",
            )

        size = (await readme_file.stat()).st_size
        if size == 0:
            return MeasurementOutput(
                status=EvaluationStatus.EVALUATED,
                score=0.0,
                reason="Readme file is empty.",
            )
        if size > ReadmeBestPractices._MAX_FILE_SIZE:
            return MeasurementOutput(
                status=EvaluationStatus.SKIPPED,
                score=0.0,
                reason="Readme file too large",
            )

        async with await readme_file.open("r", encoding="utf-8", errors="replace") as f:
            readme_text = "\n".join(await f.readlines())
        evaluations = await self.model_client.evaluate_context_likert(
            context=readme_text,
            criteria=ReadmeBestPractices._CRITERIA,
        )

        reason_parts = ["Evaluation of the README file:"]

        for criterion_name, aggregated in evaluations.items():
            reason_parts.append(
                f"\n{criterion_name}:\n"
                f"Score (avg): {aggregated.likert_evaluation}\n"
                f"{aggregated.reason}"
            )

        reason = "\n".join(reason_parts)

        return MeasurementOutput(
            status=EvaluationStatus.EVALUATED,
            score=get_normalized_likert_score(evaluations),
            reason=reason,
        )
