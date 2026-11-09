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


class InstallationGuide(ModelMeasurement):
    _MAX_FILE_SIZE = 10 * 1024 * 1024  # Do not open files larger than 10MB

    _ROOT_DOCUMENT_NAMES = frozenset(
        {"install", "install.md", "install.rst", "install.txt"}
    )
    _DOCS_DOCUMENT_NAMES = frozenset(
        {
            "installation.md",
            "installation.rst",
            "install.md",
            "install.rst",
            "setup.md",
            "setup.rst",
            "getting-started.md",
            "getting_started.md",
            "quickstart.md",
            "quick-start.md",
        }
    )

    _CRITERIA: Sequence[LikertCriterion] = (
        LikertCriterion(
            name="completeness",
            description=(
                "How would you rate the guide's coverage of the information needed to install, configure where required, and verify the software?"
            ),
        ),
        LikertCriterion(
            name="structure",
            description=(
                "Is the installation guide arranged so that the user can find what is needed and follow the installation process in the required order?"
            ),
        ),
        LikertCriterion(
            name="clarity",
            description=(
                "Are instructions, commands, prerequisites, configuration values, and expected outcomes stated precisely and without ambiguity?"
            ),
        ),
        LikertCriterion(
            name="understandability",
            description=(
                "How easy was it to understand the installation or setup steps? Consider whether the guide explained the technical terms and concepts or required you to know them beforehand."
            ),
        ),
    )

    def __init__(self, repo_path: Path, model_client: ModelClient):
        self.repo_path = repo_path
        self.model_client = model_client

    @override
    async def evaluate(self) -> MeasurementOutput:
        documents = await self._collect_documents()

        if not documents:
            return MeasurementOutput(
                status=EvaluationStatus.EVALUATED,
                score=0.0,
                reason="No README, CONTRIBUTING, or installation documentation found.",
            )

        context = "\n\n".join(f"# {label}\n\n{content}" for label, content in documents)
        evaluations = await self.model_client.evaluate_context_likert(
            context=context,
            criteria=InstallationGuide._CRITERIA,
        )

        sources = ", ".join(label for label, _ in documents)
        reason_parts = [f"Evaluation of the installation documentation ({sources}):"]

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

    async def _collect_documents(self) -> list[tuple[str, str]]:
        """Read installation-relevant files from the repository. The README and CONTRIBUTING files are always considered, together with common standalone install documents and files under ``docs/``."""
        candidates: list[tuple[str, Path]] = []

        for file_type in (RepositoryFile.README, RepositoryFile.CONTRIBUTING):
            found = await find_file(self.repo_path, file_type)
            if found is not None:
                candidates.append((file_type.value.upper(), found))

        async for entry in self.repo_path.iterdir():
            if (
                await entry.is_file()
                and entry.name.lower() in InstallationGuide._ROOT_DOCUMENT_NAMES
            ):
                candidates.append((entry.name, entry))

        docs_dir = self.repo_path / "docs"
        if await docs_dir.is_dir():
            async for entry in docs_dir.iterdir():
                if (
                    await entry.is_file()
                    and entry.name.lower() in InstallationGuide._DOCS_DOCUMENT_NAMES
                ):
                    candidates.append((f"docs/{entry.name}", entry))

        documents: list[tuple[str, str]] = []
        seen: set[str] = set()

        for label, path in candidates:
            key = str(path).lower()
            if key in seen:
                continue
            seen.add(key)

            content = await self._read_document(path)
            if content is not None:
                documents.append((label, content))

        return documents

    async def _read_document(self, path: Path) -> str | None:
        size = (await path.stat()).st_size
        if size == 0 or size > InstallationGuide._MAX_FILE_SIZE:
            return None

        async with await path.open("r", encoding="utf-8", errors="replace") as file:
            return "\n".join(await file.readlines())
