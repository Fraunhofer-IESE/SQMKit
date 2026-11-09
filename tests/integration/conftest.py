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

import os

import pytest

# Integration tests talk to real services (GitHub/GitLab APIs, git clones). They are opt-in so the default test run stays offline and deterministic: RUN_INTEGRATION=1 pytest tests/integration Individual tests additionally skip when their credentials are not configured.


@pytest.fixture(autouse=True)
def require_integration_opt_in() -> None:
    if os.environ.get("RUN_INTEGRATION") != "1":
        pytest.skip("integration test; set RUN_INTEGRATION=1 to run")
