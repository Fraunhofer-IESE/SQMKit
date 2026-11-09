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


class GitlabIssueTracker(IssueTracker):
    def __init__(self, url: HttpUrl):
        super().__init__(url)

        parsed_url = urlparse(str(url))
        self.token = settings.gitlab_api_key

        # TODO: how to deal with multi-repo projects like https://gitlab.opencode.de/diplanung with issues at the top level
        url_path = parsed_url.path
        if "/-/" in url_path:
            url_path = url_path[: url_path.find("/-/")]
        url_path = url_path.rstrip("/").removesuffix(".git")
        path_parts = url_path.strip("/").split("/")

        if len(path_parts) >= 2:
            self.project_path = "/".join(path_parts)
        else:
            raise IssueTrackerError(
                f"Invalid project URL: {url}"
            )  # e.g., 'namespace/project_name'

    def _parse_date_string(self, date: str) -> datetime:
        return datetime.fromisoformat(date)

    def _create_gql_client(self) -> Client:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else None
        transport = AIOHTTPTransport(
            url=f"https://{self.url.host}/api/graphql", headers=headers, ssl=True
        )
        return Client(transport=transport, execute_timeout=30)

    def _get_issue_query(self) -> str:
        return """
        query GetIssuesSinceDate($project_path: ID!, $end_date: Time!, $cursor: String) {
            project(fullPath: $project_path) {
                issues(
                    first: 100,
                    createdAfter: $end_date,
                    sort: CREATED_DESC,
                    after: $cursor
                ) {
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                    nodes {
                        id
                        title
                        description
                        state
                        createdAt
                        closedAt
                        author {
                            username
                        }
                        notes(first: 100) {
                            nodes {
                                id
                                body
                                system
                                createdAt
                                author {
                                    username
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
                    "project_path": self.project_path,
                    "end_date": end_date.isoformat(),
                    "cursor": cursor,
                }
                request = GraphQLRequest(issues_query, variable_values=variable_values)

                try:
                    result = await session.execute(request)
                except Exception as e:
                    raise IssueTrackerError(f"Failed to connect to GitLab: {e}") from e

                project_data = result.get("project")
                if not project_data:
                    raise IssueTrackerError(
                        f"Project {self.project_path} not found or inaccessible."
                    )

                issues_obj = project_data.get("issues", {})
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
                        issue_author_data.get("username")
                        if issue_author_data
                        else "unknown author"
                    )

                    comment_list: list[Comment] = []
                    comments = issue.get("notes", {}).get("nodes", [])

                    for comment in comments:
                        # Skip GitLab system notes ("marked as closed", ...) so the data is comparable to GitHub issue comments.
                        if comment.get("system", False):
                            continue
                        comment_author_data = comment.get("author")
                        comment_author = (
                            comment_author_data.get("username")
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
                                body=comment["body"],
                            )
                        )

                    issues_list.append(
                        Issue(
                            id=issue["id"].split("/")[-1],
                            title=issue["title"],
                            description=issue.get("description"),
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
