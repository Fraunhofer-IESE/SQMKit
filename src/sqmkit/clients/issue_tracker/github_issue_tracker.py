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

from datetime import datetime
from typing import Any, override
from urllib.parse import urlparse

from gql import Client, GraphQLRequest
from gql.transport.aiohttp import AIOHTTPTransport
from pydantic import HttpUrl

from sqmkit.clients.issue_tracker.issue_tracker import Comment, Issue, IssueTracker
from sqmkit.config import settings
from sqmkit.exceptions import IssueTrackerError


class GithubIssueTracker(IssueTracker):
    _GITHUB_API_URL = "https://api.github.com/graphql"
    _Z_SUFFIX = "Z"
    _ISO_SUFFIX = "+00:00"

    def __init__(self, url: HttpUrl):
        super().__init__(url)

        self.token = settings.github_api_key
        parsed_url = urlparse(str(url))
        path_parts = parsed_url.path.strip("/").split("/")
        if len(path_parts) >= 2:
            self.repo_owner = path_parts[0]
            self.repo_name = path_parts[1].removesuffix(".git")
        else:
            raise IssueTrackerError(
                "URL must be in the format 'https://github.com/owner/repo_name'"
            )

    def _parse_date_string(self, date: str) -> datetime:
        # handle the "Z" suffix in GitHub's ISO 8601 format
        normalized_date = date.replace(
            GithubIssueTracker._Z_SUFFIX, GithubIssueTracker._ISO_SUFFIX
        )
        return datetime.fromisoformat(normalized_date)

    def _create_gql_client(self) -> Client:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else None
        transport = AIOHTTPTransport(
            url=GithubIssueTracker._GITHUB_API_URL, headers=headers, ssl=True
        )
        return Client(transport=transport, execute_timeout=30)

    def _get_issue_query(self) -> str:
        return """
        query GetIssuesSinceDate($owner: String!, $repo: String!, $end_date: DateTime!, $cursor: String) {
            repository(owner: $owner, name: $repo) {
                issues(
                    first: 100,
                    filterBy: {since: $end_date},
                    orderBy: {field: CREATED_AT, direction: DESC},
                    after: $cursor
                ) {
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                    nodes {
                        id
                        title
                        body
                        state
                        createdAt
                        closedAt
                        author {
                            login
                        }
                        comments(first: 100) {
                            nodes {
                                id
                                body
                                createdAt
                                author {
                                login
                                }
                            }
                        }
                    }
                }
            }
        }
        """

    @override
    async def get_issues(self, end_date: datetime) -> list[Issue]:
        client = self._create_gql_client()

        issues_query = self._get_issue_query()
        issues_list: list[Issue] = []
        cursor = None
        in_time_frame = True

        async with client as session:
            while in_time_frame:
                variable_values: dict[str, Any] = {
                    "owner": self.repo_owner,
                    "repo": self.repo_name,
                    "end_date": end_date.isoformat(),
                    "cursor": cursor,
                }
                request = GraphQLRequest(issues_query, variable_values=variable_values)

                try:
                    result = await session.execute(request)
                except Exception as e:
                    raise IssueTrackerError(f"Failed to connect to GitHub: {e}") from e

                repo_data = result.get("repository")
                if not repo_data:
                    raise IssueTrackerError(
                        f"Repository {self.repo_owner}/{self.repo_name} not found or inaccessible."
                    )

                issues_obj = repo_data.get("issues", {})
                issues = issues_obj.get("nodes", [])
                page_info = issues_obj.get("pageInfo", {})

                if not issues:
                    break

                for issue in issues:
                    issue_created_at = self._parse_date_string(
                        issue["createdAt"]
                    )  # assume this is mandatory
                    issue_closed_at = (
                        self._parse_date_string(issue["closedAt"])
                        if issue.get("closedAt")
                        else None
                    )

                    if issue_created_at < end_date:
                        in_time_frame = False
                        break

                    issue_author_data = issue.get("author")
                    issue_author = (
                        issue_author_data.get("login")
                        if issue_author_data
                        else "unknown author"
                    )

                    comment_list: list[Comment] = []
                    comments = issue.get("comments", {}).get("nodes", [])

                    for comment in comments:
                        comment_author_data = comment.get("author")
                        comment_author = (
                            comment_author_data.get("login")
                            if comment_author_data
                            else "unknown author"
                        )
                        comment_created_at = self._parse_date_string(
                            comment["createdAt"]
                        )

                        comment_list.append(
                            Comment(
                                id=comment["id"].split("/")[-1],
                                author=comment_author,
                                created_at=comment_created_at,
                                body=comment.get("body") or "",
                            )
                        )

                    issues_list.append(
                        Issue(
                            id=issue["id"],
                            title=issue["title"],
                            description=issue.get("body"),
                            state=issue["state"].lower(),
                            author=issue_author,
                            created_at=issue_created_at,
                            closed_at=issue_closed_at,
                            comments=comment_list,
                        )
                    )

                if not page_info.get("hasNextPage", False):
                    break

                cursor = page_info.get("endCursor")

        return issues_list
