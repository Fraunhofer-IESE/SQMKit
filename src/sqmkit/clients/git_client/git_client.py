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

import os
import pathlib
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from types import TracebackType
from typing import Self

from anyio import Path, to_thread
from git import (
    GitCommandError,
    GitCommandNotFound,
    InvalidGitRepositoryError,
    NoSuchPathError,
    PathLike,
    Repo,
)
from pathspec import PathSpec

from sqmkit.exceptions import GitClientError
from sqmkit.utils import load_patterns

# Clones are bounded so a broken remote cannot block a run indefinitely.
_CLONE_TIMEOUT_SECONDS = 600


@dataclass
class CommitInfo:
    author_name: str
    author_email: str
    authored_date: datetime


class GitClient:
    """Reads repository data and optionally clones a remote; use it directly on a Git repository or plain directory, or as an async context manager that clones a remote into a temporary directory and cleans it up on exit, with plain directories supporting file-based measurements while git-history measurements check :attr:`is_git_repo` and skip themselves."""

    def __init__(
        self, repo_path: PathLike | None = None, *, clone_url: str | None = None
    ) -> None:
        self._repo: Repo | None = None
        self._repo_path: Path | None = (
            Path(str(repo_path)) if repo_path is not None else None
        )
        self._temp_dir: Path | None = None
        self._clone_url = clone_url
        if repo_path is not None:
            self._repo = self._open(repo_path)

    @staticmethod
    def _open(repo_path: PathLike) -> Repo | None:
        try:
            return Repo(repo_path)
        except InvalidGitRepositoryError:
            return None
        except NoSuchPathError as error:
            raise GitClientError(f"Path does not exist: {repo_path}") from error

    @property
    def is_git_repo(self) -> bool:
        """Whether this repository has git metadata (it may have no commits)."""
        return self._repo is not None

    @classmethod
    def cloned(cls, url: str) -> "GitClient":
        """Return a client that clones ``url`` into a temp dir on ``__aenter__``."""
        return cls(clone_url=url)

    @property
    def repo_path(self) -> Path:
        if self._repo_path is None:
            raise GitClientError("No repository path available")
        return self._repo_path

    async def __aenter__(self) -> Self:
        if self._clone_url is None:
            return self

        temp_dir = Path(tempfile.mkdtemp(prefix="sqmkit-"))
        try:
            repo = await self._clone_into(self._clone_url, temp_dir)
        except BaseException:
            # Clean up on every failure path, including cancellation. CancelledError (Ctrl+C) and KeyboardInterrupt subclass BaseException, so `except Exception` would miss them. On those paths __aenter__ never returns, __aexit__ never runs, and the temp dir would leak unless removed here.
            await to_thread.run_sync(
                lambda: shutil.rmtree(str(temp_dir), ignore_errors=True)
            )
            raise

        self._repo = repo
        self._repo_path = temp_dir
        self._temp_dir = temp_dir
        return self

    @staticmethod
    async def _clone_into(url: str, dest: Path) -> Repo:
        """Clone ``url`` into ``dest``, translating git errors to ``GitClientError``."""
        git_executable = shutil.which("git")
        if git_executable is None:
            raise GitClientError("git is not installed or not on PATH")

        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        try:
            result = await to_thread.run_sync(
                lambda: subprocess.run(
                    [git_executable, "clone", "--", url, str(dest)],
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=_CLONE_TIMEOUT_SECONDS,
                )
            )
        except subprocess.TimeoutExpired as error:
            raise GitClientError(
                f"Cloning {url} timed out after {_CLONE_TIMEOUT_SECONDS} seconds"
            ) from error

        if result.returncode != 0:
            detail = (result.stderr or "").strip() or (
                f"git exited with code {result.returncode}"
            )
            raise GitClientError(f"Failed to clone {url}: {detail}")

        try:
            return Repo(str(dest))
        except (InvalidGitRepositoryError, NoSuchPathError) as error:
            raise GitClientError(
                f"Cloning {url} did not produce a valid repository"
            ) from error

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._temp_dir is not None:
            temp_dir, self._temp_dir = self._temp_dir, None
            self._repo = None
            self._repo_path = None
            await to_thread.run_sync(
                lambda: shutil.rmtree(str(temp_dir), ignore_errors=True)
            )

    async def get_remote_url(self) -> str | None:
        """Return the URL of the ``origin`` remote, or ``None`` if there is none."""
        if self._repo is None:
            return None
        try:
            return self._repo.remotes.origin.url
        except (AttributeError, IndexError):
            return None

    async def list_visible_files(self) -> list[str]:
        """Relative POSIX paths of files present in the working tree. For Git repositories, ``--cached --others --exclude-standard`` honours ``.gitignore`` (including nested files and negations) without reimplementing its rules. Files that are tracked but deleted from the working tree are filtered out. For plain directories, walk the tree and apply the shared ignore patterns plus the root ``.gitignore``."""
        repo = self._repo
        if repo is None:
            return await self._walk_visible_files()
        try:
            output = await to_thread.run_sync(
                lambda: repo.git.ls_files("--cached", "--others", "--exclude-standard")
            )
        except (GitCommandError, GitCommandNotFound) as error:
            raise GitClientError(str(error)) from error

        root = pathlib.Path(str(self.repo_path))

        def existing_files() -> list[str]:
            return [
                line for line in output.splitlines() if line and (root / line).is_file()
            ]

        return await to_thread.run_sync(existing_files)

    async def _walk_visible_files(self) -> list[str]:
        root = self.repo_path
        patterns = list(load_patterns("common"))
        gitignore = root / ".gitignore"
        if await gitignore.is_file():
            patterns.extend(
                (
                    await gitignore.read_text(encoding="utf-8", errors="replace")
                ).splitlines()
            )
        ignore_spec = PathSpec.from_lines("gitignore", patterns)

        files: list[str] = []
        async for path in root.rglob("*"):
            if not await path.is_file():
                continue
            relative = path.relative_to(root)
            relative_posix = PurePosixPath(*relative.parts).as_posix()
            if ignore_spec.match_file(relative_posix):
                continue
            files.append(relative_posix)
        return sorted(files)

    async def get_commit_count(
        self, begin: datetime | None = None, end: datetime | None = None
    ) -> int:
        if self._repo is None:
            return 0

        args = ["--count", "--all"]
        if begin:
            args.append(f"--since={begin.strftime('%Y-%m-%d')}")
        if end:
            # if "until" is set to a future value no error is thrown and the latest commit is counted
            args.append(f"--until={end.strftime('%Y-%m-%d')}")

        count = await to_thread.run_sync(
            self._repo.git.rev_list, *args
        )  # https://git-scm.com/docs/git-rev-list
        return int(count)

    async def get_first_commit_date(self) -> datetime | None:
        repo = self._repo
        if repo is None:
            return None
        try:
            # ``HEAD`` instead of the active branch, so a detached HEAD works.
            commits = await to_thread.run_sync(
                lambda: list(repo.iter_commits(rev="HEAD", max_parents=0))
            )
        except GitCommandError:
            # e.g. an empty repository with no commits yet
            return None

        date = commits[0].authored_datetime if commits else None
        if date is not None and date.tzinfo is None:
            date = date.replace(tzinfo=UTC)
        return date

    async def get_commits(self, since: datetime | None = None) -> list[CommitInfo]:
        repo = self._repo
        if repo is None:
            return []
        # A freshly initialised repository has an unborn HEAD; ``git rev-list`` would fail, but "no commits" is a normal state, not an error.
        try:
            head_is_valid = await to_thread.run_sync(lambda: repo.head.is_valid())
        except (GitCommandError, ValueError):
            head_is_valid = False
        if not head_is_valid:
            return []
        try:
            if since is not None:
                commits = await to_thread.run_sync(
                    lambda: repo.iter_commits("--all", since=since)
                )
            else:
                commits = await to_thread.run_sync(lambda: repo.iter_commits("--all"))
        except GitCommandError as e:
            raise GitClientError(str(e)) from e

        result: list[CommitInfo] = []
        for commit in commits:
            date = commit.authored_datetime
            if date.tzinfo is None:
                date = date.replace(tzinfo=UTC)

            result.append(
                CommitInfo(
                    author_name=commit.author.name or "",
                    author_email=commit.author.email or "",
                    authored_date=date,
                )
            )

        return result
