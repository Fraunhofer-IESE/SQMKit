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
from enum import Enum

import pytest
from anyio import Path

from sqmkit.clients.model_client import ModelClient
from sqmkit.measurements import EvaluationStatus
from sqmkit.measurements.security.security_policy_best_practices import (
    SecurityPolicyBestPractices,
)
from tests.support import RepoDir


class SecurityPolicyTestFile(Path, Enum):
    POOR = Path("./tests/test_data/test_data_security_policies/SECURITY.poor.md")
    MEDIUM = Path("./tests/test_data/test_data_security_policies/SECURITY.medium.md")
    GOOD = Path("./tests/test_data/test_data_security_policies/SECURITY.good.md")


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_no_security_policy(repo_dir: Path, model_client: ModelClient):
    measurement = SecurityPolicyBestPractices(repo_dir, model_client)
    result = await measurement.execute()

    assert result.status is EvaluationStatus.EVALUATED
    assert result.score == 0.0
    assert result.reason == "SECURITY.md file not found in root folder."


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_empty_security_policy(repo_dir: RepoDir, model_client: ModelClient):
    await repo_dir.add_file("SECURITY.md", "")

    measurement = SecurityPolicyBestPractices(repo_dir, model_client)
    result = await measurement.execute()

    assert result.status is EvaluationStatus.EVALUATED
    assert result.score == 0.0
    assert "empty" in result.reason.lower()


@pytest.mark.parametrize(
    "file_type,expected_score_min,expected_score_max,stub_score",
    [
        (SecurityPolicyTestFile.POOR, 0.0, 0.4, 1),
        (SecurityPolicyTestFile.MEDIUM, 0.4, 0.75, 3),
        (SecurityPolicyTestFile.GOOD, 0.7, 1.0, 5),
    ],
)
@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_security_policy_best_practices(
    repo_dir: RepoDir,
    make_model_client: Callable[..., ModelClient],
    file_type: SecurityPolicyTestFile,
    expected_score_min: float,
    expected_score_max: float,
    stub_score: int,
):
    test_file_text = await file_type.read_text()
    await repo_dir.add_file("SECURITY.md", test_file_text)

    measurement = SecurityPolicyBestPractices(
        repo_dir, make_model_client(score=stub_score)
    )
    result = await measurement.execute()

    assert result.status is EvaluationStatus.EVALUATED
    assert expected_score_min <= result.score <= expected_score_max, (
        f"Expected score between {expected_score_min} and {expected_score_max}, got {result.score}"
    )
    assert "Evaluation of the SECURITY.md file:" in result.reason
