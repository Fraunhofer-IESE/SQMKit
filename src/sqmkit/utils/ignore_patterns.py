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

import tomllib
from functools import cache
from pathlib import Path

from pathspec import PathSpec

_PATTERNS_FILE = Path(__file__).with_name("ignore_patterns.toml")


@cache
def _load_sections() -> dict[str, tuple[str, ...]]:
    data = tomllib.loads(_PATTERNS_FILE.read_text(encoding="utf-8"))
    return {
        section.lower(): tuple(entry.get("patterns", ()))
        for section, entry in data.items()
        if isinstance(entry, dict)
    }


def load_patterns(*sections: str) -> list[str]:
    """Return the patterns from the requested sections."""
    loaded = _load_sections()
    return [
        pattern for section in sections for pattern in loaded.get(section.lower(), ())
    ]


def load_pathspec(*sections: str) -> PathSpec:
    """Build a gitignore-style spec from the requested sections."""
    return PathSpec.from_lines("gitignore", load_patterns(*sections))


__all__ = ["load_pathspec", "load_patterns"]
