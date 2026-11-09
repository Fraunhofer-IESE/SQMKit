# Copyright (C) Fraunhofer IESE 2026 Matthias Gerbershagen, Jonathan Ullrich, Stefan Schweitzer
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

from enum import Enum

import pytest
from anyio import Path

from sqmkit.clients.git_client import GitClient
from sqmkit.measurements import EvaluationStatus
from sqmkit.measurements.operations.software_bill_of_materials import (
    SoftwareBillOfMaterials,
)
from tests.support import RepoDir


class SbomTestFile(Path, Enum):
    CYCLONEDX_1_2_JSON = Path("./tests/test_data/test_data_sboms/CycloneDX1.2.json")
    CYCLONEDX_1_2_XML = Path("./tests/test_data/test_data_sboms/CycloneDX1.2.xml")
    SPDX_2_3_JSON = Path("./tests/test_data/test_data_sboms/SPDX2.3.json")
    SPDX_2_3_XML = Path("./tests/test_data/test_data_sboms/SPDX2.3.xml")
    SPDX_2_3_YAML = Path("./tests/test_data/test_data_sboms/SPDX2.3.yaml")
    SPDX_2_3_TAG_VALUE = Path("./tests/test_data/test_data_sboms/SPDX2.3.spdx")
    SPDX_2_3_RDF = Path("./tests/test_data/test_data_sboms/SPDX2.3.rdf")
    EMPTY_JSON = Path("./tests/test_data/test_data_sboms/empty.json")
    EMPTY_XML = Path("./tests/test_data/test_data_sboms/empty.xml")


@pytest.mark.anyio
async def test_software_bill_of_materials_file_does_not_exists(
    repo_dir: Path,
):
    check_software_bill_of_materials = SoftwareBillOfMaterials(GitClient(repo_dir))
    result = await check_software_bill_of_materials.execute()

    assert result.status is EvaluationStatus.EVALUATED
    assert result.score == 0
    assert (
        result.reason
        == "No Software Bill of Materials (SBOM) file was found in the repository"
    )


@pytest.mark.parametrize(
    "filename,file_type,expected_success,expected_score",
    [
        # CycloneDX
        (
            "sbom.json",
            SbomTestFile.CYCLONEDX_1_2_JSON,
            True,
            1.0,
        ),
        (
            "sbom.xml",
            SbomTestFile.CYCLONEDX_1_2_XML,
            True,
            1.0,
        ),
        # SPDX
        (
            "sbom.json",
            SbomTestFile.SPDX_2_3_JSON,
            True,
            1.0,
        ),
        (
            "sbom.xml",
            SbomTestFile.SPDX_2_3_XML,
            True,
            1.0,
        ),
        (
            "sbom.yaml",
            SbomTestFile.SPDX_2_3_YAML,
            True,
            1.0,
        ),
        (
            "sbom.spdx",
            SbomTestFile.SPDX_2_3_TAG_VALUE,
            True,
            1.0,
        ),
        (
            "sbom.rdf",
            SbomTestFile.SPDX_2_3_RDF,
            True,
            1.0,
        ),
        # Wrong extension
        (
            "sbom.xml",
            SbomTestFile.CYCLONEDX_1_2_JSON,
            True,
            0,
        ),
        (
            "sbom.json",
            SbomTestFile.CYCLONEDX_1_2_XML,
            True,
            0,
        ),
        # Empty / Invalid files
        (
            "sbom.json",
            SbomTestFile.EMPTY_JSON,
            True,
            0,
        ),
        (
            "sbom.xml",
            SbomTestFile.EMPTY_XML,
            True,
            0,
        ),
    ],
)
@pytest.mark.anyio
async def test_software_bill_of_materials_file_exists(
    repo_dir: RepoDir,
    filename: str,
    file_type: SbomTestFile,
    expected_success: bool,
    expected_score: float,
):
    test_file_text = await file_type.read_text()
    await repo_dir.add_file(filename, test_file_text)

    check_software_bill_of_materials = SoftwareBillOfMaterials(GitClient(repo_dir))
    result = await check_software_bill_of_materials.execute()

    assert result.status is (
        EvaluationStatus.EVALUATED if expected_success else EvaluationStatus.SKIPPED
    )
    assert result.score == expected_score


@pytest.mark.anyio
async def test_software_bill_of_materials_nested(repo_dir: RepoDir):
    content = await SbomTestFile.CYCLONEDX_1_2_JSON.read_text()
    await repo_dir.add_file("nested/dir/sbom.json", content)

    result = await SoftwareBillOfMaterials(GitClient(repo_dir)).execute()

    assert result.status is EvaluationStatus.EVALUATED
    assert result.score == 1.0


@pytest.mark.anyio
async def test_software_bill_of_materials_ignores_gitignored(repo_dir: RepoDir):
    content = await SbomTestFile.CYCLONEDX_1_2_JSON.read_text()
    await repo_dir.add_file(".gitignore", "sbom.json\n")
    await repo_dir.add_file("sbom.json", content)

    result = await SoftwareBillOfMaterials(GitClient(repo_dir)).execute()

    assert result.status is EvaluationStatus.EVALUATED
    assert result.score == 0
    assert "No Software Bill of Materials" in result.reason
