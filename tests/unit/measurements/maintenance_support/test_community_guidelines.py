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

import pytest

from sqmkit.measurements.maintenance_support.community_guidelines import (
    CommunityGuidelines,
)
from tests.support import RepoDir


@pytest.mark.parametrize(
    "files,expected_score,expected_reason",
    [
        (
            [],
            0.0,
            "Code of Conduct: missing; Contributing guidelines: missing",
        ),
        (
            ["CODE_OF_CONDUCT.md"],
            0.5,
            "Code of Conduct: present",
        ),
        (
            ["CONTRIBUTING.md"],
            0.5,
            "Contributing guidelines: present",
        ),
        (
            ["CODE_OF_CONDUCT.md", "CONTRIBUTING.md"],
            1.0,
            "Code of Conduct: present",
        ),
        (
            ["code_of_conduct.txt"],
            0.5,
            "Code of Conduct: present",
        ),
        (
            ["conduct.md"],
            0.0,
            "Code of Conduct: missing",
        ),
        (
            ["codeofconduct"],
            0.0,
            "Code of Conduct: missing",
        ),
    ],
)
@pytest.mark.anyio
async def test_community_guidelines(
    repo_dir: RepoDir,
    files: list[str],
    expected_score: float,
    expected_reason: str,
):
    for filename in files:
        await repo_dir.add_file(filename, "Dummy content")

    check = CommunityGuidelines(repo_dir)
    result = await check.execute()

    assert result.score == expected_score
    assert expected_reason in result.reason
