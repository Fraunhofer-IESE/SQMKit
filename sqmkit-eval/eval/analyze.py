#!/usr/bin/env python3
"""Agreement and run-consistency analysis for the SQMKit evaluation.

Outputs only:
- human-group ordinal Krippendorff's alpha
- LLM-group ordinal Krippendorff's alpha
- linearly weighted Cohen's kappa for human consensus vs each model consensus
- per-model run consistency: identical and within-1-point rates
"""

from __future__ import annotations

import json
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

import krippendorff
import openpyxl

EVAL_DIR = Path(__file__).resolve().parent
EVAL_ROOT = EVAL_DIR.parent
OUTPUT_DIR = EVAL_ROOT / "sqmkit-output"
ANALYSIS_DIR = OUTPUT_DIR / "analysis"
HUMAN_DIR = EVAL_DIR / "human-review"

MODEL_DIRS = {
    "Qwen": OUTPUT_DIR / "Qwen3.8-27B",
    "DeepSeek": OUTPUT_DIR / "DeepSeek-V4.1-Flash-1017",
    "CLEF": OUTPUT_DIR / "clef",
}

REPOS = [
    "Smart Village App Backend",
    "DKSR Platform",
    "Kausal Paths",
    "EVB-IT Digital",
    "BuMaP Core",
    "CIB seven",
    "Ferienabenteuer",
    "Behoerden Klartext Backend",
    "OCM Open Playground Manager",
    "Mobilitaetsplattform Bamberg",
]

MEASUREMENTS = {
    "Project Description": [
        "project_purpose",
        "setup_instructions",
        "info_project_status",
        "info_maintainer",
    ],
    "Project Structure": [
        "directory_organization",
        "naming_conventions",
        "separation_of_concerns",
        "modularity",
    ],
    "Security Policy": [
        "security_contact_information",
        "vulnerability_reporting_process",
        "supported_versions",
    ],
}

HUMAN_TO_CRITERION = {
    ("README", "Project purpose"): "project_purpose",
    ("README", "Setup instructions"): "setup_instructions",
    ("README", "Project status"): "info_project_status",
    ("README", "Maintainers and contributors"): "info_maintainer",
    ("Project Structure", "Directory organization"): "directory_organization",
    ("Project Structure", "Naming conventions"): "naming_conventions",
    ("Project Structure", "Separation of concerns"): "separation_of_concerns",
    ("Project Structure", "Modularity"): "modularity",
    ("Security Policy", "Security contact"): "security_contact_information",
    ("Security Policy", "Vulnerability reporting"): "vulnerability_reporting_process",
    ("Security Policy", "Supported versions"): "supported_versions",
}

SCORE_RE = re.compile(
    r"^(?P<criterion>[A-Za-z0-9_]+):\nScore \(avg\): (?P<score>[0-9.]+)",
    re.MULTILINE,
)


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def load_human_scores(path: Path) -> dict[tuple[str, str], int]:
    """Return (repo_slug, criterion) -> score for one reviewer workbook."""
    workbook = openpyxl.load_workbook(path, data_only=True)
    scores: dict[tuple[str, str], int] = {}

    for sheet_name in workbook.sheetnames:
        if sheet_name == "Repositories":
            continue
        sheet = workbook[sheet_name]
        repo_slug = slugify(sheet_name)
        rows = list(sheet.iter_rows(values_only=True))
        header_index = next(
            (
                index
                for index, row in enumerate(rows)
                if row and str(row[0]).strip() == "Section"
            ),
            None,
        )
        if header_index is None:
            continue

        for row in rows[header_index + 1 :]:
            if not row or row[0] is None:
                continue
            section = str(row[0]).strip()
            criterion_label = str(row[1]).strip() if row[1] is not None else ""
            score = row[3] if len(row) > 3 else None
            criterion = HUMAN_TO_CRITERION.get((section, criterion_label))
            if criterion is None or score is None:
                continue
            scores[(repo_slug, criterion)] = int(score)

    return scores


def load_all_human_scores() -> dict[str, dict[tuple[str, str], int]]:
    reviewers: dict[str, dict[tuple[str, str], int]] = {}
    for path in sorted(HUMAN_DIR.glob("*.xlsx")):
        reviewer = path.stem.rsplit("-", 1)[-1]
        reviewers[reviewer] = load_human_scores(path)
    return reviewers


