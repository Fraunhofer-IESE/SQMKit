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

from enum import StrEnum
from statistics import mean

from pydantic import AliasChoices, BaseModel, Field


class SentimentEnum(StrEnum):
    POSITIVE_OR_NEUTRAL = "POSITIVE_OR_NEUTRAL"
    RUDE = "RUDE"


class AverageLikertEvaluation(BaseModel):
    likert_evaluation: float = Field(description="The average likert score from 1 to 5")
    reason: str = Field(description="Explanation for the assigned evaluation score")


class LikertCriterion(BaseModel):
    """One evaluation criterion, defined by the measurement that owns it. ``name`` becomes the output field the score is read from; ``description`` is the question sent to the model (as the field description, which is how decision models receive their questions)."""

    name: str = Field(description="Identifier of the criterion")
    description: str = Field(description="The question the model answers")


class SentimentEvaluation(BaseModel):
    sentence: str = Field(
        description="The text excerpt being analyzed for sentiment",
        validation_alias=AliasChoices("sentence", "name", "comment"),
    )
    sentiment: SentimentEnum = Field(
        description="The detected sentiment: POSITIVE_OR_NEUTRAL or RUDE"
    )


class IdentifiedSentimentEvaluation(SentimentEvaluation):
    """Sentiment result for a comment identified by its prompt id."""

    comment_id: str = Field(
        description="Identifier of the comment as given in the prompt, e.g. c0",
        validation_alias=AliasChoices("comment_id", "id"),
    )


LIKERT_MAX = 5


def get_normalized_likert_score(
    evaluations: dict[str, AverageLikertEvaluation],
) -> float:
    """Normalize the mean Likert score (1-5) to the 0-1 range. ``1`` (worst) maps to ``0.0`` and ``LIKERT_MAX`` (best) maps to ``1.0``."""
    scores = [evaluation.likert_evaluation for evaluation in evaluations.values()]
    return round((mean(scores) - 1) / (LIKERT_MAX - 1), 2) if scores else 0.0
