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
import shutil
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from anyio import Path, fail_after, run_process

from sqmkit.exceptions import ToolNotFoundError


@dataclass
class ToolResult:
    """Result of running an external tool. ``error`` is the single failure signal: it is ``None`` when the tool ran successfully (with or without findings) and contains a human-readable description when the tool could not be executed reliably. Findings are encoded in ``output``."""

    output: Any
    error: str | None = None
    checked_files: int | None = None

    @property
    def failure(self) -> bool:
        return self.error is not None


class ToolRunner(ABC):
    _EXECUTABLE_NAME: str
    _TIMEOUT_SECONDS = 600

    async def _run_process(self, *args: Any, **kwargs: Any) -> Any:
        """Run a subprocess with a bounded runtime so a hung tool cannot block the evaluation."""
        with fail_after(self._TIMEOUT_SECONDS):
            return await run_process(*args, **kwargs)

    @staticmethod
    def find_executable_location(executable_name: str) -> str:
        """Resolve executable: PATH first, then venv bin dir, then error."""
        found = shutil.which(executable_name)
        if found:
            return found

        # Fall back to the venv's bin directory (e.g. for uv-managed tools)
        venv_bin = pathlib.Path(sys.executable).parent / executable_name
        if venv_bin.is_file():
            return str(venv_bin)

        raise ToolNotFoundError(
            f"'{executable_name}' not found on PATH or in venv ({venv_bin})"
        )

    @classmethod
    def is_available(cls) -> bool:
        """Whether this runner's executable can be resolved (PATH or venv)."""
        try:
            cls.find_executable_location(cls._EXECUTABLE_NAME)
        except ToolNotFoundError:
            return False
        return True

    @abstractmethod
    async def run(self, path: Path) -> ToolResult:
        pass
