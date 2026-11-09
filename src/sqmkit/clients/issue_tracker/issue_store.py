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

from datetime import date, datetime

from sqmkit.clients.issue_tracker.issue_tracker import Issue, IssueTracker


class IssueStore:
    """Fetch issues once per cutoff date for all measurements of one repo."""

    def __init__(self, tracker: IssueTracker) -> None:
        self._tracker = tracker
        self._cache: dict[date, list[Issue]] = {}

    async def get_issues(self, end_date: datetime) -> list[Issue]:
        key = end_date.date()
        cached = self._cache.get(key)
        if cached is None:
            cached = await self._tracker.get_issues(end_date)
            self._cache[key] = cached
        return cached
