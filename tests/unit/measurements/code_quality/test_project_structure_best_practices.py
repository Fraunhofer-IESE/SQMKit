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
from sqmkit.measurements.code_quality.project_structure_best_practices import (
    ProjectStructureBestPractices,
)
from tests.support import RepoDir

POOR_PROJECT_STRUCTURE = {
    "main.py": "",
    "utils.py": "",
    "helper.py": "",
    "sqmkit.config.json": "",
    "test.py": "",
    "data.csv": "",
    "output.txt": "",
    "script2.py": "",
    "OLD_main.py": "",
    "temp_fix.py": "",
}

GOOD_PROJECT_STRUCTURE = {
    ".venv/pyvenv.cfg": "",  # should be ignored
    "pkg.egg-info/PKG-INFO": "",  # should be ignored
    "Thumbs.db": "",  # should be ignored
    "swap.swp": "",  # should be ignored
    "src/__init__.py": "",
    "src/main.py": "",
    "src/api/__init__.py": "",
    "src/api/routes.py": "",
    "src/api/middleware.py": "",
    "src/services/__init__.py": "",
    "src/services/user_service.py": "",
    "src/services/auth_service.py": "",
    "src/models/__init__.py": "",
    "src/models/user.py": "",
    "src/utils/__init__.py": "",
    "src/utils/helpers.py": "",
    "tests/__init__.py": "",
    "tests/unit/__init__.py": "",
    "tests/unit/test_user_service.py": "",
    "tests/integration/__init__.py": "",
    "tests/integration/test_api.py": "",
    "docs/README.md": "",
    "docs/API.md": "",
    "config/settings.py": "",
    "config/logging.yaml": "",
    "pyproject.toml": "",
    "Makefile": "",
}


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_project_structure_best_practices_good_structure(
    repo_dir: RepoDir,
    make_model_client: Callable[..., ModelClient],
):
    for file_path, content in GOOD_PROJECT_STRUCTURE.items():
        await repo_dir.add_file(file_path, content)

    measurement = ProjectStructureBestPractices(repo_dir, make_model_client(score=5))
    result = await measurement.execute()

    assert result.score >= 0.5
    assert "Project structure evaluation:" in result.reason


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_project_structure_best_practices_poor_structure(
    repo_dir: RepoDir,
    make_model_client: Callable[..., ModelClient],
):
    for file_path, content in POOR_PROJECT_STRUCTURE.items():
        await repo_dir.add_file(file_path, content)

    measurement = ProjectStructureBestPractices(repo_dir, make_model_client(score=1))
    result = await measurement.execute()

    assert result.score <= 0.5
    assert "Project structure evaluation:" in result.reason


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_build_repo_tree_excludes_ignored_paths(
    repo_dir: RepoDir,
    make_model_client: Callable[..., ModelClient],
) -> None:
    await repo_dir.add_file(".venv/pyvenv.cfg", "")
    await repo_dir.add_file("pkg.egg-info/PKG-INFO", "")
    await repo_dir.add_file("Thumbs.db", "")
    await repo_dir.add_file("swap.swp", "")
    await repo_dir.add_file("vendor/dependency.go", "")
    await repo_dir.add_file("src/main.py", "")

    measurement = ProjectStructureBestPractices(repo_dir, make_model_client())
    tree = await measurement._build_repo_tree(repo_dir)

    assert ".venv" not in tree
    assert "pyvenv.cfg" not in tree
    assert ".egg-info" not in tree
    assert "Thumbs.db" not in tree
    assert ".swp" not in tree
    assert "vendor" not in tree
    assert "main.py" in tree


# TODO add more tests that specificially test the different aspect evaluations (i.e., one with wrong casing of files, etc.)
