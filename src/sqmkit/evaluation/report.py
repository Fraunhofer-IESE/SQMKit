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

from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl

from sqmkit.evaluation.evaluation import EvaluationNode


class RepoKind(StrEnum):
    REMOTE = "remote"
    LOCAL = "local"


class RepoEvaluation(BaseModel):
    """Result of evaluating a single repository. Exactly one of ``evaluation`` and ``error`` is set: a repository that could not be resolved or evaluated still gets an entry, so callers can tell the difference between a failed repository and one that was never requested."""

    name: str
    kind: RepoKind
    source: str  # repository as supplied by the user
    repository: HttpUrl | None = None
    evaluation: EvaluationNode | None = None
    error: str | None = None


class EvaluationReport(BaseModel):
    """Machine-readable output of one CLI run."""

    schema_version: int = 1
    results: list[RepoEvaluation] = Field(default_factory=list)
