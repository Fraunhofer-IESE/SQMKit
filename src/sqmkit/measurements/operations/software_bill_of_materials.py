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

from pathlib import PurePosixPath
from typing import override

from anyio import Path
from cyclonedx.schema import SchemaVersion
from cyclonedx.validation.json import JsonValidator as CycloneDXJsonValidator
from cyclonedx.validation.xml import XmlValidator as CycloneDXXmlValidator
from spdx_tools.spdx.parser.parse_anything import parse_file as parse_spdx_file
from spdx_tools.spdx.validation.document_validator import validate_full_spdx_document

from sqmkit.clients.git_client import GitClient
from sqmkit.exceptions import GitClientError
from sqmkit.measurements import EvaluationStatus, Measurement, MeasurementOutput


class SoftwareBillOfMaterials(Measurement):
    _CYCLONEDX_JSON_VERSIONS = tuple(
        v for v in SchemaVersion if v >= SchemaVersion.V1_2
    )
    _CYCLONEDX_XML_VERSIONS = tuple(SchemaVersion)
    _MAX_FILE_SIZE = 10 * 1024 * 1024  # Do not open files larger than 10MB

    # Bound how many candidate files are parsed, to keep the scan cheap on large repositories that contain many JSON/XML files. TODO: avoid this fixed cap (prefer SBOM-like filenames first) and report the SBOM path relative to the repository instead of the absolute path.
    _MAX_CANDIDATES = 200
    _CANDIDATE_EXTENSIONS = (
        ".json",
        ".xml",
        ".spdx",
        ".rdf",
        ".rdfxml",
        ".yml",
        ".yaml",
    )

    def __init__(self, git_client: GitClient):
        self.git_client = git_client
        self.repo_path = git_client.repo_path

    @override
    async def execute(self) -> MeasurementOutput:
        found_sbom: Path | None = None

        for item in await self._candidate_files():
            try:
                # in case the file is some other large file
                if (await item.stat()).st_size > SoftwareBillOfMaterials._MAX_FILE_SIZE:
                    continue

                content = await item.read_text()
                is_valid = False
                current_ext = item.suffix.lower()

                # try CycloneDX validation
                if current_ext == ".json":
                    is_valid = any(
                        CycloneDXJsonValidator(v).validate_str(content) is None
                        for v in SoftwareBillOfMaterials._CYCLONEDX_JSON_VERSIONS
                    )
                elif current_ext == ".xml":
                    is_valid = any(
                        CycloneDXXmlValidator(v).validate_str(content) is None
                        for v in SoftwareBillOfMaterials._CYCLONEDX_XML_VERSIONS
                    )

                # try SPDX validation
                if not is_valid:
                    try:
                        # parse_spdx_file handles tag-value, JSON, and YAML internally
                        doc = parse_spdx_file(str(item))
                        if len(validate_full_spdx_document(doc)) == 0:
                            is_valid = True
                    except Exception:
                        pass

                if is_valid:
                    found_sbom = item
                    break

            except Exception:
                continue

        score = 1.0 if found_sbom else 0.0
        reason = (
            f"The SBOM file {found_sbom} was found in the repository"
            if found_sbom
            else "No Software Bill of Materials (SBOM) file was found in the repository"
        )

        return MeasurementOutput(
            status=EvaluationStatus.EVALUATED,
            score=score,
            reason=reason,
        )

    async def _candidate_files(self) -> list[Path]:
        """Return SBOM candidates git can see, ordered by depth then path. Git-ignored and dependency/build files are skipped by git itself. The deterministic depth-then-path order prefers a project's own SBOM over one vendored inside a dependency."""
        try:
            visible_files = await self.git_client.list_visible_files()
        except GitClientError:
            return []

        candidates: list[tuple[int, Path]] = []
        for relative in visible_files:
            candidate = PurePosixPath(relative)
            if (
                candidate.suffix.lower()
                not in SoftwareBillOfMaterials._CANDIDATE_EXTENSIONS
            ):
                continue
            candidates.append((len(candidate.parts), self.repo_path / relative))

        candidates.sort(key=lambda entry: (entry[0], str(entry[1])))
        return [
            path for _, path in candidates[: SoftwareBillOfMaterials._MAX_CANDIDATES]
        ]
