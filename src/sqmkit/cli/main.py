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

import asyncio
import re
from collections.abc import Callable
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import TYPE_CHECKING, Annotated
from urllib.parse import urlparse

import typer
from pydantic import HttpUrl, ValidationError
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from sqmkit.clients.git_client import GitClient
from sqmkit.clients.model_client import ModelClient
from sqmkit.clients.model_client.model_factory import build_models
from sqmkit.config import settings
from sqmkit.evaluation import (
    EvaluationNode,
    EvaluationReport,
    Evaluator,
    QualityModel,
    RepoEvaluation,
    RepoKind,
)
from sqmkit.exceptions import GitClientError
from sqmkit.measurements import EvaluationStatus
from sqmkit.tools import TrivyRunner

if TYPE_CHECKING:
    from sqmkit.clients.model_client.model_config import ModelConfig

# scp-like git URL, e.g. git@github.com:owner/repo.git
_SCP_LIKE_URL = re.compile(r"^(?P<user>[^@/]+)@(?P<host>[^:/]+):(?P<path>.+)$")

_BUNDLED_MODELS_PACKAGE = "sqmkit.quality_models"


app = typer.Typer(
    name="sqmkit",
    help="A software quality model kit for assessing software repositories.",
    no_args_is_help=True,
)

error_console = Console(stderr=True)
output_console = Console()


@app.command("run")
def run(
    quality_model: Annotated[
        str,
        typer.Argument(
            help=(
                "Bundled quality model name (e.g. 'oss-adoption') or path to a "
                "quality model JSON file."
            ),
        ),
    ],
    repo: Annotated[
        list[str] | None,
        typer.Argument(
            help=(
                "Repository URL or local path to evaluate. Pass several paths "
                "to evaluate multiple repositories; omit them to be prompted."
            ),
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Print a machine-readable report on stdout and skip the confirmation prompt.",
        ),
    ] = False,
) -> None:
    """Evaluate one or more repositories against a quality model."""
    # In JSON mode all human-readable output goes to stderr so stdout stays parseable.
    console = Console(stderr=json_output)

    if json_output and not repo:
        error_console.print("[red]--json requires at least one repository.[/red]")
        raise typer.Exit(code=2)

    model_name, quality_model_data = _load_quality_model(quality_model)

    model_configs = settings.get_model_configs()
    if not json_output:
        _print_prerequisites(model_configs, model_name, console)

    repos = _collect_repos(repo or [], console=console)
    if not json_output:
        _print_repo_summary(repos, console)

    if not json_output and not typer.confirm("Start evaluation?", default=True):
        console.print("[dim]Aborted.[/dim]")
        raise typer.Exit()

    model_client = ModelClient(build_models(model_configs))
    results = asyncio.run(
        _run_evaluations(
            repos,
            quality_model_data,
            model_client,
            console=console,
            verbose=not json_output,
        )
    )

    if json_output:
        report = EvaluationReport(results=results)
        print(report.model_dump_json(indent=2))
        if any(result.error is not None for result in results):
            raise typer.Exit(code=1)
        return

    console.print()
    console.print("[bold green]Evaluation complete.[/bold green]")


@app.command("quality-models")
def list_models() -> None:
    """List the quality models bundled with SQMKit."""
    bundled = _bundled_quality_models()
    if not bundled:
        output_console.print("[yellow]No bundled quality models found.[/yellow]")
        return

    table = Table(title="Bundled quality models", title_style="bold")
    table.add_column("Name", style="cyan")
    table.add_column("Quality model")

    for name, entry in sorted(bundled.items()):
        try:
            model_name = QualityModel.from_json_file(Path(str(entry))).root.name
        except (OSError, ValueError):
            model_name = "invalid"
        table.add_row(escape(name), escape(model_name))

    output_console.print(table)


def _bundled_quality_models() -> dict[str, Traversable]:
    """Return the bundled quality models keyed by the name used on the CLI."""
    directory = resources.files(_BUNDLED_MODELS_PACKAGE)
    return {
        entry.name.removesuffix(".json"): entry
        for entry in directory.iterdir()
        if entry.name.endswith(".json")
    }


