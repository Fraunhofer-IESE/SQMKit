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

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar


class Requirement(StrEnum):
    """External capability a measurement depends on to run."""

    TRIVY = "Trivy"
    MODEL = "Model"
    FORGE = "Forge"


class EvaluationStatus(StrEnum):
    """How a measurement contributed to the result tree: ``EVALUATED`` produced a score (including 0 for a genuinely absent artifact such as a missing SECURITY.md), ``SKIPPED`` is not applicable or has an unavailable prerequisite, and ``ERRORED`` means it was applicable but the run failed."""

    EVALUATED = "evaluated"
    SKIPPED = "skipped"
    ERRORED = "errored"


@dataclass
class MeasurementOutput:
    """Result of a measurement. A measurement only ever returns ``EVALUATED`` or ``SKIPPED``. Execution failures raise a ``SqmKitError`` instead, which the evaluator turns into an ``ERRORED`` result."""

    status: EvaluationStatus
    score: float
    reason: str


class Measurement(ABC):
    """A measurement and the external capabilities it needs. Requirements are part of the measurement's metadata, so a quality model only declares which measurements it uses."""

    requires: ClassVar[tuple[Requirement, ...]] = ()

    @abstractmethod
    async def execute(self) -> MeasurementOutput:
        pass
