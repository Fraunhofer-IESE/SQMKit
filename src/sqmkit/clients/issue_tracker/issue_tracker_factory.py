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

from pydantic import HttpUrl

from sqmkit.clients.issue_tracker.github_issue_tracker import GithubIssueTracker
from sqmkit.clients.issue_tracker.gitlab_issue_tracker import GitlabIssueTracker
from sqmkit.clients.issue_tracker.issue_tracker import IssueTracker
from sqmkit.exceptions import IssueTrackerError

_GITHUB = "github"
_GITLAB = "gitlab"


class IssueTrackerFactory:
    @staticmethod
    def create_issue_tracker(issue_tracker_url: HttpUrl) -> IssueTracker:
        host = issue_tracker_url.host
        if not host:
            raise IssueTrackerError(
                "Invalid issue tracker url or issue tracker not supported"
            )
        if _GITHUB in host:
            return GithubIssueTracker(issue_tracker_url)
        if _GITLAB in host:
            return GitlabIssueTracker(issue_tracker_url)
        raise IssueTrackerError(f"Issue Tracker {issue_tracker_url!s} not supported!")
