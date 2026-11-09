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
from sqmkit.utils import load_pathspec


class ProjectStructureBestPractices(ModelMeasurement):
    MAX_DEPTH = 6

    _CRITERIA: Sequence[LikertCriterion] = (
        LikertCriterion(
            name="directory_organization",
            description="The project follows appropriate directory organization conventions for its technology stack (e.g., src/, tests/, docs/).",
        ),
        LikertCriterion(
            name="naming_conventions",
            description="The project uses consistent naming conventions for files and directories (e.g., snake_case, camelCase).",
        ),
        LikertCriterion(
            name="separation_of_concerns",
            description="The project properly separates different concerns into appropriate directories (e.g., separating source, tests, configuration).",
        ),
        LikertCriterion(
            name="modularity",
            description="The project demonstrates good modularity with a logical breakdown of components or modules.",
        ),
    )

    _IGNORE_SPEC = load_pathspec("common", "structure")

    def __init__(self, repo_path: Path, model_client: ModelClient):
        self.repo_path = repo_path
        self.model_client = model_client

    @override
    async def evaluate(self) -> MeasurementOutput:
        repo_structure = await self._build_repo_tree(self.repo_path)

        evaluations = await self.model_client.evaluate_context_likert(
            context=repo_structure,
            criteria=ProjectStructureBestPractices._CRITERIA,
        )

        reason_parts = ["Project structure evaluation:"]

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

    async def _build_repo_tree(self, root: Path) -> str:
        lines = [root.name]

        async def _walk(directory: Path, prefix: str, level: int) -> None:
            if level > self.MAX_DEPTH:
                return

            items: list[Path] = []
            async for item in directory.iterdir():
                relative = item.relative_to(self.repo_path).as_posix()
                if self._IGNORE_SPEC.match_file(relative):
                    continue
                items.append(item)
            items.sort(key=lambda item: item.name)

            for i, item in enumerate(items):
                is_last = i == len(items) - 1
                connector = "└─ " if is_last else "├─ "

                if await item.is_dir():
                    lines.append(f"{prefix}{connector}{item.name}/")
                    new_prefix = prefix + ("   " if is_last else "│  ")
                    await _walk(item, new_prefix, level + 1)
                else:
                    lines.append(f"{prefix}{connector}{item.name}")

        await _walk(root, "", 1)
        return "\n".join(lines)
