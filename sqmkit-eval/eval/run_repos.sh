#!/usr/bin/env bash
# Run the readme/structure/security quality model on all evaluation repositories.
# Usage: ./eval/run_repos.sh OUTPUT_DIR
# The current working directory controls which .env file is loaded.
set -u

OUT_DIR="${1:?usage: run_repos.sh OUTPUT_DIR}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EVAL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$EVAL_ROOT/.." && pwd)"
QUALITY_MODEL="$SCRIPT_DIR/readme-structure-security.json"

SQMKIT="$PROJECT_ROOT/.venv/bin/sqmkit"
if [[ ! -x "$SQMKIT" ]]; then
    SQMKIT="$(command -v sqmkit)" || {
        echo "sqmkit not found; install the package or run 'uv sync'" >&2
        exit 1
    }
fi

mkdir -p "$OUT_DIR" || exit 1

repos=(
    "Smart Village App Backend|https://gitlab.opencode.de/bad-belzig/smart-village-app-mainserver"
    "DKSR Platform|https://gitlab.opencode.de/dksr-gmbh/DKSR-Open-UrbanPulse"
    "Kausal Paths|https://github.com/kausaltech/kausal-paths"
    "EVB-IT Digital|https://gitlab.opencode.de/evb-it/digital/evb-it-digital"
    "BuMaP Core|https://gitlab.opencode.de/bwi/bundesmessenger/admin-portal/bumap-core"
    "CIB seven|https://gitlab.opencode.de/regierung-von-oberbayern/cibseven"
    "Ferienabenteuer|https://gitlab.opencode.de/smart-city-bamberg/ferienabenteuer"
    "Behoerden Klartext Backend|https://gitlab.opencode.de/behoerden-klartext/backend"
    "OCM Open Playground Manager|https://gitlab.opencode.de/open-playground-manager/backend"
    "Mobilitaetsplattform Bamberg|https://gitlab.opencode.de/smart-city-bamberg/mobilitaetsplattform"
)

slugify() {
    printf '%s' "$1" \
        | tr '[:upper:]' '[:lower:]' \
        | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//'
}

for entry in "${repos[@]}"; do
    name="${entry%%|*}"
    url="${entry#*|}"
    slug="$(slugify "$name")"
    local_repo="$SCRIPT_DIR/repos/$slug"
    target="$url"
    if [[ -d "$local_repo" ]]; then
        target="$local_repo"
    fi
    json_file="$OUT_DIR/$slug.json"
    log_file="$OUT_DIR/$slug.log"

    echo "Evaluating: $name ($target)"
    if "$SQMKIT" run --json "$QUALITY_MODEL" "$target" \
        >"$json_file" 2>"$log_file"; then
        echo "  done -> $json_file"
    else
        echo "  finished with errors -> $json_file (log: $log_file)" >&2
    fi
done
