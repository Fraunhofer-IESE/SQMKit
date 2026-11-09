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

"""How results from several configured models are combined into one verdict."""

from collections import Counter
from collections.abc import Hashable, Sequence


def majority[T: Hashable](values: Sequence[T]) -> T:
    """Return the most common value; ties resolve to the first one seen."""
    counts = Counter(values)
    top = max(counts.values())
    for value in values:
        if counts[value] == top:
            return value
    raise ValueError("majority() requires at least one value")
