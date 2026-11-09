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

import pathlib

from typer.testing import CliRunner

from sqmkit.cli.main import _resolve_local_path, _resolve_quality_model, app
from sqmkit.evaluation import RepoKind


def test_dot_path_uses_resolved_directory_name(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    spec = _resolve_local_path(".")

    assert spec is not None
    name, kind, source = spec
    assert name == tmp_path.name
    assert kind is RepoKind.LOCAL
    assert source == "."


def test_bundled_quality_model_is_resolved_by_name() -> None:
    name, path = _resolve_quality_model("oss-adoption")

    assert name == "oss-adoption"
    assert path.name == "oss-adoption.json"
    assert path.is_file()


def test_quality_model_can_be_resolved_from_a_path(tmp_path: pathlib.Path) -> None:
    model = tmp_path / "my-model.json"
    model.write_text('{"name": "Test", "weight": 1, "submodels": []}', encoding="utf-8")

    name, path = _resolve_quality_model(str(model))

    assert name == "my-model"
    assert path == model


def test_help_lists_run_and_quality_models() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "run" in result.output
    assert "quality-models" in result.output


def test_run_help_is_available() -> None:
    result = CliRunner().invoke(app, ["run", "--help"])

    assert result.exit_code == 0
    assert "quality_model" in result.output
    assert "repo" in result.output


def test_quality_models_lists_bundled_models() -> None:
    result = CliRunner().invoke(app, ["quality-models"])

    assert result.exit_code == 0
    assert "oss-adoption" in result.output


def test_unknown_quality_model_is_a_usage_error() -> None:
    result = CliRunner().invoke(app, ["run", "does-not-exist", "."])

    assert result.exit_code == 2


def test_json_requires_a_repository() -> None:
    result = CliRunner().invoke(app, ["run", "--json", "oss-adoption"])

    assert result.exit_code == 2
