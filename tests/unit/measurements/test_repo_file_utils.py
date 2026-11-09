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

import pytest
from git import Repo

from sqmkit.clients.git_client import GitClient
from sqmkit.measurements.repo_file_utils import (
    RepositoryFile,
    find_file,
    find_files,
)
from tests.support import RepoDir


@pytest.mark.anyio
async def test_find_file_at_root_level_readme_exists(repo_dir: RepoDir):
    # Create a README file
    await repo_dir.add_file("README.md", "This is a README file.")
    assert await find_file(repo_dir, RepositoryFile.README)


@pytest.mark.anyio
async def test_find_file_at_root_level_license_exists(repo_dir: RepoDir):
    # Create a LICENSE file
    await repo_dir.add_file("LICENSE", "This is a LICENSE file.")
    assert await find_file(repo_dir, RepositoryFile.LICENSE)


@pytest.mark.anyio
async def test_find_file_license_with_suffix(repo_dir: RepoDir):
    await repo_dir.add_file("LICENSE-MIT", "MIT")

    assert await find_file(repo_dir, RepositoryFile.LICENSE)


@pytest.mark.anyio
async def test_find_file_license_in_licenses_directory(repo_dir: RepoDir):
    await repo_dir.add_file("LICENSES/MIT.txt", "MIT")

    assert await find_file(repo_dir, RepositoryFile.LICENSE)


@pytest.mark.anyio
async def test_find_file_at_root_level_file_does_not_exist(repo_dir: RepoDir):
    # Check for a non-existing file
    assert not await find_file(repo_dir, RepositoryFile.CONTRIBUTING)


@pytest.mark.anyio
async def test_find_file_at_root_level_empty_directory(repo_dir: RepoDir):
    # Check an empty directory
    assert not await find_file(repo_dir, RepositoryFile.README)


@pytest.mark.anyio
async def test_find_file_partial_name_no_match(repo_dir: RepoDir):
    # Create a file with partial matching name
    await repo_dir.add_file("MYREADME.md", "My custom README")
    # Should not match partial names
    result = await find_file(repo_dir, RepositoryFile.README)
    assert result is None


def test_compose_matching_variants_and_overrides() -> None:
    compose = RepositoryFile.DOCKER_COMPOSE

    assert compose.matches("compose.yml")
    assert compose.matches("docker-compose.yaml")
    assert compose.matches("compose.prod.yml")
    assert compose.matches("docker-compose.ci.yaml")
    # Overrides are merged into their base, not standalone stacks.
    assert not compose.matches("compose.override.yml")
    assert not compose.matches("docker-compose.override.yaml")
    assert not compose.matches("compose2.yml")
    assert not compose.matches("my-compose.yml")


@pytest.mark.anyio
async def test_find_files_recursive_skips_examples_and_overrides(repo_dir: RepoDir):
    await repo_dir.add_file("compose.yml", "services: {}")
    await repo_dir.add_file("apps/api/compose.yml", "services: {}")
    await repo_dir.add_file("compose.prod.yml", "services: {}")
    await repo_dir.add_file("compose.override.yml", "services: {}")
    await repo_dir.add_file("examples/demo/compose.yml", "services: {}")

    found = await find_files(
        GitClient(repo_dir), RepositoryFile.DOCKER_COMPOSE, recursive=True
    )

    relative = sorted(path.relative_to(repo_dir).as_posix() for path in found)
    assert relative == ["apps/api/compose.yml", "compose.prod.yml", "compose.yml"]


@pytest.mark.anyio
async def test_find_files_recursive_ignores_deleted_tracked_files(repo_dir: RepoDir):
    compose = await repo_dir.add_file("compose.yml", "services: {}")
    Repo(str(repo_dir)).index.add(["compose.yml"])
    pathlib.Path(str(compose)).unlink()

    found = await find_files(
        GitClient(repo_dir), RepositoryFile.DOCKER_COMPOSE, recursive=True
    )

    assert found == []


@pytest.mark.anyio
async def test_find_files_recursive_respects_gitignore(repo_dir: RepoDir):
    await repo_dir.add_file(".gitignore", "vendor/\n")
    await repo_dir.add_file("compose.yml", "services: {}")
    await repo_dir.add_file("vendor/compose.yml", "services: {}")

    found = await find_files(
        GitClient(repo_dir), RepositoryFile.DOCKER_COMPOSE, recursive=True
    )

    relative = sorted(path.relative_to(repo_dir).as_posix() for path in found)
    assert relative == ["compose.yml"]
