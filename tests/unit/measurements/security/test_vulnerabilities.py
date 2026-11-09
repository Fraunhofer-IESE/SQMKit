# Copyright (C) Fraunhofer IESE 2026 Matthias Gerbershagen
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

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from anyio import Path

from sqmkit.exceptions import MeasurementError
from sqmkit.measurements import EvaluationStatus
from sqmkit.measurements.security.vulnerabilities import Vulnerability
from sqmkit.tools import ToolResult


def mock_tool_result(
    exit_code: int,
    output: dict[str, Any] | None = None,
) -> ToolResult:
    return ToolResult(
        output=output,
        error="tool failed" if exit_code > 1 else None,
    )


@pytest.mark.anyio
async def test_vulnerability_no_vulnerabilities(repo_dir: Path):
    mock_runner = AsyncMock()
    mock_result = mock_tool_result(exit_code=0)
    mock_runner.run.return_value = mock_result

    with patch(
        "sqmkit.measurements.security.vulnerabilities.TrivyRunner",
        return_value=mock_runner,
    ):
        measurement = Vulnerability(repo_dir)
        result = await measurement.execute()

    assert result.status is EvaluationStatus.EVALUATED
    assert result.score == 1.0
    assert "No dependencies with security vulnerabilities were found" in result.reason


@pytest.mark.anyio
async def test_vulnerability_multiple_vulnerabilities(repo_dir: Path):
    """Test with multiple vulnerabilities in different packages."""
    mock_output: dict[str, Any] = {
        "Results": [
            {
                "Vulnerabilities": [
                    {
                        "VulnerabilityID": "GHSA-def456",
                        "PkgName": "express",
                        "FixedVersion": "4.18.0",
                        "CVSS": {
                            "nvd": {"V3Score": 9.8},
                        },
                    },
                    {
                        "VulnerabilityID": "GHSA-ghi789",
                        "PkgName": "axios",
                        "FixedVersion": "1.6.0",
                        "CVSS": {
                            "nvd": {"V3Score": 6.2},
                        },
                    },
                ]
            }
        ]
    }

    mock_runner = AsyncMock()
    mock_result = mock_tool_result(exit_code=1, output=mock_output)
    mock_runner.run.return_value = mock_result

    with patch(
        "sqmkit.measurements.security.vulnerabilities.TrivyRunner",
        return_value=mock_runner,
    ):
        measurement = Vulnerability(repo_dir)
        result = await measurement.execute()

    assert result.status is EvaluationStatus.EVALUATED
    assert result.score == 0.0
    assert "express" in result.reason
    assert "GHSA-def456" in result.reason
    assert "Criticality: 9.8" in result.reason
    assert "axios" in result.reason
    assert "GHSA-ghi789" in result.reason
    assert "Criticality: 6.2" in result.reason


@pytest.mark.anyio
async def test_vulnerability_tool_error(repo_dir: Path):
    mock_runner = AsyncMock()
    mock_result = mock_tool_result(exit_code=2)
    mock_runner.run.return_value = mock_result

    with patch(
        "sqmkit.measurements.security.vulnerabilities.TrivyRunner",
        return_value=mock_runner,
    ):
        measurement = Vulnerability(repo_dir)
        with pytest.raises(MeasurementError, match="Trivy failed"):
            await measurement.execute()
