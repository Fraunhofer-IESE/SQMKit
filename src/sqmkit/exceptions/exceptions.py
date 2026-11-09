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


class SqmKitError(Exception):
    """Base class for expected errors raised by SQMKit. The evaluator catches this type and turns it into an errored result node, so a single failing measurement cannot abort an entire repository run."""


class MeasurementError(SqmKitError):
    """Raised when a measurement execution fails."""


class ToolNotFoundError(SqmKitError):
    """Raised when a required external executable cannot be found."""


class IssueTrackerError(SqmKitError):
    """Raised when an issue tracker operation fails."""


class GitClientError(SqmKitError):
    """Raised when a Git client operation fails."""
