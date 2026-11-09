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
import subprocess
from typing import override

from anyio import Path

from sqmkit.tools.tool_runner import ToolResult, ToolRunner
from sqmkit.utils import load_patterns


class LizardRunner(ToolRunner):
    _EXECUTABLE_NAME = "lizard"
    _IGNORED_PATTERNS = load_patterns("lizard")

    @override
    async def run(self, path: Path) -> ToolResult:
        executable_location = self.find_executable_location(
            LizardRunner._EXECUTABLE_NAME
        )

        # Build command
        command = [executable_location, "-Eduplicate", str(path)]
        for pattern in self._IGNORED_PATTERNS:
            command.extend(
                [
                    "-x",
                    pattern,
                ]
            )

        try:
            result = await self._run_process(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        except TimeoutError:
            return ToolResult(
                output={},
                error=f"lizard timed out after {self._TIMEOUT_SECONDS} seconds",
            )

        stdout = result.stdout.decode(errors="replace").strip() if result.stdout else ""
        stderr = result.stderr.decode(errors="replace").strip() if result.stderr else ""

        returncode = result.returncode

        if returncode > 1:
            return ToolResult(
                output=stdout,
                error=stderr or f"lizard exited with code {returncode}",
            )

        # Lizard may return exit code 1 because warnings were detected. This does not necessarily mean that the analysis failed. Therefore, we first try to extract the duplication rate from stdout.
        output = {}
        match = re.search(
            r"Total duplicate rate:\s*([\d.]+)%",
            stdout,
        )

        # If no duplication rate was produced, the result cannot be used for the measurement.
        if match is None:
            return ToolResult(
                output=stdout,
                error="Lizard failed to produce a duplicate rate.",
            )

        duplicate_rate_pct = float(match.group(1))
        output["duplicate_rate_pct"] = duplicate_rate_pct

        nloc_match = re.search(r"Total nloc[^\n]*\n-+\n\s*(\d+)", stdout)
        if nloc_match is not None:
            output["total_nloc"] = int(nloc_match.group(1))

        return ToolResult(output=output)
