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
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from sqmkit.measurements import EvaluationStatus
from sqmkit.measurements.maintenance_support.bus_factor import BusFactor


def create_dummy_commit(
    name: str = "John Doe",
    email: str = "johndoe@example.com",
    days_ago: int = 0,
):
    return SimpleNamespace(
        author_name=name,
        author_email=email,
        authored_date=datetime.now(UTC) - timedelta(days=days_ago),
    )


@pytest.mark.anyio
async def test_bus_factor_skips_without_git_history():
    mock_client = AsyncMock()
    mock_client.is_git_repo = False

    check = BusFactor(mock_client)
    result = await check.execute()

    assert result.status is EvaluationStatus.SKIPPED
    assert result.score == 0.0
    assert "No Git history" in result.reason


@pytest.mark.anyio
async def test_bus_factor_no_commits():
    mock_client = AsyncMock()
    mock_client.is_git_repo = True
    mock_client.get_commits.return_value = []

    check = BusFactor(mock_client)
    result = await check.execute()

    assert result.status is EvaluationStatus.SKIPPED
    assert result.score == 0.0
    assert "No commits found" in result.reason


@pytest.mark.anyio
async def test_bus_factor_only_bot_commits():
    mock_client = AsyncMock()
    mock_client.get_commits.return_value = [
        create_dummy_commit(name="dependabot", email="dependabot@github.com"),
        create_dummy_commit(name="github-actions", email="actions@github.com"),
    ]

    check = BusFactor(mock_client)
    result = await check.execute()

    assert result.status is EvaluationStatus.EVALUATED
    assert result.score == 0.0
    assert "Only commits from bot accounts" in result.reason


@pytest.mark.parametrize(
    "num_contributors,expected_score",
    [
        (0, 0.0),
        (1, 1 / BusFactor._MAX_CONTRIBUTORS),  # type: ignore
        (2, 2 / BusFactor._MAX_CONTRIBUTORS),  # type: ignore
        (3, 1.0),
        (5, 1.0),
    ],
)
@pytest.mark.anyio
async def test_bus_factor_frequent_contributors_scoring(
    num_contributors: int,
    expected_score: float,
):
    commits: list[SimpleNamespace] = []

    if num_contributors == 0:
        # Commits exist, but below MIN_COMMITS_PER_CONTRIBUTOR → 0 frequent contributors (NOT "no commits")
        commits = [
            create_dummy_commit()
            for _ in range(BusFactor._MIN_COMMITS_PER_CONTRIBUTOR - 1)  # type: ignore
        ]
    else:
        for i in range(num_contributors):
            for _ in range(BusFactor._MIN_COMMITS_PER_CONTRIBUTOR):  # type: ignore
                commits.append(
                    create_dummy_commit(
                        name=f"user{i}",
                        email=f"user{i}@example.com",
                        days_ago=1,
                    )
                )

    mock_client = AsyncMock()
    mock_client.get_commits.return_value = commits

    check = BusFactor(mock_client)
    result = await check.execute()

    assert result.status is EvaluationStatus.EVALUATED
    assert result.score == expected_score
    if num_contributors == 1:
        assert "1 active contributor was found" in result.reason
    else:
        assert f"{num_contributors} active contributors were found" in result.reason


@pytest.mark.anyio
async def test_bus_factor_mixed_bot_and_human_commits():
    commits = [
        create_dummy_commit(name="dependabot", email="dependabot@github.com"),
        create_dummy_commit(name="github-actions", email="actions@github.com"),
    ]

    for _ in range(BusFactor._MIN_COMMITS_PER_CONTRIBUTOR):  # type: ignore
        commits.append(create_dummy_commit())

    mock_client = AsyncMock()
    mock_client.get_commits.return_value = commits

    check = BusFactor(mock_client)
    result = await check.execute()

    assert result.status is EvaluationStatus.EVALUATED
    assert result.score == 1 / BusFactor._MAX_CONTRIBUTORS  # type: ignore
    assert "1 active contributor was found" in result.reason


@pytest.mark.anyio
async def test_bus_factor_commits_outside_time_range():
    commits = [
        create_dummy_commit(days_ago=BusFactor._TIME_RANGE_DAYS + 10)  # type: ignore
        for _ in range(BusFactor._MIN_COMMITS_PER_CONTRIBUTOR)  # type: ignore
    ]

    mock_client = AsyncMock()
    mock_client.get_commits.return_value = commits

    check = BusFactor(mock_client)
    result = await check.execute()

    assert result.status is EvaluationStatus.EVALUATED
    assert result.score == 0.0
    assert "0 active contributors were found" in result.reason
