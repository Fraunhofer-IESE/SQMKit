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

import os
from collections.abc import Callable

import pytest

from sqmkit.clients.model_client import ModelClient
from sqmkit.clients.model_client.aggregation import majority
from sqmkit.clients.model_client.chunking import truncate_middle
from sqmkit.clients.model_client.likert import _likert_type
from sqmkit.clients.model_client.model_config import Provider
from sqmkit.clients.model_client.model_evaluation import (
    AverageLikertEvaluation,
    IdentifiedSentimentEvaluation,
    LikertCriterion,
    SentimentEnum,
    get_normalized_likert_score,
)
from sqmkit.clients.model_client.sentiment import (
    _align_text_outputs,
    _format_comments,
    _sentiment_decision_type,
)
from sqmkit.config import settings
from sqmkit.exceptions import MeasurementError

_CRITERIA: list[LikertCriterion] = [
    LikertCriterion(name="a", description="Question A"),
    LikertCriterion(name="b", description="Question B"),
    LikertCriterion(name="c", description="Question C"),
]


@pytest.mark.parametrize(
    ("likert", "expected"),
    [(1.0, 0.0), (2.0, 0.25), (3.0, 0.5), (4.0, 0.75), (5.0, 1.0)],
)
def test_normalized_likert_score_maps_worst_to_zero(
    likert: float, expected: float
) -> None:
    evaluations = {
        "criterion": AverageLikertEvaluation(likert_evaluation=likert, reason="reason")
    }

    assert get_normalized_likert_score(evaluations) == expected


def test_normalized_likert_score_is_zero_without_evaluations() -> None:
    assert get_normalized_likert_score({}) == 0.0


def test_majority_ties_resolve_to_first_seen() -> None:
    assert majority(["a", "b", "a", "b"]) == "a"
    assert majority([SentimentEnum.RUDE, SentimentEnum.POSITIVE_OR_NEUTRAL]) == (
        SentimentEnum.RUDE
    )


