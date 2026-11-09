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

import json
import subprocess
from typing import override

from anyio import Path

from sqmkit.tools.tool_runner import ToolResult, ToolRunner


class ComposeLintRunner(ToolRunner):
    """Runs compose-lint (a pip-installable Docker Compose linter) on one file. https://github.com/tmatens/compose-lint"""

    _EXECUTABLE_NAME = "compose-lint"

    @override
    async def run(self, path: Path) -> ToolResult:
        executable_location = self.find_executable_location(
            ComposeLintRunner._EXECUTABLE_NAME
        )

        # ``--allow-partial-coverage`` demotes coverage gaps to warnings instead of exit code 2, so a complete-but-partially-readable stack still grades.
        try:
            result = await self._run_process(
                [
                    executable_location,
                    "check",
                    "--format",
                    "json",
                    "--fail-on",
                    "low",
                    "--allow-partial-coverage",
                    "--",
                    path.name,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                cwd=str(path.parent),
            )
        except TimeoutError:
            return ToolResult(
                output={},
                error=(f"compose-lint timed out after {self._TIMEOUT_SECONDS} seconds"),
            )

        stdout = (
            result.stdout.decode(errors="replace").strip() if result.stdout else None
        )
        stderr = (
            result.stderr.decode(errors="replace").strip() if result.stderr else None
        )

        output: object = {}
        if stdout:
            try:
                output = json.loads(stdout)
            except json.JSONDecodeError:
                return ToolResult(
                    output={},
                    error="JSON parsing of compose-lint output failed",
                )

        # compose-lint exits 1 when there are findings at or above --fail-on and 2 when it could not run; exit code 2 is the execution failure.
        error = (
            (stderr or f"compose-lint exited with code {result.returncode}")
            if result.returncode > 1
            else None
        )
        return ToolResult(output=output, error=error)
