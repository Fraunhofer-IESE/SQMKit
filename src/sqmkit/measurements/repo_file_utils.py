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

import re
from collections.abc import Sequence
from enum import StrEnum
from pathlib import PurePosixPath

from anyio import Path

from sqmkit.clients.git_client import GitClient
from sqmkit.exceptions import GitClientError

# Compose files: compose[.variant].yml/.yaml and docker-compose[...], but not override files, which Compose merges into their base rather than deploying alone.
_DOCKER_COMPOSE_PATTERN = re.compile(r"^(?:docker-)?compose(?:[._-].*)?\.ya?ml$")

# License files often carry a suffix (LICENSE-MIT, COPYING.LESSER, ...).
_LICENSE_FILE_PATTERN = re.compile(r"^(?:licen[cs]e|copying|unlicense)(?:[._-].*)?$")

# Directories that hold examples/tests/docs rather than deployable stacks; a Compose file inside one is not the project's own container configuration.
_EXCLUDED_DIRS = frozenset(
    {"examples", "example", "samples", "sample", "docs", "test", "tests", ".github"}
)


class RepositoryFile(StrEnum):
    README = "readme"
    LICENSE = "license"
    CODE_OF_CONDUCT = "code_of_conduct"
    CONTRIBUTING = "contributing"
    SECURITY = "security"
    DOCKER_COMPOSE = "docker_compose"

    @property
    def candidate_names(self) -> list[str]:
        """Return a list of possible filenames (case-insensitive) for this file type."""
        match self:
            case RepositoryFile.README:
                return ["readme.md", "readme.txt", "readme.rst", "readme"]
            case RepositoryFile.LICENSE:
                return ["license", "license.md", "license.txt", "copying"]
            case RepositoryFile.CODE_OF_CONDUCT:
                return [
                    "code_of_conduct.md",
                    "code_of_conduct.txt",
                    "code-of-conduct.md",
                    "code-of-conduct.txt",
                    "codeofconduct.md",
                    "codeofconduct.txt",
                ]
            case RepositoryFile.CONTRIBUTING:
                return [
                    "contributing.md",
                    "contributing.txt",
                    "contributing.rst",
                ]
            case RepositoryFile.SECURITY:
                return ["security.md", "security.txt", "security.rst"]
        return []

    def matches(self, filename: str) -> bool:
        """Whether a base ``filename`` belongs to this file type (case-insensitive). Compose files additionally match variants such as ``compose.prod.yml`` or ``docker-compose.ci.yaml``, but never override files."""
        name = filename.lower()
        if self is RepositoryFile.DOCKER_COMPOSE:
            return "override" not in name and bool(_DOCKER_COMPOSE_PATTERN.match(name))
        if self is RepositoryFile.LICENSE:
            return bool(_LICENSE_FILE_PATTERN.match(name))
        return name in {candidate.lower() for candidate in self.candidate_names}


def _in_excluded_dir(parts: tuple[str, ...]) -> bool:
    return bool(set(parts[:-1]) & _EXCLUDED_DIRS)


async def find_file(repo_path: Path, file_type: RepositoryFile) -> Path | None:
    """Find a repository file (case-insensitive) in the repository root. License files additionally fall back to the first file in a REUSE-style ``LICENSES/`` directory when no root license file exists."""
    async for entry in repo_path.iterdir():
        if await entry.is_file() and file_type.matches(entry.name):
            return entry

    if file_type is RepositoryFile.LICENSE:
        licenses_dir = repo_path / "LICENSES"
        if await licenses_dir.is_dir():
            async for entry in licenses_dir.iterdir():
                if await entry.is_file():
                    return entry

    return None


async def find_files(
    git_client: GitClient,
    file_type: RepositoryFile,
    *,
    recursive: bool = False,
) -> Sequence[Path]:
    """Find all matching repository files, in path order. With ``recursive=True`` the whole repository is searched, skipping git-ignored files and example/test/doc directories."""
    repo_path = git_client.repo_path
    if not recursive:
        found: list[Path] = []
        async for entry in repo_path.iterdir():
            if await entry.is_file() and file_type.matches(entry.name):
                found.append(entry)
        return sorted(found)

    try:
        visible_files = await git_client.list_visible_files()
    except GitClientError:
        return []

    matches: list[Path] = []
    for visible_path in visible_files:
        parts = PurePosixPath(visible_path).parts
        if _in_excluded_dir(parts):
            continue
        if file_type.matches(parts[-1]):
            matches.append(repo_path / visible_path)
    return sorted(matches)
