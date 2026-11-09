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

from pydantic import BaseModel, Field, HttpUrl

from sqmkit.clients.git_client import GitClient
from sqmkit.clients.issue_tracker import IssueStore
from sqmkit.clients.issue_tracker.issue_tracker_factory import IssueTrackerFactory
from sqmkit.clients.model_client import ModelClient
from sqmkit.config import settings
from sqmkit.evaluation.quality_model import QualityModel, QualityModelNode
from sqmkit.exceptions import IssueTrackerError, SqmKitError
from sqmkit.measurements import EvaluationStatus, Requirement
from sqmkit.measurements.measurement_factory import MeasurementFactory
from sqmkit.tools import TrivyRunner


class EvaluationNode(BaseModel):
    name: str
    weight: float
    status: EvaluationStatus
    score: float
    reason: str
    children: list["EvaluationNode"] = Field(default_factory=list)
    # How many leaf measurements were actually evaluated, independent of how their weights were renormalized. ``coverage`` is the ratio of evaluated measurements to all measurements in this subtree.
    evaluated_measurements: int = 0
    total_measurements: int = 0
    coverage: float = 0.0


class Evaluator:
    def __init__(
        self,
        quality_model: QualityModel,
        git_client: GitClient,
        repo_url: HttpUrl | None,
        model_client: ModelClient,
    ) -> None:
        self._quality_model = quality_model
        self._git_client = git_client
        self._repo_url = repo_url
        self._model_client = model_client
        # One shared runner so Trivy is only executed once per repository, regardless of how many measurements depend on it.
        self._trivy_runner = TrivyRunner()
        self._has_trivy = TrivyRunner.is_available()
        # One shared issue store so Solved Issues and Community Discussions do not fetch the same issue pages twice.
        self._issue_store = self._build_issue_store()

    def _build_issue_store(self) -> IssueStore | None:
        if self._repo_url is None or self._unmet_forge_requirement() is not None:
            return None
        try:
            return IssueStore(IssueTrackerFactory.create_issue_tracker(self._repo_url))
        except IssueTrackerError:
            return None

    async def evaluate(self, node: QualityModelNode | None = None) -> EvaluationNode:
        node = node if node is not None else self._quality_model.root
        # base case - leaf node with measurement
        if node.measurement is not None:
            skip_reason = self._unmet_requirement(
                MeasurementFactory.get_requirements(node.measurement)
            )
            if skip_reason is not None:
                return EvaluationNode(
                    name=node.name,
                    weight=node.weight,
                    status=EvaluationStatus.SKIPPED,
                    score=0.0,
                    reason=skip_reason,
                    evaluated_measurements=0,
                    total_measurements=1,
                    coverage=0.0,
                )

            # A single failing measurement must not abort the whole repository: convert any error into an errored node and keep evaluating.
            try:
                measurement = MeasurementFactory.get_measurement(
                    node.measurement,
                    self._git_client,
                    self._repo_url,
                    self._model_client,
                    self._trivy_runner,
                    self._issue_store,
                )
                output = await measurement.execute()
            except SqmKitError as error:
                return EvaluationNode(
                    name=node.name,
                    weight=node.weight,
                    status=EvaluationStatus.ERRORED,
                    score=0.0,
                    reason=self._error_reason(error),
                    evaluated_measurements=0,
                    total_measurements=1,
                    coverage=0.0,
                )
            except Exception as error:  # keep the run going
                return EvaluationNode(
                    name=node.name,
                    weight=node.weight,
                    status=EvaluationStatus.ERRORED,
                    score=0.0,
                    reason=self._error_reason(error, unexpected=True),
                    evaluated_measurements=0,
                    total_measurements=1,
                    coverage=0.0,
                )

            status = output.status
            evaluated = 1 if status is EvaluationStatus.EVALUATED else 0
            return EvaluationNode(
                name=node.name,
                weight=node.weight,
                status=status,
                score=output.score,
                reason=output.reason,
                evaluated_measurements=evaluated,
                total_measurements=1,
                coverage=float(evaluated),
            )
        # recursive step - node has children
        else:
            children = [await self.evaluate(child) for child in node.submodels]
            # Only aggregate over evaluated children and renormalize their weights, so skipped/errored measurements do not drag the score towards zero.
            evaluated_children = [
                child
                for child in children
                if child.status is EvaluationStatus.EVALUATED
            ]
            total_weight = sum(child.weight for child in evaluated_children)
            weighted_score = (
                sum(child.weight * child.score for child in evaluated_children)
                / total_weight
                if total_weight > 0
                else 0.0
            )
            if evaluated_children:
                status = EvaluationStatus.EVALUATED
                reason = "Weighted score of evaluated measurements"
            elif any(child.status is EvaluationStatus.ERRORED for child in children):
                status = EvaluationStatus.ERRORED
                reason = "No measurement could be evaluated; at least one failed."
            else:
                status = EvaluationStatus.SKIPPED
                reason = "No measurement could be evaluated for this node."
            evaluated_measurements = sum(
                child.evaluated_measurements for child in children
            )
            total_measurements = sum(child.total_measurements for child in children)
            coverage = (
                evaluated_measurements / total_measurements
                if total_measurements > 0
                else 0.0
            )
            return EvaluationNode(
                name=node.name,
                weight=node.weight,
                status=status,
                score=weighted_score,
                reason=reason,
                children=children,
                evaluated_measurements=evaluated_measurements,
                total_measurements=total_measurements,
                coverage=coverage,
            )

    @staticmethod
    def _error_reason(error: Exception, *, unexpected: bool = False) -> str:
        prefix = "Unexpected error" if unexpected else "Evaluation failed"
        return f"{prefix}: {type(error).__name__}: {error}"

    def _unmet_requirement(self, requirements: Sequence[Requirement]) -> str | None:
        """Return a skip reason if a required capability is not available."""
        for requirement in requirements:
            if requirement is Requirement.TRIVY and not self._has_trivy:
                return "Trivy is not installed, measurement skipped."
            if requirement is Requirement.MODEL and not self._model_client.has_models():
                return "No model configured, measurement skipped."
            if requirement is Requirement.FORGE:
                forge_reason = self._unmet_forge_requirement()
                if forge_reason is not None:
                    return forge_reason
        return None

    def _unmet_forge_requirement(self) -> str | None:
        """Return a skip reason if issue-tracker access is unavailable."""
        if self._repo_url is None:
            return "No GitHub/GitLab remote found, measurement skipped."

        host = self._repo_url.host or ""
        if "github" in host:
            if not settings.github_api_key:
                return "GitHub API key not configured, measurement skipped."
            return None
        if "gitlab" in host:
            if not settings.gitlab_api_key:
                return "GitLab API key not configured, measurement skipped."
            return None
        return "Unsupported forge, measurement skipped."
