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

"""Facade for evaluating repositories with one or more configured models. The facade owns the configured models and delegates the task-specific work (prompting, chunking, output schemas and aggregation) to :mod:`clients.model_client.likert` and :mod:`clients.model_client.sentiment`."""

from collections.abc import Sequence

from sqmkit.clients.model_client.likert import (
    evaluate_context_likert as _evaluate_context_likert,
)
from sqmkit.clients.model_client.model_evaluation import (
    AverageLikertEvaluation,
    LikertCriterion,
    SentimentEvaluation,
)
from sqmkit.clients.model_client.model_factory import ModelHandle
from sqmkit.clients.model_client.sentiment import (
    evaluate_comment_sentiment as _evaluate_comment_sentiment,
)


class ModelClient:
    def __init__(self, models: list[ModelHandle]) -> None:
        self.models = models

    def has_models(self) -> bool:
        return bool(self.models)

    async def evaluate_context_likert(
        self,
        context: str,
        criteria: Sequence[LikertCriterion],
    ) -> dict[str, AverageLikertEvaluation]:
        """Score ``context`` against each criterion, combining all models."""
        return await _evaluate_context_likert(self.models, context, criteria)

    async def evaluate_comment_sentiment(
        self, comments: list[str]
    ) -> list[SentimentEvaluation]:
        """Classify each comment, combining the votes of all configured models."""
        return await _evaluate_comment_sentiment(self.models, comments)