def _resolve_quality_model(spec: str) -> tuple[str, Path]:
    """Resolve a bundled model name or a path to a quality model JSON file."""
    bundled = _bundled_quality_models()
    candidate = Path(spec).expanduser()

    # A bare name prefers a bundled model; anything with a directory separator is treated as a file path.
    if len(candidate.parts) == 1:
        name = candidate.name.removesuffix(".json")
        if name in bundled:
            return name, Path(str(bundled[name]))

    if candidate.is_file():
        return candidate.stem, candidate

    if candidate.exists():
        error_console.print(
            f"[red]Quality model is not a file:[/red] {escape(str(candidate))}"
        )
        raise typer.Exit(code=2)

    available = ", ".join(sorted(bundled)) or "none"
    error_console.print(
        f"[red]Quality model not found:[/red] {escape(spec)}\n"
        f"[dim]Available bundled quality models:[/dim] {escape(available)}"
    )
    raise typer.Exit(code=2)


def _load_quality_model(spec: str) -> tuple[str, QualityModel]:
    """Resolve and parse a quality model, reporting invalid files cleanly."""
    name, path = _resolve_quality_model(spec)
    try:
        return name, QualityModel.from_json_file(path)
    except (OSError, ValueError) as error:
        error_console.print(
            f"[red]Invalid quality model[/red] {escape(str(path))}: "
            f"{escape(str(error))}"
        )
        raise typer.Exit(code=2)


def _print_prerequisites(
    model_configs: "list[ModelConfig]", quality_model_name: str, console: Console
) -> None:
    table = Table(title="Prerequisites", title_style="bold")
    table.add_column("Resource", style="cyan")
    table.add_column("Status")
    table.add_column("Usage")

    table.add_row(
        "trivy",
        _status(TrivyRunner.is_available()),
        "Security, license & Dockerfile scanning",
    )
    table.add_row(
        "GitHub API key",
        _status(bool(settings.github_api_key)),
        "Issue tracking & repo access for GitHub",
    )
    table.add_row(
        "GitLab API key",
        _status(bool(settings.gitlab_api_key)),
        "Issue tracking & repo access for GitLab",
    )

    if model_configs:
        model_label = f"Model ({', '.join(config.id for config in model_configs)})"
    else:
        model_label = "Model"
    table.add_row(
        escape(model_label), _status(bool(model_configs)), "AI-based evaluations"
    )
    table.add_row(escape(quality_model_name), "[green]✓[/green]", "Quality model")

    console.print(table)
    console.print()


def _status(available: bool) -> str:
    return "[green]✓[/green]" if available else "[red]✗[/red]"


def _collect_repos(
    initial: list[str], *, console: Console
) -> list[tuple[str, RepoKind, str]]:
    """Resolve repository arguments, falling back to prompting for repositories."""
    repos: list[tuple[str, RepoKind, str]] = []  # (name, kind, url_or_path)
    seen: set[str] = set()

    def add(spec: tuple[str, RepoKind, str]) -> None:
        identity = _repo_identity(spec[1], spec[2])
        if identity in seen:
            error_console.print(
                f"[red]Repository specified more than once:[/red] {escape(identity)}"
            )
            raise typer.Exit(code=2)
        seen.add(identity)
        repos.append(spec)

    for raw in initial:
        spec = _classify_repo(raw)
        if spec is None:
            raise typer.Exit(code=2)
        add(spec)

    if not repos:
        console.print()
        console.print(
            "[bold]Add repositories to evaluate[/bold]\n"
            "[dim]Paste a Git URL or local path, one at a time. Press Enter on an empty line when done.[/dim]"
        )

        while True:
            # Prompts go to stderr so stdout only ever carries the requested output.
            raw = typer.prompt(
                "Repo URL or path", default="", show_default=False, err=True
            ).strip()

            if not raw:
                if repos:
                    break
                console.print("[yellow]Add at least one repository.[/yellow]")
                continue

            spec = _classify_repo(raw)
            if spec is not None:
                add(spec)

    return _ensure_unique_names(repos)


def _repo_identity(kind: RepoKind, url_or_path: str) -> str:
    if kind is RepoKind.REMOTE:
        return url_or_path
    return str(Path(url_or_path).expanduser().resolve())


