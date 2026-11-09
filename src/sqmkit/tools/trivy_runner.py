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

import json
import subprocess
from typing import override

from anyio import Path

from sqmkit.tools.tool_runner import ToolResult, ToolRunner


class TrivyRunner(ToolRunner):
    """Runs Trivy against a repository, caching the result per path. A single ``trivy fs`` invocation scans for vulnerabilities, licenses and misconfigurations (including Dockerfile best practices). The result is cached so that all measurements depending on Trivy share one scan instead of each running the tool on its own."""

    _EXECUTABLE_NAME = "trivy"
    _SCANNERS = "vuln,license,misconfig"

    def __init__(self) -> None:
        self._results: dict[str, ToolResult] = {}

    @override
    async def run(self, path: Path) -> ToolResult:
        key = str(path)
        if key not in self._results:
            self._results[key] = await self._scan(path)
        return self._results[key]

    async def _scan(self, path: Path) -> ToolResult:
        executable_location = self.find_executable_location(
            TrivyRunner._EXECUTABLE_NAME
        )

        command = [
            executable_location,
            "fs",
            "--format",
            "json",
            "--scanners",
            TrivyRunner._SCANNERS,
            "--license-full",
            "--exit-code",
            "1",
            str(path),
        ]

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
                error=f"trivy timed out after {self._TIMEOUT_SECONDS} seconds",
            )

        stdout = (
            result.stdout.decode(errors="replace").strip() if result.stdout else None
        )
        stderr = (
            result.stderr.decode(errors="replace").strip() if result.stderr else None
        )

        output = {}
        if stdout:
            try:
                output = json.loads(stdout)
            except json.JSONDecodeError:
                # A scan we cannot read is an execution failure, not a clean result, so measurements report an error instead of a perfect score.
                return ToolResult(
                    output=output,
                    error="JSON parsing of trivy output failed",
                )

        # `--exit-code 1` makes Trivy return 1 when findings are present and 0 when the scan is clean. Anything higher indicates an execution error.
        error = (
            (stderr or f"trivy exited with code {result.returncode}")
            if result.returncode > 1
            else None
        )
        return ToolResult(output=output, error=error)
