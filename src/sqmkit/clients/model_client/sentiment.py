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

"""Comment-sentiment evaluation across one or more models."""

from collections import Counter, defaultdict, deque
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, Field, create_model

from sqmkit.clients.model_client.aggregation import majority
from sqmkit.clients.model_client.chunking import (
    check_context_overflow,
    comment_char_budget,
    truncate_middle,
)
from sqmkit.clients.model_client.model_evaluation import (
    IdentifiedSentimentEvaluation,
    SentimentEnum,
    SentimentEvaluation,
)
from sqmkit.clients.model_client.model_factory import ModelHandle
from sqmkit.exceptions import MeasurementError


def get_sentiment_prompt(context: str) -> str:
    return f"""Please assign the following GitHub issue sentence as either POSITIVE_OR_NEUTRAL or RUDE.

Only classify a sentence as RUDE if it contains clear hostility, insults, mockery, or aggressive language directed at a person or group.
Constructive criticism, neutral statements, bug reports, or frustrated but non-insulting sentences should be classified as POSITIVE_OR_NEUTRAL.

Here are some examples:

Sentence: "Thanks for the quick fix! I tested it locally and it works great."
Classification: POSITIVE_OR_NEUTRAL

Sentence: "I'm still seeing the same error on version 2.1. Could you clarify if this was fully addressed?"
Classification: POSITIVE_OR_NEUTRAL

Sentence: "This implementation doesn't handle edge cases around null values. We might want to add additional validation here."
Classification: POSITIVE_OR_NEUTRAL

Sentence: "The documentation is a bit confusing in the authentication section. Maybe adding an example request would help."
Classification: POSITIVE_OR_NEUTRAL

Sentence: "This is completely broken. Did you even test this before merging?"
Classification: RUDE

Sentence: "Why would you design it this way? This makes no sense and just creates more problems."
Classification: RUDE

Now classify the following comments. Each comment is formatted as
`Comment c0: <text>`, `Comment c1: <text>`, and so on. Return one result per
comment with the exact `comment_id` (the `cN` part), the original `sentence`,
and its `sentiment`.

{context}"""


def _sentiment_decision_type(comments: tuple[str, ...]) -> type[BaseModel]:
    """Build a per-comment sentiment output type for decision models."""
    fields: dict[str, Any] = {}
    for index, comment in enumerate(comments):
        fields[f"c{index}"] = (
            SentimentEnum,
            Field(
                description=(f"Classify the sentiment of comment c{index}: {comment}")
            ),
        )
    return create_model(
        "SentimentDecision",
        __doc__="Classify the sentiment of every comment in the state.",
        **fields,
    )


def _format_comments(comments: Sequence[str]) -> str:
    """Render comments with the ids the model must echo back."""
    return "\n".join(
        f"Comment c{index}: {comment}" for index, comment in enumerate(comments)
    )


def _align_text_outputs(
    batch: list[str],
    outputs: Sequence[IdentifiedSentimentEvaluation],
    model_id: str,
) -> list[SentimentEnum]:
    """Match a text model's results to the comments that were sent. The prompt gives every comment a stable id (``c0``, ``c1``, ...), so normal results are aligned by id regardless of their order. Models that ignore the ids fall back to echoed sentence text and finally to positional order. A count mismatch is always an error: silently dropping votes would bias the eventual majority."""
    if len(outputs) != len(batch):
        raise MeasurementError(
            f"Model {model_id} returned {len(outputs)} sentiment results for "
            f"{len(batch)} comments."
        )

    expected_ids = [f"c{index}" for index in range(len(batch))]
    output_ids = [output.comment_id for output in outputs]

    if any(output_ids):
        if not all(output_ids):
            raise MeasurementError(
                f"Model {model_id} returned some sentiment results without a "
                "comment id."
            )
        if len(set(output_ids)) != len(output_ids) or set(output_ids) != set(
            expected_ids
        ):
            raise MeasurementError(
                f"Model {model_id} returned unknown or duplicate comment ids."
            )
        by_id = {output.comment_id: output.sentiment for output in outputs}
        return [by_id[comment_id] for comment_id in expected_ids]

    aligned: list[SentimentEnum | None] = [None] * len(batch)
    echoed = [output.sentence for output in outputs]
    matches_input = bool(all(echoed)) and Counter(echoed) == Counter(batch)

    if matches_input:
        positions: dict[str, deque[int]] = defaultdict(deque)
        for index, comment in enumerate(batch):
            positions[comment].append(index)
        for output in outputs:
            if not positions[output.sentence]:
                raise MeasurementError(
                    f"Model {model_id} returned a sentiment result for an "
                    "unknown comment."
                )
            aligned[positions[output.sentence].popleft()] = output.sentiment
    else:
        aligned = [output.sentiment for output in outputs]

    if any(sentiment is None for sentiment in aligned):
        raise MeasurementError(
            f"Model {model_id} returned sentiment results that cannot be "
            "matched to the comments."
        )
    return [sentiment for sentiment in aligned if sentiment is not None]


def _batch_comments(comments: list[str]) -> list[list[str]]:
    """Group comments into batches that fit the configured context size."""
    batches: list[list[str]] = []
    current: list[str] = []

    for comment in comments:
        candidate = [*current, comment]
        candidate_prompt = get_sentiment_prompt(_format_comments(candidate))
        if current and check_context_overflow(candidate_prompt):
            batches.append(current)
            current = [comment]
        else:
            current = candidate

    if current:
        batches.append(current)

    return batches


async def evaluate_comment_sentiment(
    models: Sequence[ModelHandle], comments: list[str]
) -> list[SentimentEvaluation]:
    """Classify each comment, combining the votes of all configured models."""
    if not comments or not models:
        return []

    budget = comment_char_budget()
    cropped_comments = [truncate_middle(comment, budget) for comment in comments]

    sentiments: list[SentimentEvaluation] = []
    for batch in _batch_comments(cropped_comments):
        batch_prompt = get_sentiment_prompt(_format_comments(batch))
        # one vote per model per comment in the batch
        votes: list[list[SentimentEnum]] = [[] for _ in batch]

        for handle in models:
            if handle.supports_text:
                result = await handle.agent.run(
                    batch_prompt, output_type=list[IdentifiedSentimentEvaluation]
                )
                aligned = _align_text_outputs(batch, result.output, handle.id)
                for index, sentiment in enumerate(aligned):
                    votes[index].append(sentiment)
            else:
                decision_type = _sentiment_decision_type(tuple(batch))
                decision_result = await handle.agent.run(
                    batch_prompt, output_type=decision_type
                )
                for index in range(len(batch)):
                    votes[index].append(getattr(decision_result.output, f"c{index}"))

        for index, comment in enumerate(batch):
            comment_votes = votes[index]
            if not comment_votes:
                raise MeasurementError(
                    f"No sentiment vote was produced for comment {index + 1}."
                )
            sentiments.append(
                SentimentEvaluation(
                    sentence=comment,
                    sentiment=majority(comment_votes),
                )
            )

    return sentiments
