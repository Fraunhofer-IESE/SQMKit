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

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from sqmkit.measurements import EvaluationStatus
from sqmkit.measurements.maintenance_support.commit_trend import CommitTrend


def mock_git_client(
    first_commit_days_ago: int | None, monthly_counts: list[int]
) -> AsyncMock:
    """Return a mocked GitClient that reports the given first commit age and monthly commit counts in order."""
    mock_client = AsyncMock()

    if first_commit_days_ago is None:
        mock_client.get_first_commit_date.return_value = None
    else:
        mock_client.get_first_commit_date.return_value = datetime.now(UTC) - timedelta(
            days=first_commit_days_ago
        )

    mock_client.get_commit_count.side_effect = monthly_counts
    mock_client.is_git_repo = True

    return mock_client


@pytest.mark.anyio
async def test_commit_trend_skips_without_git_history():
    mock_client = mock_git_client(first_commit_days_ago=None, monthly_counts=[])
    mock_client.is_git_repo = False

    check = CommitTrend(mock_client)
    result = await check.execute()

    assert result.status is EvaluationStatus.SKIPPED
    assert "No Git history" in result.reason


@pytest.mark.anyio
async def test_commit_trend_no_commits():
    mock_client = mock_git_client(first_commit_days_ago=None, monthly_counts=[])

    check = CommitTrend(mock_client)
    result = await check.execute()

    assert result.score == 0.0
    assert "trend cannot be evaluated" in result.reason


@pytest.mark.anyio
async def test_commit_trend_history_shorter_than_3_months():
    # First commit only 60 days ago → below the 90-day threshold
    mock_client = mock_git_client(first_commit_days_ago=60, monthly_counts=[])

    check = CommitTrend(mock_client)
    result = await check.execute()

    assert result.score == 0.0
    assert "trend cannot be evaluated" in result.reason


@pytest.mark.anyio
async def test_commit_trend_no_commits_in_last_3_months():
    # Median > 0 but last 3 months are all zero
    monthly_counts = [10, 8, 12, 9, 11, 0, 0, 0]

    mock_client = mock_git_client(
        first_commit_days_ago=(len(monthly_counts) - 1) * 30,
        monthly_counts=monthly_counts,
    )

    check = CommitTrend(mock_client)
    result = await check.execute()

    assert result.score == 0.0
    assert "last 3 months" in result.reason


@pytest.mark.anyio
async def test_commit_trend_zero_median():
    # Most months have 0 commits → median == 0
    monthly_counts = [0, 0, 0, 0, 0, 0, 0, 5]

    mock_client = mock_git_client(
        first_commit_days_ago=(len(monthly_counts) - 1) * 30,
        monthly_counts=monthly_counts,
    )

    check = CommitTrend(mock_client)
    result = await check.execute()

    assert result.score == 0.0
    assert "median" in result.reason


@pytest.mark.parametrize(
    "monthly_counts,expected_score",
    [
        # ratio ≈ 0.1  → score 0.25  (avg_last_3=1, median=10)
        ([10, 10, 10, 10, 10, 1, 1, 1], 0.25),
        # ratio ≈ 0.375 → score 0.5  (avg_last_3=3, median=8)
        ([8, 8, 8, 8, 8, 3, 3, 3], 0.5),
        # ratio ≈ 0.625 → score 0.75 (avg_last_3=5, median=8)
        ([8, 8, 8, 8, 8, 5, 5, 5], 0.75),
        # ratio ≈ 1.0   → score 1.0  (avg_last_3=10, median=10)
        ([10, 10, 10, 10, 10, 10, 10, 10], 1.0),
        # ratio > 1.0   → score 1.0  (avg_last_3=20, median=10 — burst of activity)
        ([10, 10, 10, 10, 10, 20, 20, 20], 1.0),
    ],
)
@pytest.mark.anyio
async def test_commit_trend_score_bands(
    monthly_counts: list[int],
    expected_score: float,
):
    mock_client = mock_git_client(
        first_commit_days_ago=(len(monthly_counts) - 1) * 30,
        monthly_counts=monthly_counts,
    )

    check = CommitTrend(mock_client)
    result = await check.execute()

    assert result.score == expected_score
    assert "ratio" in result.reason


@pytest.mark.parametrize(
    "avg_last_3,median,expected_score",
    [
        # exact boundary at 0.25 → score 0.25
        (1, 4, 0.25),
        # just above 0.25 → score 0.5
        (3, 10, 0.5),
        # exact boundary at 0.5 → score 0.5
        (1, 2, 0.5),
        # just above 0.5 → score 0.75
        (6, 10, 0.75),
        # exact boundary at 0.75 → score 0.75
        (3, 4, 0.75),
        # just above 0.75 → score 1.0
        (8, 10, 1.0),
    ],
)
@pytest.mark.anyio
async def test_commit_trend_score_band_boundaries(
    avg_last_3: int,
    median: int,
    expected_score: float,
):
    # Build a month list where the first N months all equal `median` and the last 3 months all equal `avg_last_3` (so avg == avg_last_3 exactly)
    padding = [median] * 5
    last_3 = [avg_last_3] * 3
    monthly_counts = padding + last_3

    mock_client = mock_git_client(
        first_commit_days_ago=(len(monthly_counts) - 1) * 30,
        monthly_counts=monthly_counts,
    )

    check = CommitTrend(mock_client)
    result = await check.execute()

    assert result.score == expected_score
