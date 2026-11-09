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

from enum import StrEnum

from pydantic import HttpUrl

from sqmkit.clients.git_client import GitClient
from sqmkit.clients.issue_tracker import IssueStore
from sqmkit.clients.model_client import ModelClient
from sqmkit.measurements import Measurement, Requirement
from sqmkit.measurements.code_quality import (
    CodeDuplication,
    ProjectStructureBestPractices,
)
from sqmkit.measurements.legal import (
    LicenseCompliance,
    LicenseCoverage,
)
from sqmkit.measurements.maintenance_support import (
    BusFactor,
    CommitTrend,
    CommunityGuidelines,
    IssueSentiment,
    ReadmeBestPractices,
    SolvedIssues,
)
from sqmkit.measurements.operations import (
    DockerBestPractices,
    InstallationGuide,
    SoftwareBillOfMaterials,
)
from sqmkit.measurements.security import (
    SecurityPolicyBestPractices,
    Vulnerability,
)
from sqmkit.tools import TrivyRunner


class MeasurementIds(StrEnum):
    # legal
    LICENSE_COVERAGE = "license-coverage"
    LICENSE_COMPLIANCE = "license-compliance"
    # maintenance and support
    SOLVED_ISSUES = "solved-issues"
    COMMIT_TREND = "commit-trend"
    COMMUNITY_GUIDELINES = "community-guidelines"
    COMMUNITY_DISCUSSIONS = "community-discussions"
    PROJECT_DESCRIPTION = "project-description"
    BUS_FACTOR = "bus-factor"
    # operations
    DOCKER_BEST_PRACTICES = "docker-best-practices"
    SBOM_AVAILABILITY = "sbom-availability"
    INSTALLATION_GUIDE = "installation-guide"
    # security
    SECURITY_POLICY = "security-policy"
    VULNERABILITIES = "vulnerabilities"
    # code quality
    CODE_DUPLICATION = "code-duplication"
    PROJECT_STRUCTURE = "project-structure"


_MEASUREMENT_TYPES: dict[MeasurementIds, type[Measurement]] = {
    MeasurementIds.LICENSE_COVERAGE: LicenseCoverage,
    MeasurementIds.LICENSE_COMPLIANCE: LicenseCompliance,
    MeasurementIds.SOLVED_ISSUES: SolvedIssues,
    MeasurementIds.COMMIT_TREND: CommitTrend,
    MeasurementIds.COMMUNITY_GUIDELINES: CommunityGuidelines,
    MeasurementIds.COMMUNITY_DISCUSSIONS: IssueSentiment,
    MeasurementIds.PROJECT_DESCRIPTION: ReadmeBestPractices,
    MeasurementIds.BUS_FACTOR: BusFactor,
    MeasurementIds.DOCKER_BEST_PRACTICES: DockerBestPractices,
    MeasurementIds.SBOM_AVAILABILITY: SoftwareBillOfMaterials,
    MeasurementIds.INSTALLATION_GUIDE: InstallationGuide,
    MeasurementIds.SECURITY_POLICY: SecurityPolicyBestPractices,
    MeasurementIds.VULNERABILITIES: Vulnerability,
    MeasurementIds.CODE_DUPLICATION: CodeDuplication,
    MeasurementIds.PROJECT_STRUCTURE: ProjectStructureBestPractices,
}


class MeasurementFactory:
    @staticmethod
    def get_requirements(measurement_id: MeasurementIds) -> tuple[Requirement, ...]:
        """Return the external capabilities a measurement needs."""
        return _MEASUREMENT_TYPES[measurement_id].requires

    @staticmethod
    def get_measurement(
        measurement_id: MeasurementIds,
        git_client: GitClient,
        repo_url: HttpUrl | None,
        model_client: ModelClient,
        trivy_runner: TrivyRunner,
        issue_store: IssueStore | None = None,
    ) -> Measurement:
        repo_path = git_client.repo_path
        match measurement_id:
            # legal
            case MeasurementIds.LICENSE_COVERAGE:
                return LicenseCoverage(repo_path)
            case MeasurementIds.LICENSE_COMPLIANCE:
                return LicenseCompliance(repo_path, trivy_runner)
            # maintenance and support
            case MeasurementIds.COMMUNITY_GUIDELINES:
                return CommunityGuidelines(repo_path)
            case MeasurementIds.COMMIT_TREND:
                return CommitTrend(git_client)
            case MeasurementIds.COMMUNITY_DISCUSSIONS:
                return IssueSentiment(repo_url, model_client, issue_store)
            case MeasurementIds.SOLVED_ISSUES:
                return SolvedIssues(repo_url, issue_store)
            case MeasurementIds.PROJECT_DESCRIPTION:
                return ReadmeBestPractices(repo_path, model_client)
            case MeasurementIds.BUS_FACTOR:
                return BusFactor(git_client)
            # security
            case MeasurementIds.SECURITY_POLICY:
                return SecurityPolicyBestPractices(repo_path, model_client)
            case MeasurementIds.VULNERABILITIES:
                return Vulnerability(repo_path, trivy_runner)
            # operations
            case MeasurementIds.DOCKER_BEST_PRACTICES:
                return DockerBestPractices(git_client, trivy_runner)
            case MeasurementIds.SBOM_AVAILABILITY:
                return SoftwareBillOfMaterials(git_client)
            case MeasurementIds.INSTALLATION_GUIDE:
                return InstallationGuide(repo_path, model_client)
            # code quality
            case MeasurementIds.CODE_DUPLICATION:
                return CodeDuplication(repo_path)
            case MeasurementIds.PROJECT_STRUCTURE:
                return ProjectStructureBestPractices(repo_path, model_client)
