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

"""Turn :class:`ModelConfig` values into runnable Pydantic AI agents. This is the only place in the codebase that constructs Pydantic AI models and providers. Provider SDKs are imported lazily so that a missing optional extra only affects the provider that needs it."""

from dataclasses import dataclass

import pydantic_ai
from pydantic_ai import Agent

from sqmkit.clients.model_client.model_config import ModelConfig, Provider

# This application owns its own console output, so hide Pydantic AI's first-run banner. Set before the first agent run to suppress it process-wide.
pydantic_ai.BANNER_ENABLED = False


@dataclass(frozen=True)
class ModelHandle:
    """A configured model together with the capabilities we care about."""

    id: str
    provider: Provider
    agent: Agent
    # Decision models (System One) cannot produce free text (e.g. a reason).
    supports_text: bool


def _build_openai(config: ModelConfig) -> Agent:
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    provider = OpenAIProvider(
        base_url=config.base_url,
        api_key=config.api_key.get_secret_value() if config.api_key else None,
    )
    return Agent(OpenAIChatModel(config.model_name, provider=provider))


def _build_anthropic(config: ModelConfig) -> Agent:
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.providers.anthropic import AnthropicProvider

    provider = AnthropicProvider(
        base_url=config.base_url,
        api_key=config.api_key.get_secret_value() if config.api_key else None,
    )
    return Agent(AnthropicModel(config.model_name, provider=provider))


def _build_systemone(config: ModelConfig) -> Agent:
    from pydantic_ai.models.system_one import SystemOneModel
    from pydantic_ai.providers.system_one import SystemOneProvider

    provider = SystemOneProvider(
        base_url=config.base_url,
        api_key=config.api_key.get_secret_value() if config.api_key else None,
    )
    return Agent(SystemOneModel(config.model_name, provider=provider))


def build_models(configs: list[ModelConfig]) -> list[ModelHandle]:
    """Build one :class:`ModelHandle` per configured model, preserving order."""
    handles: list[ModelHandle] = []
    for config in configs:
        match config.provider:
            case Provider.OPENAI:
                agent = _build_openai(config)
                supports_text = True
            case Provider.ANTHROPIC:
                agent = _build_anthropic(config)
                supports_text = True
            case Provider.SYSTEMONE:
                agent = _build_systemone(config)
                supports_text = False
        handles.append(
            ModelHandle(
                id=config.id,
                provider=config.provider,
                agent=agent,
                supports_text=supports_text,
            )
        )
    return handles
