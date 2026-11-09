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

from collections.abc import Callable

import pytest
from anyio import Path
from pydantic import HttpUrl

from sqmkit.clients.model_client import ModelClient
from sqmkit.evaluation import Evaluator, QualityModel, QualityModelNode
from sqmkit.exceptions import MeasurementError
from sqmkit.measurements import EvaluationStatus, MeasurementOutput
from sqmkit.measurements.measurement_factory import MeasurementFactory, MeasurementIds
from tests.support import GitClientFactory


class _FakeMeasurement:
    def __init__(
        self,
        score: float = 1.0,
        status: EvaluationStatus = EvaluationStatus.EVALUATED,
        error: Exception | None = None,
    ) -> None:
        self._score = score
        self._status = status
        self._error = error

    async def execute(self) -> MeasurementOutput:
        if self._error is not None:
            raise self._error
        return MeasurementOutput(
            status=self._status,
            score=self._score,
            reason="fake",
        )


def _build_evaluator(
    root: QualityModelNode,
    model_client: ModelClient,
    make_git_client: GitClientFactory,
) -> Evaluator:
    return Evaluator(
        quality_model=QualityModel(root=root),
        git_client=make_git_client(Path("/tmp")),  # type: ignore[arg-type]
        repo_url=HttpUrl("https://github.com/example/repo"),
        model_client=model_client,
    )


