# Copyright (C) Fraunhofer IESE 2026 Jonathan Ullrich, Matthias Gerbershagen
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


from sqmkit.measurements.code_quality.code_duplication import CodeDuplication
from sqmkit.measurements.code_quality.project_structure_best_practices import (
    ProjectStructureBestPractices,
)

__all__ = ["CodeDuplication", "ProjectStructureBestPractices"]