def _ensure_unique_names(
    repos: list[tuple[str, RepoKind, str]],
) -> list[tuple[str, RepoKind, str]]:
    """Reject repositories whose result names would collide."""
    seen: set[str] = set()
    for name, _, _ in repos:
        if name in seen:
            error_console.print(
                f"[red]Repository names must be unique:[/red] {escape(name)}"
            )
            raise typer.Exit(code=2)
        seen.add(name)
    return repos


def _classify_repo(raw: str) -> tuple[str, RepoKind, str] | None:
    """Return ``(name, kind, url_or_path)`` for a user-supplied repository."""
    forge_url = _normalize_forge_url(raw)
    if forge_url is not None:
        name = str(forge_url).rstrip("/").split("/")[-1]
        return (name, RepoKind.REMOTE, str(forge_url))
    return _resolve_local_path(raw)


def _print_repo_summary(
    repos: list[tuple[str, RepoKind, str]], console: Console
) -> None:
    table = Table(title="Repositories to Evaluate", title_style="bold")
    table.add_column("#", style="dim")
    table.add_column("Repository", style="cyan")
    table.add_column("Type")

    for i, (name, kind, _) in enumerate(repos, 1):
        type_str = (
            "[blue]remote[/blue]"
            if kind is RepoKind.REMOTE
            else "[yellow]local[/yellow]"
        )
        table.add_row(str(i), escape(name), type_str)

    console.print()
    console.print(table)
    console.print()


async def _run_evaluations(
    repos: list[tuple[str, RepoKind, str]],
    quality_model: QualityModel,
    model_client: ModelClient,
    *,
    console: Console,
    verbose: bool,
) -> list[RepoEvaluation]:
    results: list[RepoEvaluation] = []

    for name, kind, url_or_path in repos:
        if verbose:
            console.print()
            console.rule(f"[bold]{escape(name)}[/bold]")
            stage = "Cloning" if kind is RepoKind.REMOTE else "Using local repository"
            console.print(f"[dim]{stage} {escape(url_or_path)} …[/dim]")

        def on_ready() -> None:
            if verbose:
                console.print("[dim]Evaluating …[/dim]")

        try:
            repo_url, result_node = await _evaluate_repo(
                kind, url_or_path, quality_model, model_client, on_ready=on_ready
            )
        except GitClientError as error:
            message = _error_message(error)
            error_console.print(
                f"[red]Repository error ({escape(name)}):[/red] {escape(message)}"
            )
            results.append(_repository_failure(name, kind, url_or_path, message))
            continue
        except Exception as error:  # keep the CLI running per repo
            message = _error_message(error)
            error_console.print(
                f"[red]Evaluation failed ({escape(name)}):[/red] {escape(message)}"
            )
            results.append(_repository_failure(name, kind, url_or_path, message))
            continue

        results.append(
            RepoEvaluation(
                name=name,
                kind=kind,
                source=url_or_path,
                repository=repo_url,
                evaluation=result_node,
            )
        )

        if verbose:
            _print_evaluation_table(result_node, console)

    return results


def _repository_failure(
    name: str, kind: RepoKind, source: str, message: str
) -> RepoEvaluation:
    return RepoEvaluation(name=name, kind=kind, source=source, error=message)


def _error_message(error: Exception) -> str:
    return str(error) or type(error).__name__


async def _evaluate_repo(
    kind: RepoKind,
    url_or_path: str,
    quality_model: QualityModel,
    model_client: ModelClient,
    *,
    on_ready: Callable[[], None] | None = None,
) -> tuple[HttpUrl | None, EvaluationNode]:
    """Resolve one repository (cloning if needed) and evaluate it. Local repositories without a GitHub/GitLab remote are supported: the URL is ``None`` and forge-dependent measurements are skipped by the evaluator. Plain directories are supported too; git-history measurements skip when there is no repository metadata."""
    client = (
        GitClient.cloned(url_or_path)
        if kind is RepoKind.REMOTE
        else GitClient(Path(url_or_path).expanduser())
    )

    async with client:
        if on_ready is not None:
            on_ready()

        if kind is RepoKind.REMOTE:
            repo_url = _normalize_forge_url(url_or_path)
        else:
            remote = await client.get_remote_url()
            repo_url = _normalize_forge_url(remote) if remote else None

        if kind is RepoKind.REMOTE and repo_url is None:
            raise GitClientError(
                f"No usable GitHub/GitLab remote found for {url_or_path}"
            )

        evaluator = Evaluator(
            quality_model=quality_model,
            git_client=client,
            repo_url=repo_url,
            model_client=model_client,
        )

        return repo_url, await evaluator.evaluate()


