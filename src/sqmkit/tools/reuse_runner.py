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

import subprocess
from typing import override

from anyio import Path

from sqmkit.tools.tool_runner import ToolResult, ToolRunner
from sqmkit.utils import load_pathspec


class ReuseRunner(ToolRunner):
    _EXECUTABLE_NAME = "reuse"
    # Shared ignore patterns (gitignore syntax) exclude common dependency, build, binary, asset and documentation files from the REUSE check. They are bundled with the package and never written into the inspected repo.
    _IGNORE_SPEC = load_pathspec("common", "reuse")

    # Keep each ``reuse lint-file`` invocation well below the OS limit on the total size of the argument list by batching the file paths.
    _MAX_BATCH_ARGV_BYTES = 100_000

    @classmethod
    def _batched(cls, files: list[str]) -> list[list[str]]:
        """Split ``files`` into batches whose combined argv length is bounded."""
        batches: list[list[str]] = []
        batch: list[str] = []
        size = 0
        for file in files:
            entry_size = len(file) + 1
            if batch and size + entry_size > cls._MAX_BATCH_ARGV_BYTES:
                batches.append(batch)
                batch = []
                size = 0
            batch.append(file)
            size += entry_size
        if batch:
            batches.append(batch)
        return batches

    @override
    async def run(self, path: Path) -> ToolResult:
        executable_location = self.find_executable_location(
            ReuseRunner._EXECUTABLE_NAME
        )

        abs_path = await path.resolve()

        # Collect all files
        all_files = []
        async for file in abs_path.rglob("*"):
            if await file.is_file():
                all_files.append(file.relative_to(abs_path).as_posix())

        # Filter files based on the ignore patterns
        files_to_check = [
            file for file in all_files if not self._IGNORE_SPEC.match_file(file)
        ]

        if not files_to_check:
            # Nothing to lint. Report zero checked files so the measurement can score the LICENSE presence alone, without invoking reuse on an empty file list.
            return ToolResult(
                output="",
                checked_files=0,
            )

        # reuse plain prints by default https://reuse.readthedocs.io/en/stable/man/reuse-lint.html We lint only the files that survived the ignore-pattern filter, so no .reuseignore needs to be injected into the inspected repository. The file list is batched to stay below the OS argv size limit.
        outputs: list[str] = []
        errors: list[str] = []
        exit_codes: list[int] = []
        for batch in self._batched(files_to_check):
            try:
                lint_result = await self._run_process(
                    [executable_location, "lint-file", *batch],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    cwd=str(abs_path),
                )
            except TimeoutError:
                return ToolResult(
                    output={},
                    error=(f"reuse timed out after {self._TIMEOUT_SECONDS} seconds"),
                )
            if lint_result.stdout:
                outputs.append(lint_result.stdout.decode(errors="replace").strip())
            if lint_result.stderr:
                errors.append(lint_result.stderr.decode(errors="replace").strip())
            exit_codes.append(lint_result.returncode)

        exit_code = max(exit_codes)
        # reuse exits 1 when it reports findings; anything above that is a genuine execution failure.
        error = (
            ("\n".join(errors) or f"reuse exited with code {exit_code}")
            if exit_code > 1
            else None
        )
        return ToolResult(
            output="\n".join(outputs),
            error=error,
            checked_files=len(files_to_check),
        )
