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

import pytest
from pydantic import HttpUrl

from sqmkit.clients.issue_tracker.gitlab_issue_tracker import GitlabIssueTracker
from sqmkit.config import settings


@pytest.mark.skipif(not settings.gitlab_api_key, reason="GITLAB_API_KEY not set")
@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_gitlab_issue_count():
    issue_tracker_url = HttpUrl(
        "https://gitlab.com/civitas-connect/civitas-core/civitas-core-v1/civitas-core"
    )

    issue_tracker = GitlabIssueTracker(issue_tracker_url)
    six_months_ago = datetime.now(UTC) - timedelta(days=180)
    issues = await issue_tracker.get_issues(six_months_ago)
    assert isinstance(issues, list)


@pytest.mark.skipif(not settings.gitlab_api_key, reason="GITLAB_API_KEY not set")
@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_opencode_gitlab_issue_count():
    issue_tracker_url = HttpUrl(
        "https://gitlab.opencode.de/DEUTSCHLAND.DIGITAL/l1/backend"
    )

    issue_tracker = GitlabIssueTracker(issue_tracker_url)
    six_months_ago = datetime.now(UTC) - timedelta(days=180)
    issues = await issue_tracker.get_issues(six_months_ago)
    assert isinstance(issues, list)
