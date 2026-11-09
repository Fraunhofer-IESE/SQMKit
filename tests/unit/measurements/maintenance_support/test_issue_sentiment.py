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

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import HttpUrl

from sqmkit.clients.issue_tracker import Comment, Issue
from sqmkit.clients.model_client import ModelClient
from sqmkit.measurements import EvaluationStatus
from sqmkit.measurements.maintenance_support.issue_sentiment import IssueSentiment


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_issue_sentiment(
    make_model_client: Callable[..., ModelClient],
) -> None:
    git_url = HttpUrl(
        "https://github.com/smart-village-solutions/smart-village-app-app"
    )

    comment_bodies = [
        # rude comments - 5
        "This is terrible, I hate how this works.",
        "This is unacceptable!",
        "Why is this broken again?",
        "The issue persists and it's frustrating.",
        "Poor implementation.",
        # neutral or positive comments - 10
        "This could use some improvement.",
        "Great job on this!",
        "Looks good to me.",
        "Thanks for fixing this.",
        "Can we improve the documentation?",
        "All good here.",
        "Works as expected.",
        "Much appreciated!",
        "Still seeing a bug here.",
        "Awesome update!",
    ]

    issues: list[Issue] = []
    for d, body in enumerate(comment_bodies):
        created_at = datetime.now(UTC) - timedelta(days=d)
        comments: list[Comment] = []
        c = Comment(
            id=f"comment_{d}",
            author=f"dummy_{d}",
            created_at=created_at,
            body=body,
        )
        comments.append(c)
        issues.append(
            Issue(
                id="issue",
                title="Issue title",
                description="Some issue description",
                state="open",
                author="dummy",
                created_at=created_at,
                closed_at=None,
                comments=comments,
            )
        )

    old_issue = Issue(
        id="issue_old",
        title="Old Issue",
        description="An old issue that should not be included",
        state="open",
        author="dummy",
        created_at=datetime.now(UTC) - timedelta(days=200),
        closed_at=None,
        comments=[
            Comment(
                id="c_old_1",
                author="user_1",
                created_at=datetime.now(UTC) - timedelta(days=199),
                body="This is very outdated and wrong.",
            )
        ],
    )

    closed_issue = Issue(
        id="issue_closed",
        title="Closed Issue",
        description="A closed issue that should not be included",
        state="closed",
        author="dummy",
        created_at=datetime.now(UTC) - timedelta(days=10),
        closed_at=datetime.now(UTC) - timedelta(days=1),
        comments=[
            Comment(
                id="c_old_1",
                author="user_1",
                created_at=datetime.now(UTC) - timedelta(days=199),
                body="This is very outdated and wrong.",
            )
        ],
    )

    issues.append(old_issue)
    issues.append(closed_issue)

    mock_tracker = AsyncMock()
    mock_tracker.get_issues.return_value = issues

    with patch(
        "sqmkit.measurements.maintenance_support.issue_sentiment.IssueTrackerFactory.create_issue_tracker",
        return_value=mock_tracker,
    ):
        sentiment = IssueSentiment(
            issue_tracker_url=git_url,
            model_client=make_model_client(kind="sentiment"),
        )  # run the model sentiment analysis
        result = await sentiment.execute()
        assert result.status is EvaluationStatus.EVALUATED
        assert 0.0 <= result.score <= 1.0


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_issue_sentiment_only_rude_comments(
    make_model_client: Callable[..., ModelClient],
) -> None:
    git_url = HttpUrl(
        "https://github.com/smart-village-solutions/smart-village-app-app"
    )

    rude_comments = [
        "This is terrible.",
        "Absolutely unacceptable.",
        "I hate this implementation.",
        "This is broken again.",
        "Very frustrating experience.",
        "This feature is completely useless.",
        "Nothing works as documented.",
        "This keeps failing and no one fixes it. ARGH",
        "The quality of this release is disappointing. TRASH",
        "I'm tired of dealing with these constant bugs. PLEASE FIX",
    ]

    issues: list[Issue] = []
    for d, body in enumerate(rude_comments):
        created_at = datetime.now(UTC) - timedelta(days=d)
        issues.append(
            Issue(
                id=f"issue_{d}",
                title="Issue title",
                description="Some issue description",
                state="open",
                author="dummy",
                created_at=created_at,
                closed_at=None,
                comments=[
                    Comment(
                        id=f"comment_{d}",
                        author=f"user_{d}",
                        created_at=created_at,
                        body=body,
                    )
                ],
            )
        )

    mock_tracker = AsyncMock()
    mock_tracker.get_issues.return_value = issues

    with patch(
        "sqmkit.measurements.maintenance_support.issue_sentiment.IssueTrackerFactory.create_issue_tracker",
        return_value=mock_tracker,
    ):
        sentiment = IssueSentiment(
            issue_tracker_url=git_url,
            model_client=make_model_client(kind="sentiment", sentiment="RUDE"),
        )
        result = await sentiment.execute()

        assert result.status is EvaluationStatus.EVALUATED
        assert result.score <= 0.5


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_issue_sentiment_only_outdated_comments(
    model_client: ModelClient,
) -> None:
    git_url = HttpUrl(
        "https://github.com/smart-village-solutions/smart-village-app-app"
    )

    old_issue = Issue(
        id="old_issue",
        title="Old Issue",
        description="Very old issue",
        state="open",
        author="dummy",
        created_at=datetime.now(UTC) - timedelta(days=250),
        closed_at=None,
        comments=[
            Comment(
                id="old_comment",
                author="user_1",
                created_at=datetime.now(UTC) - timedelta(days=249),
                body="This is terrible and broken.",
            )
        ],
    )

    mock_tracker = AsyncMock()
    mock_tracker.get_issues.return_value = [old_issue]

    with patch(
        "sqmkit.measurements.maintenance_support.issue_sentiment.IssueTrackerFactory.create_issue_tracker",
        return_value=mock_tracker,
    ):
        sentiment = IssueSentiment(
            issue_tracker_url=git_url,
            model_client=model_client,
        )
        result = await sentiment.execute()

        assert result.status is EvaluationStatus.SKIPPED
        assert result.score == 0.0


def _issue_with_comments(comments: list[Comment]) -> Issue:
    now = datetime.now(UTC)
    return Issue(
        id="issue",
        title="Issue",
        description="Description",
        state="open",
        author="dummy",
        created_at=now,
        closed_at=None,
        comments=comments,
    )


def test_unique_comment_bodies_deduplicates_by_comment_id() -> None:
    now = datetime.now(UTC)
    duplicate = Comment(
        id="same-id", author="user", created_at=now, body="Duplicated comment."
    )
    other = Comment(id="other-id", author="user", created_at=now, body="Other comment.")

    issues = [
        _issue_with_comments([duplicate, other]),
        _issue_with_comments([duplicate]),
    ]

    assert IssueSentiment._unique_comment_bodies(issues) == [
        "Other comment.",
        "Duplicated comment.",
    ]


def test_unique_comment_bodies_falls_back_to_identity_without_ids() -> None:
    now = datetime.now(UTC)
    first = Comment(id="", author="user", created_at=now, body="Same comment.")
    second = Comment(id="", author="user", created_at=now, body="Same comment.")
    third = Comment(id="", author="other", created_at=now, body="Different author.")

    issues = [_issue_with_comments([first, second, third])]

    assert IssueSentiment._unique_comment_bodies(issues) == [
        "Different author.",
        "Same comment.",
    ]
