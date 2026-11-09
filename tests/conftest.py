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

import pathlib
from collections.abc import AsyncGenerator
from typing import Literal

import pytest
from anyio import Path
from git import Repo
from pydantic_ai import Agent

from sqmkit.clients.model_client import ModelClient
from sqmkit.clients.model_client.model_config import Provider
from sqmkit.clients.model_client.model_factory import ModelHandle
from tests.support import (
    FakeGitClient,
    GitClientFactory,
    ModelClientFactory,
    RepoDir,
    likert_model,
    sentiment_model,
)

# conftest.py declares global fixtures - https://docs.pytest.org/en/stable/reference/fixtures.html#conftest-py-sharing-fixtures-across-multiple-files


@pytest.fixture
def make_model_client() -> ModelClientFactory:
    """Build a deterministic :class:`ModelClient` backed by fake models."""

    def factory(
        *,
        kind: Literal["likert", "sentiment"] = "likert",
        score: int = 3,
        scores: list[int] | None = None,
        reason: str = "stub reason",
        sentiment: str = "POSITIVE_OR_NEUTRAL",
        sentiments: list[str] | None = None,
        models: int = 1,
        supports_text: bool = True,
    ) -> ModelClient:
        per_model_scores = scores if scores is not None else [score] * models
        per_model_sentiments = (
            sentiments
            if sentiments is not None
            else [sentiment] * len(per_model_scores)
        )
        handles = [
            ModelHandle(
                id=f"model-{index + 1}",
                provider=Provider.OPENAI,
                agent=Agent(
                    likert_model(score=model_score, reason=reason)
                    if kind == "likert"
                    else sentiment_model(sentiment=model_sentiment)
                ),
                supports_text=supports_text,
            )
            for index, (model_score, model_sentiment) in enumerate(
                zip(per_model_scores, per_model_sentiments)
            )
        ]
        return ModelClient(handles)

    return factory


@pytest.fixture
def model_client(make_model_client: ModelClientFactory) -> ModelClient:
    return make_model_client()


@pytest.fixture
def make_git_client() -> GitClientFactory:
    """Build a minimal ``GitClient`` stand-in exposing visible files."""

    def factory(
        repo_path: Path | None = None,
        *,
        visible_files: list[str] | None = None,
        is_git_repo: bool = True,
    ) -> FakeGitClient:
        return FakeGitClient(
            repo_path=repo_path if repo_path is not None else Path("/tmp/repo"),
            visible_files=visible_files or [],
            is_git_repo=is_git_repo,
        )

    return factory


@pytest.fixture
async def repo_dir(tmp_path: pathlib.Path) -> AsyncGenerator[RepoDir, None]:
    """Yield an empty temporary git repository directory."""
    Repo.init(str(tmp_path))
    yield RepoDir(tmp_path)
