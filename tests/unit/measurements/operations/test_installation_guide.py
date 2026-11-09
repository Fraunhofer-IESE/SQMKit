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

from collections.abc import Callable

import pytest

from sqmkit.clients.model_client import ModelClient
from sqmkit.measurements import EvaluationStatus
from sqmkit.measurements.operations.installation_guide import InstallationGuide
from tests.support import RepoDir

GOOD_README = """# Demo

## Installation

1. Install Python 3.12 or newer.
2. Create a virtual environment with `python -m venv .venv`.
3. Activate it and run `pip install -e .`.
4. Verify the installation with `demo --version`.
"""


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_installation_guide_from_readme(
    repo_dir: RepoDir, make_model_client: Callable[..., ModelClient]
):
    await repo_dir.add_file("README.md", GOOD_README)

    measurement = InstallationGuide(repo_dir, make_model_client(score=5))
    result = await measurement.execute()

    assert result.status is EvaluationStatus.EVALUATED
    assert result.score > 0.5
    assert "README" in result.reason


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_installation_guide_from_docs_folder(
    repo_dir: RepoDir, make_model_client: Callable[..., ModelClient]
):
    await repo_dir.add_file("docs/installation.md", GOOD_README)

    measurement = InstallationGuide(repo_dir, make_model_client(score=4))
    result = await measurement.execute()

    assert result.status is EvaluationStatus.EVALUATED
    assert result.score > 0.5
    assert "docs/installation.md" in result.reason


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_installation_guide_from_install_file(
    repo_dir: RepoDir, make_model_client: Callable[..., ModelClient]
):
    await repo_dir.add_file("INSTALL.md", GOOD_README)

    measurement = InstallationGuide(repo_dir, make_model_client(score=5))
    result = await measurement.execute()

    assert result.status is EvaluationStatus.EVALUATED
    assert result.score > 0.5
    assert "INSTALL.md" in result.reason


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_installation_guide_missing_documentation(
    repo_dir: RepoDir, make_model_client: Callable[..., ModelClient]
):
    measurement = InstallationGuide(repo_dir, make_model_client(score=5))
    result = await measurement.execute()

    assert result.status is EvaluationStatus.EVALUATED
    assert result.score == 0.0
    assert "No README" in result.reason
