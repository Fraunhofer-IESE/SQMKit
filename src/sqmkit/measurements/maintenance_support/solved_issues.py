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
from typing import override

from pydantic import HttpUrl

from sqmkit.clients.issue_tracker import IssueStore
from sqmkit.clients.issue_tracker.issue_tracker_factory import IssueTrackerFactory
from sqmkit.exceptions import IssueTrackerError, MeasurementError
from sqmkit.measurements import (
    EvaluationStatus,
    Measurement,
    MeasurementOutput,
    Requirement,
)


class SolvedIssues(Measurement):
    requires = (Requirement.FORGE,)

    def __init__(
        self,
        repo_url: HttpUrl | None,
        issue_store: IssueStore | None = None,
    ):
        self.repo_url = repo_url
        self.issue_store = issue_store

    async def _get_issues(self, end_date: datetime):
        if self.issue_store is not None:
            return await self.issue_store.get_issues(end_date)
        if self.repo_url is None:
            return []
        tracker = IssueTrackerFactory.create_issue_tracker(self.repo_url)
        return await tracker.get_issues(end_date)

    @override
    async def execute(self) -> MeasurementOutput:
        if not self.repo_url:
            return MeasurementOutput(
                status=EvaluationStatus.SKIPPED,
                score=0.0,
                reason="No repository URL provided.",
            )

        six_months_ago = datetime.now(UTC) - timedelta(days=180)
        # TODO: count issues closed in the last 6 months even when they were created earlier; the trackers currently restrict by creation date.
        try:
            issues = await self._get_issues(six_months_ago)
        except IssueTrackerError as error:
            raise MeasurementError(str(error)) from error

        closed_issues = sum(
            1
            for issue in issues
            if issue.state == "closed"
            and issue.closed_at
            and issue.closed_at >= six_months_ago
        )
        open_issues = sum(1 for issue in issues if issue.state in ["open", "opened"])
        all_issues = open_issues + closed_issues

        # if we have 0 open issues, we optimistically return a score of 1, else we calculate the ratio of closed to all issues
        score = closed_issues / all_issues if open_issues > 0 else 1

        return MeasurementOutput(
            status=EvaluationStatus.EVALUATED,
            score=score,
            reason=f"{closed_issues} closed and {open_issues} open issues in the last six months.",
        )
