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

from pydantic import BaseModel, SecretStr


class Provider(StrEnum):
    """Supported model backends."""

    # Any OpenAI-compatible chat API (OpenAI, vLLM, Ollama, ...).
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    # Decision models served over the System One API (TypeSafe Jev, CLM, ...).
    SYSTEMONE = "systemone"


class ModelConfig(BaseModel):
    """A single configured model, resolved from ``MODEL_<ID>_<FIELD>`` env vars. Pure configuration data: no Pydantic AI (or any other SDK) is imported here."""

    id: str
    provider: Provider
    model_name: str
    base_url: str | None = None
    api_key: SecretStr | None = None
