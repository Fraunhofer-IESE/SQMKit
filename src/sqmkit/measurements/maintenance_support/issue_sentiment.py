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
from random import Random
from typing import override

from pydantic import HttpUrl

from sqmkit.clients.issue_tracker import Issue, IssueStore
from sqmkit.clients.issue_tracker.issue_tracker_factory import IssueTrackerFactory
from sqmkit.clients.model_client import ModelClient
from sqmkit.clients.model_client.chunking import truncate_middle
from sqmkit.clients.model_client.model_evaluation import SentimentEnum
from sqmkit.exceptions import IssueTrackerError, MeasurementError
from sqmkit.measurements import (
    EvaluationStatus,
    MeasurementOutput,
    ModelMeasurement,
    Requirement,
)


class IssueSentiment(ModelMeasurement):
    requires = (Requirement.FORGE, Requirement.MODEL)

    # Keep the reason readable: cap each echoed rude comment.
    _MAX_REASON_COMMENT_CHARS = 500

    def __init__(
        self,
        issue_tracker_url: HttpUrl | None,
        model_client: ModelClient,
        issue_store: IssueStore | None = None,
    ):
        self.model_client = model_client
        self.issue_tracker_url = issue_tracker_url
        self.issue_store = issue_store

    @staticmethod
    def _unique_comment_bodies(issues: list[Issue]) -> list[str]:
        """Collect each comment once, in a stable order. Comment ids are unique per tracker; the fallback identity keeps trackers that do not expose ids from producing duplicate votes."""
        unique_comments: dict[str, str] = {}
        for issue in issues:
            for comment in issue.comments:
                if not comment.body:
                    continue
                key = comment.id or (
                    f"{comment.author or ''}|"
                    f"{comment.created_at.isoformat()}|"
                    f"{comment.body}"
                )
                unique_comments[key] = comment.body
        return [unique_comments[key] for key in sorted(unique_comments)]

    async def _get_issues(self, end_date: datetime):
        if self.issue_store is not None:
            return await self.issue_store.get_issues(end_date)
        if self.issue_tracker_url is None:
            return []
        tracker = IssueTrackerFactory.create_issue_tracker(self.issue_tracker_url)
        return await tracker.get_issues(end_date)

    @override
    async def evaluate(self) -> MeasurementOutput:
        if not self.issue_tracker_url:
            return MeasurementOutput(
                status=EvaluationStatus.SKIPPED,
                score=0.0,
                reason="No repository URL provided.",
            )

        six_months_ago = datetime.now(UTC) - timedelta(days=6 * 30)
        # TODO: include comments from the last 6 months on older issues too; the trackers currently restrict results by issue creation date.
        try:
            issues = await self._get_issues(six_months_ago)
        except IssueTrackerError as error:
            raise MeasurementError(str(error)) from error

        if not issues:
            return MeasurementOutput(
                status=EvaluationStatus.EVALUATED,
                score=1.0,
                reason="No issues found.",
            )

        all_comments = self._unique_comment_bodies(issues)

        if len(all_comments) < 10:
            return MeasurementOutput(
                status=EvaluationStatus.SKIPPED,
                score=0.0,
                reason="Fewer than 10 comments in the last 6 months, sentiment in comments cannot be evaluated.",
            )

        # Randomly sample up to 25 comments. A fixed seed keeps results reproducible across runs without touching the global RNG.
        selected_comments: list[str] = Random(42).sample(
            all_comments, min(25, len(all_comments))
        )

        sentiments = await self.model_client.evaluate_comment_sentiment(
            selected_comments
        )

        if not sentiments:
            return MeasurementOutput(
                status=EvaluationStatus.SKIPPED,
                score=0.0,
                reason="Comment sentiments could not be evaluated.",
            )

        rude_comments: list[str] = [
            sentence.sentence
            for sentence in sentiments
            if sentence.sentiment == SentimentEnum.RUDE
        ]

        rude_comments_count = len(rude_comments)

        rude_comment_ratio = rude_comments_count / len(sentiments)

        # step function to normalize ratio
        if rude_comment_ratio <= 0.05:
            score = 1.0
        elif rude_comment_ratio <= 0.1:
            score = 0.75
        elif rude_comment_ratio <= 0.2:
            score = 0.5
        elif rude_comment_ratio <= 0.3:
            score = 0.25
        else:
            score = 0.0

        # prepare reason; collapse identical texts so a duplicated body is only echoed once, while the score still counts each sampled comment.
        if rude_comments:
            unique_rude_comments = list(dict.fromkeys(rude_comments))
            rude_comments_formatted = "\n".join(
                f"- {truncate_middle(comment, IssueSentiment._MAX_REASON_COMMENT_CHARS)}"
                for comment in unique_rude_comments
            )
            reason = f"{rude_comments_count} rude or negative comments were found in the issues:\n{rude_comments_formatted}"
        else:
            reason = "No rude or negative comments were found in the issues."

        return MeasurementOutput(
            status=EvaluationStatus.EVALUATED,
            score=score,
            reason=reason,
        )