def _resolve_local_path(raw: str) -> tuple[str, RepoKind, str] | None:
    """Validate a local repository path early, reporting clear errors."""
    candidate = Path(raw).expanduser()
    if not candidate.exists():
        error_console.print(
            f"[red]Invalid:[/red] '{escape(raw)}' is neither a URL nor an existing path."
        )
        return None
    if not candidate.is_dir():
        error_console.print(f"[red]Invalid:[/red] '{escape(raw)}' is not a directory.")
        return None
    resolved = candidate.resolve()
    return (resolved.name or str(resolved), RepoKind.LOCAL, str(candidate))


def _normalize_forge_url(raw: str) -> HttpUrl | None:
    """Return an HTTPS forge URL for HTTP(S)/SSH input, or ``None`` if unusable. GitHub and GitLab issue APIs only speak HTTPS, so SSH remotes are rewritten to their HTTPS equivalent. Hosts other than GitHub/GitLab return ``None``."""
    candidate = raw.strip()
    if not candidate:
        return None

    # scp-like syntax: git@github.com:owner/repo.git
    scp_like = _SCP_LIKE_URL.match(candidate)
    if scp_like:
        candidate = f"https://{scp_like.group('host')}/{scp_like.group('path')}"
    elif candidate.startswith("ssh://"):
        parsed = urlparse(candidate)
        if not parsed.hostname:
            return None
        candidate = f"https://{parsed.hostname}{parsed.path}"

    candidate = candidate.rstrip("/")
    candidate = candidate.removesuffix(".git")

    try:
        url = HttpUrl(candidate)
    except ValidationError:
        return None

    host = url.host or ""
    if "github" not in host and "gitlab" not in host:
        return None
    return url


def _print_evaluation_table(node: "EvaluationNode", console: Console) -> None:

    def _flatten(
        n: "EvaluationNode", depth: int = 0
    ) -> list[tuple[int, str, float, EvaluationStatus, float, str]]:
        """Flatten tree into rows: (depth, name, weight, status, score, reason)."""
        rows = [(depth, n.name, n.weight, n.status, n.score, n.reason)]
        for child in n.children:
            rows.extend(_flatten(child, depth + 1))
        return rows

    rows = _flatten(node)

    table = Table(title="Evaluation Results", title_style="bold", show_lines=True)
    table.add_column("Measurement", style="bold")
    table.add_column("Weight")
    table.add_column("Status")
    table.add_column("Score")
    table.add_column("Reason", overflow="fold")

    for depth, name, weight, status, score, reason in rows:
        indent = "  " * depth
        safe_name = escape(name)
        display_name = (
            f"{indent}{safe_name}"
            if depth > 0
            else f"[bold cyan]{safe_name}[/bold cyan]"
        )

        if status is EvaluationStatus.SKIPPED:
            status_str = "[dim]skipped[/dim]"
            score_str = "[dim]—[/dim]"
        elif status is EvaluationStatus.ERRORED:
            status_str = "[red]errored[/red]"
            score_str = "[red]—[/red]"
        else:
            status_str = "[green]evaluated[/green]"
            score_color = (
                "green" if score >= 0.7 else "yellow" if score >= 0.4 else "red"
            )
            score_str = f"[{score_color}]{score:.2f}[/{score_color}]"

        weight_str = f"{weight:.0%}" if depth > 0 else "—"

        table.add_row(display_name, weight_str, status_str, score_str, escape(reason))

    console.print(table)
    console.print(
        f"[dim]Measurement coverage:[/dim] {node.coverage:.0%} "
        f"({node.evaluated_measurements}/{node.total_measurements} measurements evaluated)"
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
