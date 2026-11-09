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
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import HttpUrl

from sqmkit.clients.issue_tracker import Issue
from sqmkit.measurements import MeasurementOutput
from sqmkit.measurements.maintenance_support.solved_issues import SolvedIssues


def days_ago(n: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=n)


@pytest.mark.anyio
async def test_solved_issues_with_mock_data() -> None:
    mock_issues = [
        Issue(
            id="1",
            title="Fix bug A",
            state="closed",
            author="dev1",
            created_at=days_ago(500),
            closed_at=days_ago(499),  # closed earlier than 6 months ago
            comments=[],
        ),
        Issue(
            id="2",
            title="Add feature X",
            state="closed",
            author="dev2",
            created_at=days_ago(90),
            closed_at=days_ago(10),
            comments=[],
        ),
        Issue(
            id="3",
            title="Open issue Y",
            state="open",
            author="dev3",
            created_at=days_ago(30),
            closed_at=None,
            comments=[],
        ),
        Issue(
            id="4",
            title="Open issue X",
            state="open",
            author="dev1",
            created_at=days_ago(30),
            closed_at=None,
            comments=[],
        ),
        Issue(
            id="5",
            title="Open issue Z",
            state="open",
            author="dev2",
            created_at=days_ago(30),
            closed_at=None,
            comments=[],
        ),
    ]

    mock_issue_tracker = AsyncMock()
    mock_issue_tracker.get_issues.return_value = mock_issues

    with patch(
        "sqmkit.measurements.maintenance_support.solved_issues.IssueTrackerFactory.create_issue_tracker",
        return_value=mock_issue_tracker,
    ):
        mocked_solved_issues = SolvedIssues(
            repo_url=HttpUrl("https://mock.github.url/john/doe")
        )
        result: MeasurementOutput = await mocked_solved_issues.execute()

    assert result.score == 0.25
    assert "open issues in the last six months." in result.reason
