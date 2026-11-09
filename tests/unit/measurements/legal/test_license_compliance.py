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

import pytest
from anyio import Path

from sqmkit.config import settings
from sqmkit.exceptions import MeasurementError
from sqmkit.measurements import EvaluationStatus
from sqmkit.measurements.legal.license_compliance import LicenseCompliance


@pytest.mark.anyio
async def test_license_file_does_not_exist(repo_dir: Path):
    license_compliance = LicenseCompliance(repo_dir)
    result = await license_compliance.execute()

    assert result.status is EvaluationStatus.EVALUATED
    assert result.score == 0.0
    assert result.reason == "LICENSE file not found."


@pytest.mark.anyio
@pytest.mark.parametrize(
    "license_name,expected_compliant",
    [
        ("MIT", True),
        ("AGPL-3.0", True),
        ("MIT OR Apache-2.0", True),
        ("LicenseRef-Proprietary OR MIT", True),
        ("BSD-3-Clause AND MIT", True),
        ("MIT AND LicenseRef-Proprietary", False),
        ("Apache-2.0 WITH LLVM-exception", True),
        ("GPL-2.0+", True),
        ("SEE LICENSE IN LICENSE.txt", False),
        ("unknown", False),
        ("UNLICENSED", False),
    ],
)
async def test_is_compliant(
    repo_dir: Path, license_name: str, expected_compliant: bool
):
    license_compliance = LicenseCompliance(repo_dir)
    allowed = await license_compliance._load_allowed_licenses()

    assert license_compliance._is_compliant(license_name, allowed) is expected_compliant


@pytest.mark.anyio
async def test_allowlist_default(repo_dir: Path):
    allowed = await LicenseCompliance(repo_dir)._load_allowed_licenses()

    assert "mit" in allowed
    assert "apache-2.0" in allowed


@pytest.mark.anyio
async def test_allowlist_override(
    repo_dir: Path,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
):
    custom = tmp_path / "allowlist.txt"
    custom.write_text("# comment\nMIT\n\n")
    monkeypatch.setattr(settings, "license_allowlist_path", str(custom))

    allowed = await LicenseCompliance(repo_dir)._load_allowed_licenses()

    assert allowed == {"mit"}


@pytest.mark.anyio
async def test_allowlist_missing_path_raises(
    repo_dir: Path,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
):
    missing = tmp_path / "does-not-exist.txt"
    monkeypatch.setattr(settings, "license_allowlist_path", str(missing))

    with pytest.raises(MeasurementError, match="LICENSE_ALLOWLIST_PATH"):
        await LicenseCompliance(repo_dir)._load_allowed_licenses()
