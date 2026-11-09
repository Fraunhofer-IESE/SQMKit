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

import pathlib
import subprocess

import pytest
from anyio import Path
from git import Repo

from sqmkit.clients.git_client import GitClient
from sqmkit.exceptions import GitClientError
from tests.support import RepoDir


@pytest.mark.anyio
async def test_plain_directory_is_supported(tmp_path: pathlib.Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
    (tmp_path / "ignored.log").write_text("noise\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("*.log\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dependency.js").write_text(
        "module.exports = {};\n", encoding="utf-8"
    )

    client = GitClient(tmp_path)

    assert client.is_git_repo is False
    assert await client.list_visible_files() == [
        ".gitignore",
        "README.md",
        "src/app.py",
    ]
    assert await client.get_remote_url() is None
    assert await client.get_commit_count() == 0
    assert await client.get_commits() == []
    assert await client.get_first_commit_date() is None


@pytest.mark.anyio
async def test_git_repository_is_detected(repo_dir: RepoDir) -> None:
    await repo_dir.add_file("README.md", "# Project\n")

    client = GitClient(repo_dir)

    assert client.is_git_repo is True
    assert await client.list_visible_files() == ["README.md"]


@pytest.mark.anyio
async def test_deleted_tracked_file_is_not_visible(repo_dir: RepoDir) -> None:
    await repo_dir.add_file("README.md", "# Project\n")
    await repo_dir.add_file("keep.txt", "keep\n")
    Repo(str(repo_dir)).index.add(["README.md", "keep.txt"])
    pathlib.Path(str(repo_dir), "README.md").unlink()

    client = GitClient(repo_dir)

    assert await client.list_visible_files() == ["keep.txt"]


@pytest.mark.anyio
async def test_git_repository_without_commits(repo_dir: RepoDir) -> None:
    await repo_dir.add_file("README.md", "# Project\n")

    client = GitClient(repo_dir)

    assert client.is_git_repo is True
    assert await client.get_commits() == []
    assert await client.get_first_commit_date() is None


def test_missing_path_raises(tmp_path: pathlib.Path) -> None:
    with pytest.raises(GitClientError, match="does not exist"):
        GitClient(tmp_path / "missing")


@pytest.mark.anyio
async def test_clone_timeout_is_reported(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> None:
        captured.update(kwargs)
        raise subprocess.TimeoutExpired(cmd=command, timeout=1)

    monkeypatch.setattr("sqmkit.clients.git_client.git_client.subprocess.run", fake_run)
    monkeypatch.setattr(
        "sqmkit.clients.git_client.git_client.shutil.which", lambda _: "/usr/bin/git"
    )

    with pytest.raises(GitClientError, match="timed out"):
        await GitClient._clone_into(
            "https://example.com/repo", Path(str(tmp_path / "clone"))
        )

    env = captured["env"]
    assert isinstance(env, dict)
    assert env["GIT_TERMINAL_PROMPT"] == "0"
