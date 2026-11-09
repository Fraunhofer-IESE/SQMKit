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


from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import override

from sqmkit.clients.git_client import GitClient
from sqmkit.measurements import EvaluationStatus, Measurement, MeasurementOutput


class BusFactor(Measurement):
    _TIME_RANGE_DAYS = 180
    _MAX_CONTRIBUTORS = 3
    _MIN_COMMITS_PER_CONTRIBUTOR = 3

    _BOT_KEYWORDS = (
        "bot",
        "github-actions",
    )

    def __init__(self, git_client: GitClient):
        self.git_client = git_client

    def _is_bot(self, name: str, email: str) -> bool:
        combined = f"{name} {email}".lower()
        return any(bot in combined for bot in BusFactor._BOT_KEYWORDS)

    def _normalize_identity(self, name: str, email: str) -> str:
        name = name.strip().lower()
        email = email.strip().lower()

        if email:
            return email
        return name

    @override
    async def execute(self) -> MeasurementOutput:
        if not self.git_client.is_git_repo:
            return MeasurementOutput(
                status=EvaluationStatus.SKIPPED,
                score=0.0,
                reason="No Git history found, bus factor cannot be evaluated.",
            )

        # Get current time and cutoff time
        now = datetime.now(UTC)
        cutoff = now - timedelta(days=BusFactor._TIME_RANGE_DAYS)

        # Get git log
        commits = await self.git_client.get_commits(since=cutoff)

        if not commits:
            return MeasurementOutput(
                status=EvaluationStatus.SKIPPED,
                score=0.0,
                reason="No commits found in the repository.",
            )

        # Filter out bot commits, keep only human commits
        human_commits = [
            c for c in commits if not self._is_bot(c.author_name, c.author_email)
        ]

        # Only bots, no human commits
        if not human_commits:
            return MeasurementOutput(
                status=EvaluationStatus.EVALUATED,
                score=0.0,
                reason="Only commits from bot accounts were found in the repository.",
            )

        # Contributor calculation, count distinct contributors in time range
        commit_counts: dict[str, int] = defaultdict(int)

        for c in human_commits:
            if c.authored_date < cutoff:
                continue

            contributor_id = self._normalize_identity(c.author_name, c.author_email)
            commit_counts[contributor_id] += 1

        # Keep only frequent committers
        frequent_contributors = [
            contributor_id
            for contributor_id, count in commit_counts.items()
            if count >= BusFactor._MIN_COMMITS_PER_CONTRIBUTOR
        ]

        number_of_contributors = len(frequent_contributors)
        contributor_score = min(
            (number_of_contributors / BusFactor._MAX_CONTRIBUTORS), 1.0
        )

        if number_of_contributors == 1:
            reason = (
                "1 active contributor was found in the last "
                f"{BusFactor._TIME_RANGE_DAYS} days, having contributed at least "
                f"{BusFactor._MIN_COMMITS_PER_CONTRIBUTOR} commits."
            )
        else:
            reason = (
                f"{number_of_contributors} active contributors were found in the "
                f"last {BusFactor._TIME_RANGE_DAYS} days, each having contributed "
                f"at least {BusFactor._MIN_COMMITS_PER_CONTRIBUTOR} commits."
            )

        return MeasurementOutput(
            status=EvaluationStatus.EVALUATED,
            score=contributor_score,
            reason=reason,
        )
