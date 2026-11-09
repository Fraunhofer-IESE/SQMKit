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

"""Shared test helpers and types. Fixtures live in ``conftest.py``; this module only contains reusable types and builders so tests can import them without importing ``conftest``."""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from anyio import Path
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from sqmkit.clients.model_client import ModelClient

_LIKERT_LEVELS = [1, 2, 3, 4, 5]


class RepoDir(Path):
    """A temporary repository directory that tests populate with files. Subclasses ``anyio.Path`` so it can be handed directly to measurements, which expect a repository path."""

    async def add_file(self, filename: str, content: str) -> Path:
        """Write ``content`` to ``filename`` (relative to this repo), creating parents."""
        file_path = self / filename
        await file_path.parent.mkdir(parents=True, exist_ok=True)
        await file_path.write_text(content)
        return file_path


@dataclass
class FakeGitClient:
    """Minimal ``GitClient`` stand-in for tests that only read repository files."""

    repo_path: Path
    visible_files: list[str] = field(default_factory=list)
    is_git_repo: bool = True

    async def list_visible_files(self) -> list[str]:
        return self.visible_files


ModelClientFactory = Callable[..., ModelClient]
GitClientFactory = Callable[..., FakeGitClient]


def _resolve_ref(schema: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in schema:
        schema = defs[schema["$ref"].split("/")[-1]]
    return schema


def _function_model(
    fill: Callable[[list[Any], dict[str, Any], dict[str, Any]], Any],
) -> FunctionModel:
    """Build a fake model from a schema-to-answer function."""

    def respond(messages: list[Any], info: AgentInfo) -> ModelResponse:
        if not info.output_tools:
            return ModelResponse(parts=[])
        tool = info.output_tools[0]
        schema = tool.parameters_json_schema
        args = fill(messages, schema, schema.get("$defs", {}))
        return ModelResponse(parts=[ToolCallPart(tool_name=tool.name, args=args)])

    return FunctionModel(respond)


def likert_model(score: int, reason: str) -> FunctionModel:
    """Fake model that answers Likert criteria with ``score`` and ``reason``."""

    def fill(_messages: list[Any], schema: dict[str, Any], defs: dict[str, Any]) -> Any:
        schema = _resolve_ref(schema, defs)
        if "properties" in schema:
            return {
                name: fill(_messages, sub_schema, defs)
                for name, sub_schema in schema["properties"].items()
            }
        if schema.get("enum") == _LIKERT_LEVELS:
            return score
        if schema.get("type") == "integer":
            return score
        return reason

    return _function_model(fill)


def _message_text(messages: list[Any]) -> str:
    """Concatenate the textual prompt parts of Pydantic AI messages."""
    texts: list[str] = []
    for message in messages:
        for part in getattr(message, "parts", []):
            content = getattr(part, "content", None)
            if isinstance(content, str):
                texts.append(content)
    return "\n".join(texts)


def sentiment_model(sentiment: str) -> FunctionModel:
    """Fake model that classifies every comment with ``sentiment``."""

    def fill(messages: list[Any], schema: dict[str, Any], defs: dict[str, Any]) -> Any:
        comment_count = max(
            len(
                re.findall(
                    r"^Comment c\d+: ", _message_text(messages), flags=re.MULTILINE
                )
            ),
            1,
        )

        def build(schema: dict[str, Any], defs: dict[str, Any], index: int = 0) -> Any:
            schema = _resolve_ref(schema, defs)
            if schema.get("type") == "array" or "items" in schema:
                return [
                    build(schema["items"], defs, index)
                    for index in range(comment_count)
                ]
            if "properties" in schema:
                return {
                    name: (
                        f"c{index}"
                        if name == "comment_id"
                        else build(sub_schema, defs, index)
                    )
                    for name, sub_schema in schema["properties"].items()
                }
            enum = schema.get("enum")
            if enum:
                return sentiment if sentiment in enum else enum[0]
            return ""

        return build(schema, defs)

    return _function_model(fill)
