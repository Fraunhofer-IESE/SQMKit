# Copyright (C) Fraunhofer IESE 2026 Matthias Gerbershagen, Jonathan Ullrich, Julien Siebert, Prateek Kumar Sharma
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


from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anyio import Path

from sqmkit.exceptions import MeasurementError
from sqmkit.measurements import EvaluationStatus
from sqmkit.measurements.code_quality.code_duplication import CodeDuplication


def create_tool_result(
    failure: bool,
    duplicate_rate_pct: float = 0.0,
    total_nloc: int = 100,
):
    """Create a mocked ToolResult returned by LizardRunner."""
    tool_result = MagicMock()
    tool_result.failure = failure
    tool_result.output = {
        "duplicate_rate_pct": duplicate_rate_pct,
        "total_nloc": total_nloc,
    }
    return tool_result


@pytest.mark.anyio
async def test_code_duplication_lizard_failure(repo_dir: Path):
    """Verify that a failed Lizard execution raises so the node is ERRORED."""

    tool_result = create_tool_result(failure=True)

    with patch(
        "sqmkit.measurements.code_quality.code_duplication.LizardRunner"
    ) as mock_runner:
        mock_runner.return_value.run = AsyncMock(return_value=tool_result)

        check = CodeDuplication(repo_dir)
        with pytest.raises(
            MeasurementError, match="Lizard failed to analyze the repository"
        ):
            await check.execute()


@pytest.mark.anyio
async def test_code_duplication_skips_without_source(repo_dir: Path):
    """Verify that a repository with no analyzable source is skipped."""

    tool_result = create_tool_result(failure=False, total_nloc=0)

    with patch(
        "sqmkit.measurements.code_quality.code_duplication.LizardRunner"
    ) as mock_runner:
        mock_runner.return_value.run = AsyncMock(return_value=tool_result)

        check = CodeDuplication(repo_dir)
        result = await check.execute()

    assert result.status == EvaluationStatus.SKIPPED
    assert result.score == 0.0
    assert "No analyzable source code" in result.reason


@pytest.mark.parametrize(
    ("duplicate_rate_pct", "expected_score"),
    [
        (0.0, 1.0),
        (25.0, 0.75),
        (50.0, 0.50),
        (75.0, 0.25),
        (100.0, 0.0),
    ],
)
@pytest.mark.anyio
async def test_code_duplication_score(
    repo_dir: Path,
    duplicate_rate_pct: float,
    expected_score: float,
):
    """Verify that the duplication percentage is converted into the correct score."""

    tool_result = create_tool_result(
        failure=False,
        duplicate_rate_pct=duplicate_rate_pct,
    )

    with patch(
        "sqmkit.measurements.code_quality.code_duplication.LizardRunner"
    ) as mock_runner:
        mock_runner.return_value.run = AsyncMock(return_value=tool_result)

        check = CodeDuplication(repo_dir)
        result = await check.execute()

    assert result.status == EvaluationStatus.EVALUATED
    assert result.score == expected_score
    assert (
        result.reason
        == f"Lizard has calculated a duplication rate of {duplicate_rate_pct:.2f}%"
    )
