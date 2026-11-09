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

"""Context-window handling shared by the model tasks."""

from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

from sqmkit.config import settings
from sqmkit.exceptions import MeasurementError


def truncate_middle(text: str, max_chars: int) -> str:
    """Crop ``text`` to exactly ``max_chars`` characters, keeping head and tail. The ellipsis is included in the budget, so the returned string never exceeds ``max_chars``. If ``max_chars`` is too small for an ellipsis, the beginning of the text is returned unchanged in length."""
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]

    available = max_chars - 3
    head = available // 2
    tail = available - head
    return f"{text[:head]}...{text[-tail:]}"


def comment_char_budget() -> int:
    """Max characters for a single comment. Leave room for the prompt template and the model's answer inside the configured context window. Mirrors the 1 token ~= 4 characters heuristic used in :func:`check_context_overflow`."""
    return max(int(settings.model_context_size * 4 * 0.5), 1000)


def check_context_overflow(text: str) -> bool:
    # we apply a heuristic of 4 chars are equal to one token this is usually on upper bound and underestimates actual tokens this heuristic is good enough and does not require model-specific tokenizer see https://platform.openai.com/tokenizer
    estimated_tokens = len(text) / 4
    return estimated_tokens > settings.model_context_size


def split_context(context: str, prompt: str) -> list[str]:
    """Split context into chunks that fit within the configured context size."""
    overhead_tokens = len(prompt) / 4
    available_tokens = settings.model_context_size - overhead_tokens
    chunk_size = int(available_tokens * 4)  # chars, matching the /4 heuristic

    if chunk_size <= 0:
        raise MeasurementError(
            "The configured model context size "
            f"({settings.model_context_size} tokens) is too small for the "
            "evaluation prompt; increase MODEL_CONTEXT_SIZE."
        )

    splitter = RecursiveCharacterTextSplitter.from_language(
        language=Language.MARKDOWN,
        chunk_size=chunk_size,
        chunk_overlap=0,
    )

    return splitter.split_text(context)
