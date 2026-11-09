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

"""Likert-criterion evaluation across one or more models."""

from collections.abc import Sequence
from statistics import mean
from typing import Any, Literal

from pydantic import BaseModel, Field, create_model

from sqmkit.clients.model_client.chunking import check_context_overflow, split_context
from sqmkit.clients.model_client.model_evaluation import (
    AverageLikertEvaluation,
    LikertCriterion,
)
from sqmkit.clients.model_client.model_factory import ModelHandle

# Reason attached to scores produced by decision models, which cannot emit free text.
_DECISION_REASON = "Decision model output"

_LikertLevel = Literal[1, 2, 3, 4, 5]


def get_likert_prompt(context: str, questions: str) -> str:
    return f"""You are a reviewer for open source software. Evaluate the following based on the listed evaluation criteria.

CONTENT TO EVALUATE:
```
{context}
```

EVALUATION CRITERIA:
{questions}

For EACH criterion above, provide:
- The question being evaluated
- Your evaluation score
    - Use a Likert scale from 1 to 5:
        1 = Strongly Disagree / Very Poor
        2 = Disagree / Poor
        3 = Neutral / Acceptable
        4 = Agree / Good
        5 = Strongly Agree / Excellent
- A detailed reason explaining your score, with specific references to the content. The reason must be in English.

Be thorough and objective in your evaluation. Cite specific sections or missing elements from the content to justify your scores.
    """


def _likert_type(
    criteria: Sequence[LikertCriterion], *, with_reason: bool
) -> type[BaseModel]:
    """Build the wire output type for a set of criteria. One ``Literal[1..5]`` field per criterion (its description is the question, which is how decision models receive it). Text models additionally get a ``<name>_reason`` field, since decision models cannot emit free text."""
    fields: dict[str, Any] = {}
    for criterion in criteria:
        fields[criterion.name] = (
            _LikertLevel,
            Field(description=criterion.description),
        )
        if with_reason:
            fields[f"{criterion.name}_reason"] = (
                str,
                Field(description=f"Reason for: {criterion.description}"),
            )
    return create_model("LikertEvaluation", **fields)


async def evaluate_context_likert(
    models: Sequence[ModelHandle],
    context: str,
    criteria: Sequence[LikertCriterion],
) -> dict[str, AverageLikertEvaluation]:
    """Score ``context`` against each criterion, combining all models."""
    if not models or not criteria:
        return {}

    questions_str = "\n".join(
        [f"{i + 1}. {c.description}" for i, c in enumerate(criteria)]
    )
    prompt = get_likert_prompt(context, questions_str)

    # split context if necessary
    prompts = (
        [
            get_likert_prompt(chunk, questions_str)
            for chunk in split_context(context, get_likert_prompt("", questions_str))
        ]
        if check_context_overflow(prompt)
        else [prompt]
    )

    field_names = [criterion.name for criterion in criteria]
    best_evaluations: dict[str, AverageLikertEvaluation] = {}

    # The wire output type only depends on the model, so build it once.
    model_outputs = [
        (handle, _likert_type(criteria, with_reason=handle.supports_text))
        for handle in models
    ]

    for chunk_prompt in prompts:
        per_field: dict[str, list[tuple[str, int, str | None]]] = {
            name: [] for name in field_names
        }

        for handle, output_type in model_outputs:
            result = await handle.agent.run(chunk_prompt, output_type=output_type)
            for name in field_names:
                score = getattr(result.output, name)
                reason = (
                    getattr(result.output, f"{name}_reason")
                    if handle.supports_text
                    else None
                )
                per_field[name].append((handle.id, score, reason))

        for name in field_names:
            entries = per_field[name]
            scores = [score for _, score, _ in entries]
            reasons = [
                f"[{model_id}] {reason}" for model_id, _, reason in entries if reason
            ]
            chunk_evaluation = AverageLikertEvaluation(
                likert_evaluation=round(mean(scores), 2),
                reason="\n---\n".join(reasons) if reasons else _DECISION_REASON,
            )

            existing = best_evaluations.get(name)
            if (
                existing is None
                or chunk_evaluation.likert_evaluation > existing.likert_evaluation
            ):
                best_evaluations[name] = chunk_evaluation

    return best_evaluations
