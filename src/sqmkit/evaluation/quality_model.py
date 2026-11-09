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

import json
import math
from pathlib import Path
from typing import Self

from pydantic import BaseModel, Field, model_validator

from sqmkit.measurements.measurement_factory import MeasurementIds


class QualityModelNode(BaseModel):
    name: str
    weight: float = Field(ge=0, le=1)
    measurement: MeasurementIds | None  # Pydantic throws error if not in MeasurementIds
    submodels: list["QualityModelNode"] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_has_submodels_or_measurement(self) -> Self:
        has_measurement = self.measurement is not None
        has_submodels = len(self.submodels) > 0

        if has_measurement and has_submodels:
            raise ValueError(
                f"Node '{self.name}' has both a measurement and submodels. A node must be either a measurement (leaf node) or a concept (intermediate node), not both."
            )
        if not has_measurement and not has_submodels:
            raise ValueError(
                f"Node '{self.name}' has neither a measurement nor submodels."
            )
        return self

    @model_validator(mode="after")
    def validate_sum_weights(self) -> Self:
        if self.submodels:
            total = sum(child.weight for child in self.submodels)
            # Compare with a tolerance: weights such as 0.7 + 0.2 + 0.1 sum to 0.9999999999999999 in binary floating point, which is not a typo.
            if not math.isclose(total, 1.0, abs_tol=1e-9):
                raise ValueError(
                    f"Node {self.name}'s weights of its {len(self.submodels)} children sum to {total}, but must sum to 1.0."
                )
        return self


class QualityModel(BaseModel):
    root: QualityModelNode

    @classmethod
    def from_json_file(cls, path: Path) -> "QualityModel":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(root=data)
