#!/usr/bin/env bash
# Clone the evaluation repositories once into eval/repos/.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOS_DIR="$SCRIPT_DIR/repos"
mkdir -p "$REPOS_DIR" || exit 1

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
    dest="$REPOS_DIR/$slug"

    if [[ -d "$dest/.git" ]]; then
        echo "Already cloned: $name -> $dest"
        continue
    fi

    echo "Cloning: $name"
    if GIT_TERMINAL_PROMPT=0 git clone --depth 1 -- "$url" "$dest"; then
        echo "  done -> $dest"
    else
        echo "  clone failed -> $dest" >&2
    fi
done
