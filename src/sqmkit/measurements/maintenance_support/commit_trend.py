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


import statistics
from datetime import UTC, datetime, timedelta
from typing import override

from sqmkit.clients.git_client import GitClient
from sqmkit.measurements import EvaluationStatus, Measurement, MeasurementOutput


class CommitTrend(Measurement):
    def __init__(self, git_client: GitClient):
        self.git_client = git_client

    @override
    async def execute(self) -> MeasurementOutput:
        if not self.git_client.is_git_repo:
            return MeasurementOutput(
                status=EvaluationStatus.SKIPPED,
                score=0.0,
                reason="No Git history found, commit trend cannot be evaluated.",
            )

        now = datetime.now(UTC)

        # Get earliest commit date
        first_commit_date = await self.git_client.get_first_commit_date()

        # if there is no commit or the first commit is not older than 3 months, we cannot evaluate the commit trend Repo is too young, cannot make statement
        if not first_commit_date or first_commit_date > now - timedelta(days=90):
            return MeasurementOutput(
                status=EvaluationStatus.SKIPPED,
                score=0.0,
                reason="No commits in the repository or commit history shorter than 3 months; trend cannot be evaluated.",
            )

        monthly_commit_counts: list[int] = []
        current_start = first_commit_date.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )  # sets the current_start to the beginning of the month of the first commit date

        while current_start < now:
            current_end = current_start + timedelta(days=30)
            count = await self.git_client.get_commit_count(
                begin=current_start, end=current_end
            )
            monthly_commit_counts.append(count)
            current_start = current_end

        median_commits = statistics.median(monthly_commit_counts)
        last_3_months_counts = monthly_commit_counts[-3:]  # last 3 months commit counts
        average_commit_counts_last_three_months = sum(last_3_months_counts) / len(
            last_3_months_counts
        )

        if average_commit_counts_last_three_months == 0 or median_commits == 0:
            score = 0.0
            reason = (
                "No commits in the last 3 months or the median commit count is zero."
            )
        else:
            ratio = average_commit_counts_last_three_months / median_commits
            if 0 < ratio <= 0.25:
                score = 0.25
            elif 0.25 < ratio <= 0.5:
                score = 0.5
            elif 0.5 < ratio <= 0.75:
                score = 0.75
            else:
                score = 1.0
            reason = f"Average commits in the last 3 months are {average_commit_counts_last_three_months:.2f}, the median of commits is {median_commits:.2f}, evaluation based on the ratio {ratio:.2f}."

        return MeasurementOutput(
            status=EvaluationStatus.EVALUATED,
            score=score,
            reason=reason,
        )