def load_sqmkit(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    result = data["results"][0]
    evaluation = result["evaluation"]
    measurements: dict[str, Any] = {}

    for child in evaluation["children"]:
        name = child["name"]
        criteria = {
            criterion: float(score)
            for criterion, score in SCORE_RE.findall(child["reason"])
        }
        # Missing/empty SECURITY.md gets the same floor as the human review.
        if (
            name == "Security Policy"
            and not criteria
            and child["reason"].startswith(
                ("SECURITY.md file not found", "SECURITY.md file is empty")
            )
        ):
            criteria = {
                criterion: 1.0 for criterion in MEASUREMENTS["Security Policy"]
            }
        measurements[name] = {"criteria": criteria}
    return measurements


def load_run(directory: Path) -> dict[str, dict[str, Any]]:
    reports: dict[str, dict[str, Any]] = {}
    for repo in REPOS:
        path = directory / f"{slugify(repo)}.json"
        if path.exists():
            reports[slugify(repo)] = load_sqmkit(path)
    return reports


def ordinal_alpha(matrix: list[list[float]]) -> float:
    values = {value for row in matrix for value in row}
    if not values <= {1.0, 2.0, 3.0, 4.0, 5.0}:
        raise ValueError(f"Unexpected Likert values: {sorted(values)}")
    return float(
        krippendorff.alpha(
            reliability_data=matrix,
            value_domain=[1, 2, 3, 4, 5],
            level_of_measurement="ordinal",
        )
    )


def linear_weighted_kappa(first: list[float], second: list[float]) -> float:
    """Cohen's kappa with linear weights on the 1-5 ordinal scale."""
    if len(first) != len(second) or not first:
        raise ValueError("Need equally sized, non-empty score lists.")
    n = len(first)
    observed = sum(1 - abs(a - b) / 4 for a, b in zip(first, second)) / n

    first_counts = Counter(first)
    second_counts = Counter(second)
    expected = sum(
        first_counts[a] / n * second_counts[b] / n * (1 - abs(a - b) / 4)
        for a in first_counts
        for b in second_counts
    )
    return (observed - expected) / (1 - expected)


def build_units() -> tuple[list[dict[str, Any]], list[str]]:
    human = load_all_human_scores()
    reviewers = sorted(human)
    runs = {
        model: [load_run(directory / f"run{i}") for i in (1, 2, 3)]
        for model, directory in MODEL_DIRS.items()
    }

    units: list[dict[str, Any]] = []
    for repo in REPOS:
        repo_slug = slugify(repo)
        for measurement, criteria in MEASUREMENTS.items():
            for criterion in criteria:
                human_scores = [
                    human[reviewer].get((repo_slug, criterion))
                    for reviewer in reviewers
                ]
                if any(score is None for score in human_scores):
                    raise ValueError(
                        f"Missing human score for {repo}/{criterion}."
                    )

                model_medians: dict[str, float] = {}
                model_runs: dict[str, list[float]] = {}
                for model in MODEL_DIRS:
                    values = [
                        run[repo_slug][measurement]["criteria"].get(criterion)
                        for run in runs[model]
                    ]
                    if any(value is None for value in values):
                        raise ValueError(
                            f"Missing {model} score for {repo}/{criterion}."
                        )
                    model_runs[model] = [float(value) for value in values]
                    model_medians[model] = statistics.median(model_runs[model])

                units.append(
                    {
                        "repo": repo,
                        "criterion": criterion,
                        "human_scores": [int(score) for score in human_scores],
                        "human_median": float(statistics.median(human_scores)),
                        "model_medians": model_medians,
                        "model_runs": model_runs,
                    }
                )
    return units, reviewers


def main() -> None:
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    units, reviewers = build_units()

    human_matrix = [
        [unit["human_scores"][index] for unit in units]
        for index in range(len(reviewers))
    ]
    llm_matrix = [
        [unit["model_medians"][model] for unit in units] for model in MODEL_DIRS
    ]

    human_alpha = ordinal_alpha(human_matrix)
    llm_alpha = ordinal_alpha(llm_matrix)

    kappas = {
        model: linear_weighted_kappa(
            [unit["human_median"] for unit in units],
            [unit["model_medians"][model] for unit in units],
        )
        for model in MODEL_DIRS
    }

    consistency: dict[str, Any] = {}
    for model in MODEL_DIRS:
        ranges = [
            max(unit["model_runs"][model]) - min(unit["model_runs"][model])
            for unit in units
        ]
        identical = sum(value == 0 for value in ranges)
        within_one = sum(value <= 1 for value in ranges)
        consistency[model] = {
            "n": len(ranges),
            "identical": identical,
            "identical_pct": identical / len(ranges),
            "within_one": within_one,
            "within_one_pct": within_one / len(ranges),
        }

    summary = {
        "n_units": len(units),
        "reviewers": reviewers,
        "krippendorff_alpha": {
            "human_group": round(human_alpha, 4),
            "llm_group": round(llm_alpha, 4),
            "level_of_measurement": "ordinal",
        },
        "linear_weighted_cohen_kappa": {
            model: round(value, 4) for model, value in kappas.items()
        },
        "consistency": consistency,
    }
    (ANALYSIS_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    lines = [
        "# SQMKit evaluation analysis",
        "",
        f"Units: {len(units)} criteria assessments "
        f"({len(REPOS)} repositories x {sum(len(v) for v in MEASUREMENTS.values())} criteria).",
        "",
        "## Inter-group agreement (ordinal Krippendorff's alpha)",
        "",
        "| Group | alpha |",
        "|---|---:|",
        f"| Human ({', '.join(reviewers)}) | {human_alpha:.4f} |",
        "| LLM (Qwen, DeepSeek, CLEF medians) | "
        f"{llm_alpha:.4f} |",
        "",
        "## Human consensus vs model consensus",
        "",
        "Linearly weighted Cohen's kappa on the 1-5 scale.",
        "",
        "| Comparison | kappa |",
        "|---|---:|",
        f"| Human median vs Qwen median | {kappas['Qwen']:.4f} |",
        f"| Human median vs DeepSeek median | {kappas['DeepSeek']:.4f} |",
        f"| Human median vs CLEF median | {kappas['CLEF']:.4f} |",
        "",
        "## Run consistency",
        "",
        "| Model | Identical across 3 runs | Within 1 point |",
        "|---|---:|---:|",
    ]
    for model in MODEL_DIRS:
        values = consistency[model]
        lines.append(
            f"| {model} | {values['identical']}/{values['n']} = "
            f"{values['identical_pct']:.1%} | "
            f"{values['within_one']}/{values['n']} = "
            f"{values['within_one_pct']:.1%} |"
        )

    (ANALYSIS_DIR / "summary.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print((ANALYSIS_DIR / "summary.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
