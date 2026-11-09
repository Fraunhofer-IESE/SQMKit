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

"""Base class for measurements that rely on one or more configured models."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar, override

from sqmkit.measurements.measurement import (
    Measurement,
    MeasurementOutput,
    Requirement,
)

if TYPE_CHECKING:
    from sqmkit.clients.model_client import ModelClient


class ModelMeasurement(Measurement, ABC):
    """Base class for measurements that use one or more configured models. The ``Model`` requirement guarantees that ``self.model_client`` has at least one model before this runs, so there is no no-model handling here."""

    requires: ClassVar[tuple[Requirement, ...]] = (Requirement.MODEL,)

    model_client: "ModelClient"

    @override
    async def execute(self) -> MeasurementOutput:
        return await self.evaluate()

    @abstractmethod
    async def evaluate(self) -> MeasurementOutput:
        """Run the measurement with at least one configured model."""
