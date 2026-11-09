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

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class Comment(BaseModel):
    id: str
    author: str | None
    created_at: datetime
    body: str


class Issue(BaseModel):
    id: str
    title: str
    description: str | None = None
    state: Literal[
        "opened", "open", "closed"
    ]  # Gitlab uses 'opened, closed'; Github uses 'open, closed'
    author: str | None
    created_at: datetime
    closed_at: datetime | None = None
    comments: list[Comment] = Field(default_factory=list)


class IssueTracker(ABC):
    def __init__(self, url: HttpUrl):
        self.url = url

    @abstractmethod
    async def get_issues(self, end_date: datetime) -> list[Issue]:
        """Return the issues between now and an end date."""