def test_get_model_configs(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("MODEL_"):
            monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("MODEL_QWEN_PROVIDER", "openai")
    monkeypatch.setenv("MODEL_QWEN_MODEL_NAME", "Qwen/Qwen3.6")
    monkeypatch.setenv("MODEL_QWEN_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("MODEL_QWEN_API_KEY", "sk-test")
    monkeypatch.setenv("MODEL_JEV_PROVIDER", "systemone")
    monkeypatch.setenv("MODEL_JEV_MODEL_NAME", "jev-latest")
    monkeypatch.setenv("MODEL_JEV_API_KEY", "jev-test")
    # incomplete, credential-less and invalid groups must be ignored
    monkeypatch.setenv("MODEL_BROKEN_MODEL_NAME", "broken")
    monkeypatch.setenv("MODEL_NO_KEY_PROVIDER", "openai")
    monkeypatch.setenv("MODEL_NO_KEY_MODEL_NAME", "no-key")
    monkeypatch.setenv("MODEL_BAD_PROVIDER", "not-a-provider")
    monkeypatch.setenv("MODEL_BAD_MODEL_NAME", "bad")
    monkeypatch.setenv("MODEL_BAD_API_KEY", "bad-test")

    configs = settings.get_model_configs()

    assert [config.id for config in configs] == ["JEV", "QWEN"]
    qwen = next(config for config in configs if config.id == "QWEN")
    assert qwen.provider is Provider.OPENAI
    assert qwen.model_name == "Qwen/Qwen3.6"
    assert qwen.base_url == "http://localhost:8000/v1"
    assert qwen.api_key is not None
    jev = next(config for config in configs if config.id == "JEV")
    assert jev.provider is Provider.SYSTEMONE
    assert jev.base_url is None
    assert jev.api_key is not None


def test_likert_type_is_flat_with_criterion_descriptions() -> None:
    decision_type = _likert_type(_CRITERIA, with_reason=False)

    assert list(decision_type.model_fields) == ["a", "b", "c"]
    assert decision_type.model_fields["a"].description == "Question A"
    assert "a_reason" not in decision_type.model_fields

    instance = decision_type(a=4, b=2, c=5)
    assert instance.a == 4  # type: ignore[attr-defined]


def test_likert_type_adds_reason_fields_for_text_models() -> None:
    text_type = _likert_type(_CRITERIA, with_reason=True)

    assert list(text_type.model_fields) == [
        "a",
        "a_reason",
        "b",
        "b_reason",
        "c",
        "c_reason",
    ]
    assert text_type.model_fields["a_reason"].description == "Reason for: Question A"


def test_sentiment_decision_type_has_one_field_per_comment() -> None:
    decision_type = _sentiment_decision_type(("first", "second"))

    assert list(decision_type.model_fields) == ["c0", "c1"]
    instance = decision_type(
        c0=SentimentEnum.RUDE, c1=SentimentEnum.POSITIVE_OR_NEUTRAL
    )
    assert instance.c0 is SentimentEnum.RUDE  # type: ignore[attr-defined]


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_no_models_returns_empty_results(
    make_model_client: Callable[..., ModelClient],
) -> None:
    client = make_model_client(models=0)

    assert client.has_models() is False
    assert await client.evaluate_context_likert("context", _CRITERIA) == {}
    assert await client.evaluate_comment_sentiment(["a comment"]) == []


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_likert_aggregates_across_models(
    make_model_client: Callable[..., ModelClient],
) -> None:
    client = make_model_client(scores=[2, 4])

    evaluations = await client.evaluate_context_likert("context", _CRITERIA)

    assert set(evaluations) == {"a", "b", "c"}
    assert all(
        evaluation.likert_evaluation == 3.0 for evaluation in evaluations.values()
    )
    assert all(
        "stub reason" in evaluation.reason for evaluation in evaluations.values()
    )
    assert all(
        "[model-1] stub reason" in evaluation.reason
        and "[model-2] stub reason" in evaluation.reason
        for evaluation in evaluations.values()
    )


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_likert_reason_is_attributed_to_model(
    make_model_client: Callable[..., ModelClient],
) -> None:
    client = make_model_client(reason="stub reason")

    evaluations = await client.evaluate_context_likert("context", _CRITERIA)

    assert all(
        evaluation.reason.startswith("[model-1] stub reason")
        for evaluation in evaluations.values()
    )


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_decision_model_gets_static_reason(
    make_model_client: Callable[..., ModelClient],
) -> None:
    client = make_model_client(score=2, supports_text=False)

    evaluations = await client.evaluate_context_likert("context", _CRITERIA)

    assert all(
        evaluation.likert_evaluation == 2.0 for evaluation in evaluations.values()
    )
    assert all(
        evaluation.reason == "Decision model output"
        for evaluation in evaluations.values()
    )


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_sentiment_is_majority_vote_across_models(
    make_model_client: Callable[..., ModelClient],
) -> None:
    client = make_model_client(
        kind="sentiment",
        sentiments=["RUDE", "RUDE", "POSITIVE_OR_NEUTRAL"],
    )

    results = await client.evaluate_comment_sentiment(["a rude comment"])

    assert len(results) == 1
    assert results[0].sentiment is SentimentEnum.RUDE


def test_sentiment_alignment_uses_comment_ids() -> None:
    batch = ["first comment", "second comment"]
    outputs = [
        IdentifiedSentimentEvaluation(
            comment_id="c1",
            sentence="second comment",
            sentiment=SentimentEnum.RUDE,
        ),
        IdentifiedSentimentEvaluation(
            comment_id="c0",
            sentence="first comment",
            sentiment=SentimentEnum.POSITIVE_OR_NEUTRAL,
        ),
    ]

    aligned = _align_text_outputs(batch, outputs, "model-1")

    assert aligned == [SentimentEnum.POSITIVE_OR_NEUTRAL, SentimentEnum.RUDE]


def test_sentiment_alignment_falls_back_to_echoed_sentences() -> None:
    batch = ["first comment", "second comment"]
    outputs = [
        IdentifiedSentimentEvaluation(
            comment_id="",
            sentence="second comment",
            sentiment=SentimentEnum.RUDE,
        ),
        IdentifiedSentimentEvaluation(
            comment_id="",
            sentence="first comment",
            sentiment=SentimentEnum.POSITIVE_OR_NEUTRAL,
        ),
    ]

    aligned = _align_text_outputs(batch, outputs, "model-1")

    assert aligned == [SentimentEnum.POSITIVE_OR_NEUTRAL, SentimentEnum.RUDE]


def test_sentiment_alignment_falls_back_to_positional_order() -> None:
    batch = ["first comment", "second comment"]
    outputs = [
        IdentifiedSentimentEvaluation(
            comment_id="", sentence="", sentiment=SentimentEnum.RUDE
        ),
        IdentifiedSentimentEvaluation(
            comment_id="", sentence="", sentiment=SentimentEnum.POSITIVE_OR_NEUTRAL
        ),
    ]

    aligned = _align_text_outputs(batch, outputs, "model-1")

    assert aligned == [SentimentEnum.RUDE, SentimentEnum.POSITIVE_OR_NEUTRAL]


def test_sentiment_alignment_rejects_unknown_comment_ids() -> None:
    outputs = [
        IdentifiedSentimentEvaluation(
            comment_id="c0",
            sentence="first comment",
            sentiment=SentimentEnum.POSITIVE_OR_NEUTRAL,
        ),
        IdentifiedSentimentEvaluation(
            comment_id="c9",
            sentence="second comment",
            sentiment=SentimentEnum.RUDE,
        ),
    ]

    with pytest.raises(MeasurementError, match="unknown or duplicate comment ids"):
        _align_text_outputs(["first comment", "second comment"], outputs, "model-1")


def test_sentiment_alignment_rejects_partial_comment_ids() -> None:
    outputs = [
        IdentifiedSentimentEvaluation(
            comment_id="c0",
            sentence="first comment",
            sentiment=SentimentEnum.POSITIVE_OR_NEUTRAL,
        ),
        IdentifiedSentimentEvaluation(
            comment_id="",
            sentence="second comment",
            sentiment=SentimentEnum.RUDE,
        ),
    ]

    with pytest.raises(MeasurementError, match="without a comment id"):
        _align_text_outputs(["first comment", "second comment"], outputs, "model-1")


def test_sentiment_alignment_rejects_count_mismatch() -> None:
    outputs = [
        IdentifiedSentimentEvaluation(
            comment_id="c0",
            sentence="first comment",
            sentiment=SentimentEnum.POSITIVE_OR_NEUTRAL,
        )
    ]

    with pytest.raises(MeasurementError, match="1 sentiment results for 2 comments"):
        _align_text_outputs(["first comment", "second comment"], outputs, "model-1")


def test_sentiment_prompt_contains_comment_ids() -> None:
    assert _format_comments(["first", "second"]) == (
        "Comment c0: first\nComment c1: second"
    )


def test_truncate_middle_keeps_head_and_tail() -> None:
    text = "A" * 5000

    truncated = truncate_middle(text, 100)

    assert len(truncated) == 100
    assert "..." in truncated
    assert truncated.startswith("A" * 48)
    assert truncated.endswith("A" * 49)
    assert truncate_middle("short", 100) == "short"


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_comment_sentiment_truncates_long_comments(
    make_model_client: Callable[..., ModelClient],
) -> None:
    client = make_model_client(kind="sentiment")
    long_comment = "x" * 1_000_000

    results = await client.evaluate_comment_sentiment([long_comment])

    assert len(results) == 1
    assert len(results[0].sentence) < len(long_comment)
    assert "..." in results[0].sentence


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_context_too_small_raises(
    monkeypatch: pytest.MonkeyPatch,
    make_model_client: Callable[..., ModelClient],
) -> None:
    monkeypatch.setattr(settings, "model_context_size", 1)
    client = make_model_client()

    with pytest.raises(MeasurementError, match="MODEL_CONTEXT_SIZE"):
        await client.evaluate_context_likert("x" * 100_000, _CRITERIA)
