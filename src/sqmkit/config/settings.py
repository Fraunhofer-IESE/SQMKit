# Copyright (C) Fraunhofer IESE 2026 Jonathan Ullrich
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
from collections import defaultdict
from typing import TYPE_CHECKING

from dotenv import find_dotenv, load_dotenv
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from sqmkit.clients.model_client.model_config import ModelConfig


load_dotenv(find_dotenv(usecwd=True))


_MODEL_ENV_PREFIX = "MODEL_"

# Each configured model is described by MODEL_<ID>_<FIELD> env vars, where <ID> is a free label (e.g. QWEN, CLAUDE, LOCAL). The field suffix is matched from the right so <ID> may contain underscores.
_MODEL_FIELD_SUFFIXES: dict[str, str] = {
    "_PROVIDER": "provider",
    "_MODEL_NAME": "model_name",
    "_BASE_URL": "base_url",
    "_API_KEY": "api_key",
}


class Settings(BaseSettings):
    # load from .env file https://docs.pydantic.dev/latest/concepts/pydantic_settings/#settings-management
    model_config = SettingsConfigDict(
        env_file=find_dotenv(usecwd=True) or None,
        env_file_encoding="utf-8",
        extra="ignore",
        # Our settings fields are prefixed with ``model_`` on purpose.
        protected_namespaces=(),
    )

    # Git forge API keys. Both are optional; only the matching forge is used.
    github_api_key: str = Field(default="", description="API key for GitHub")
    gitlab_api_key: str = Field(
        default="", description="API key for GitLab (and self-hosted GitLab)"
    )

    # Optional path to a custom allow-list of OpenCoDE-compatible license ids; defaults to the bundled list.
    license_allowlist_path: str = Field(
        default="",
        description="Path to a custom license allow-list. Set via LICENSE_ALLOWLIST_PATH.",
    )

    # Models
    model_context_size: int = Field(
        default=32768,
        description="Maximum context size in tokens for model calls. Set via MODEL_CONTEXT_SIZE env var.",
    )

    def get_model_configs(self) -> "list[ModelConfig]":
        """Resolve configured models from the environment. Every ``MODEL_<ID>_<FIELD>`` group becomes one :class:`ModelConfig`. A group is only kept if it has a valid ``PROVIDER``, a ``MODEL_NAME`` and an ``API_KEY``. Without credentials a configured model cannot be used, so it is skipped instead of failing every model measurement. This is pure data: no model SDK is constructed here."""
        from sqmkit.clients.model_client.model_config import ModelConfig, Provider

        model_env: dict[str, dict[str, str]] = defaultdict(dict)

        for key, value in os.environ.items():
            if not key.startswith(_MODEL_ENV_PREFIX):
                continue
            for suffix, field in _MODEL_FIELD_SUFFIXES.items():
                if key.endswith(suffix):
                    model_id = key[len(_MODEL_ENV_PREFIX) : -len(suffix)]
                    if model_id:
                        model_env[model_id][field] = value
                    break

        configs: list[ModelConfig] = []
        for model_id, fields in model_env.items():
            provider_value = fields.get("provider")
            model_name = fields.get("model_name")
            api_key = fields.get("api_key")
            if not provider_value or not model_name or not api_key:
                continue
            try:
                provider = Provider(provider_value)
            except ValueError:
                continue
            configs.append(
                ModelConfig(
                    id=model_id,
                    provider=provider,
                    model_name=model_name,
                    base_url=fields.get("base_url"),
                    api_key=SecretStr(api_key),
                )
            )

        return sorted(configs, key=lambda config: config.id)


settings = Settings()
