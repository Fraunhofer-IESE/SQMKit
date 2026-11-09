# Copyright (C) Fraunhofer IESE 2026 Jonathan Ullrich
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


class SecurityPolicyBestPractices(ModelMeasurement):
    _CRITERIA: Sequence[LikertCriterion] = (
        LikertCriterion(
            name="security_contact_information",
            description="The document provides clear contact information for security-related inquiries.",
        ),
        LikertCriterion(
            name="vulnerability_reporting_process",
            description="The document clearly describes the process how to report security vulnerabilities.",
        ),
        LikertCriterion(
            name="supported_versions",
            description="The document specifies which versions of the software are currently supported with security updates.",
        ),
    )

    def __init__(self, repo_path: Path, model_client: ModelClient):
        self.repo_path = repo_path
        self.model_client = model_client

    @override
    async def evaluate(self) -> MeasurementOutput:
        security_policy_file = await find_file(self.repo_path, RepositoryFile.SECURITY)

        if not security_policy_file:
            return MeasurementOutput(
                status=EvaluationStatus.EVALUATED,
                score=0.0,
                reason="SECURITY.md file not found in root folder.",
            )

        if (await security_policy_file.stat()).st_size == 0:
            return MeasurementOutput(
                status=EvaluationStatus.EVALUATED,
                score=0.0,
                reason="SECURITY.md file is empty.",
            )

        async with await security_policy_file.open(
            "r", encoding="utf-8", errors="replace"
        ) as f:
            security_text = "\n".join(await f.readlines())
        evaluations = await self.model_client.evaluate_context_likert(
            context=security_text,
            criteria=SecurityPolicyBestPractices._CRITERIA,
        )

        reason_parts = ["Evaluation of the SECURITY.md file:"]

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
