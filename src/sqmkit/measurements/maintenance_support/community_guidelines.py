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

from types import MappingProxyType
from typing import override

from anyio import Path

from sqmkit.measurements import EvaluationStatus, Measurement, MeasurementOutput
from sqmkit.measurements.repo_file_utils import RepositoryFile, find_file


class CommunityGuidelines(Measurement):
    _COMMUNITY_FILES = (
        RepositoryFile.CODE_OF_CONDUCT,
        RepositoryFile.CONTRIBUTING,
    )
    _LABELS = MappingProxyType(
        {
            RepositoryFile.CODE_OF_CONDUCT: "Code of Conduct",
            RepositoryFile.CONTRIBUTING: "Contributing guidelines",
        }
    )

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path

    @override
    async def execute(self) -> MeasurementOutput:
        score = 0.0
        reasons: list[str] = []

        per_file_score = 1 / len(CommunityGuidelines._COMMUNITY_FILES)

        # Run checks for each file type
        for file_type in CommunityGuidelines._COMMUNITY_FILES:
            file_found = await find_file(self.repo_path, file_type)

            label = CommunityGuidelines._LABELS[file_type]
            if file_found:
                score += per_file_score
                reasons.append(f"{label}: present")
            else:
                reasons.append(f"{label}: missing")

        reason = "; ".join(reasons)
        return MeasurementOutput(
            status=EvaluationStatus.EVALUATED,
            score=score,
            reason=reason,
        )