def _measurement_node(
    name: str,
    measurement: MeasurementIds,
    weight: float = 1,
) -> QualityModelNode:
    return QualityModelNode(
        name=name,
        weight=weight,
        measurement=measurement,
    )


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_measurement_requiring_missing_trivy_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
    make_model_client: Callable[..., ModelClient],
    make_git_client: GitClientFactory,
) -> None:
    monkeypatch.setattr(
        "sqmkit.tools.trivy_runner.TrivyRunner.is_available", lambda: False
    )
    root = QualityModelNode(
        name="Vulnerabilities",
        weight=1,
        measurement=MeasurementIds.VULNERABILITIES,
    )

    node = await _build_evaluator(root, make_model_client(), make_git_client).evaluate()

    assert node.status is EvaluationStatus.SKIPPED
    assert node.score == 0.0
    assert "Trivy" in node.reason


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_measurement_requiring_missing_model_is_skipped(
    make_model_client: Callable[..., ModelClient],
    make_git_client: GitClientFactory,
) -> None:
    root = QualityModelNode(
        name="Security Policy",
        weight=1,
        measurement=MeasurementIds.SECURITY_POLICY,
    )

    node = await _build_evaluator(
        root, make_model_client(models=0), make_git_client
    ).evaluate()

    assert node.status is EvaluationStatus.SKIPPED
    assert node.score == 0.0
    assert "No model" in node.reason


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_unevaluated_children_are_excluded_and_weights_renormalized(
    monkeypatch: pytest.MonkeyPatch,
    make_model_client: Callable[..., ModelClient],
    make_git_client: GitClientFactory,
) -> None:
    monkeypatch.setattr(
        "sqmkit.tools.trivy_runner.TrivyRunner.is_available", lambda: False
    )

    def fake_get_measurement(*_args: object, **_kwargs: object) -> object:
        return _FakeMeasurement(score=1.0)

    monkeypatch.setattr(
        MeasurementFactory, "get_measurement", staticmethod(fake_get_measurement)
    )

    root = QualityModelNode(
        name="root",
        weight=1,
        measurement=None,
        submodels=[
            QualityModelNode(
                name="skipped",
                weight=0.5,
                measurement=MeasurementIds.VULNERABILITIES,
            ),
            QualityModelNode(
                name="evaluated",
                weight=0.5,
                measurement=MeasurementIds.SBOM_AVAILABILITY,
            ),
        ],
    )

    node = await _build_evaluator(root, make_model_client(), make_git_client).evaluate()

    assert [child.status for child in node.children] == [
        EvaluationStatus.SKIPPED,
        EvaluationStatus.EVALUATED,
    ]
    # Only the evaluated child counts: its weight is renormalized to 1.0.
    assert node.status is EvaluationStatus.EVALUATED
    assert node.score == 1.0
    assert node.evaluated_measurements == 1
    assert node.total_measurements == 2
    assert node.coverage == 0.5


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_forge_measurement_without_remote_is_skipped(
    make_model_client: Callable[..., ModelClient],
    make_git_client: GitClientFactory,
) -> None:
    root = QualityModelNode(
        name="Solved Issues",
        weight=1,
        measurement=MeasurementIds.SOLVED_ISSUES,
    )
    evaluator = Evaluator(
        quality_model=QualityModel(root=root),
        git_client=make_git_client(Path("/tmp")),  # type: ignore[arg-type]
        repo_url=None,
        model_client=make_model_client(),
    )

    node = await evaluator.evaluate()

    assert node.status is EvaluationStatus.SKIPPED
    assert "remote" in node.reason.lower()
    assert node.coverage == 0.0


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_failing_measurement_does_not_abort_siblings(
    monkeypatch: pytest.MonkeyPatch,
    make_model_client: Callable[..., ModelClient],
    make_git_client: GitClientFactory,
) -> None:
    def fake_get_measurement(
        measurement_id: MeasurementIds, *_args: object, **_kwargs: object
    ) -> object:
        if measurement_id is MeasurementIds.SECURITY_POLICY:
            return _FakeMeasurement(error=MeasurementError("trivy exploded"))
        return _FakeMeasurement(score=1.0)

    monkeypatch.setattr(
        MeasurementFactory, "get_measurement", staticmethod(fake_get_measurement)
    )

    root = QualityModelNode(
        name="root",
        weight=1,
        measurement=None,
        submodels=[
            _measurement_node(
                "broken",
                MeasurementIds.SECURITY_POLICY,
                weight=0.5,
            ),
            _measurement_node(
                "works", MeasurementIds.SBOM_AVAILABILITY, weight=0.5
            ),
        ],
    )

    node = await _build_evaluator(root, make_model_client(), make_git_client).evaluate()

    broken, works = node.children
    assert broken.status is EvaluationStatus.ERRORED
    assert "MeasurementError" in broken.reason
    assert works.status is EvaluationStatus.EVALUATED
    assert node.status is EvaluationStatus.EVALUATED
    assert node.score == 1.0
    assert node.evaluated_measurements == 1
    assert node.total_measurements == 2
    assert node.coverage == 0.5


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_parent_with_only_failed_children_is_errored(
    monkeypatch: pytest.MonkeyPatch,
    make_model_client: Callable[..., ModelClient],
    make_git_client: GitClientFactory,
) -> None:
    def fake_get_measurement(*_args: object, **_kwargs: object) -> object:
        return _FakeMeasurement(error=MeasurementError("boom"))

    monkeypatch.setattr(
        MeasurementFactory, "get_measurement", staticmethod(fake_get_measurement)
    )

    root = QualityModelNode(
        name="root",
        weight=1,
        measurement=None,
        submodels=[
            _measurement_node(
                "a", MeasurementIds.SBOM_AVAILABILITY, weight=0.5
            ),
            _measurement_node(
                "b",
                MeasurementIds.PROJECT_STRUCTURE,
                weight=0.5,
            ),
        ],
    )

    node = await _build_evaluator(root, make_model_client(), make_git_client).evaluate()

    assert node.status is EvaluationStatus.ERRORED
    assert node.score == 0.0
    assert all(child.status is EvaluationStatus.ERRORED for child in node.children)


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_node_without_evaluated_children_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
    make_model_client: Callable[..., ModelClient],
    make_git_client: GitClientFactory,
) -> None:
    monkeypatch.setattr(
        "sqmkit.tools.trivy_runner.TrivyRunner.is_available", lambda: False
    )
    root = QualityModelNode(
        name="root",
        weight=1,
        measurement=None,
        submodels=[
            QualityModelNode(
                name="skipped",
                weight=1,
                measurement=MeasurementIds.VULNERABILITIES,
            ),
        ],
    )

    node = await _build_evaluator(root, make_model_client(), make_git_client).evaluate()

    assert node.status is EvaluationStatus.SKIPPED
    assert node.score == 0.0
