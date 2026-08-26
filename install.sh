#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/Parteicoder/Asset.git"
DIR="${1:-Asset}"

command -v git >/dev/null || { echo "git fehlt. Bitte installieren: https://git-scm.com"; exit 1; }
command -v python3 >/dev/null || { echo "python3 fehlt. Bitte installieren: https://python.org"; exit 1; }

if [ -d "$DIR/.git" ]; then
  echo "Verzeichnis '$DIR' existiert bereits. Zum Aktualisieren: cd $DIR && ./update.sh"
  exit 1
fi

git clone "$REPO_URL" "$DIR"
cd "$DIR"
python3 scripts/selbsttest.py

echo
echo "Installiert nach $DIR."
echo "Daten sammeln: cd $DIR && python3 scripts/sammeln.py --land NN"
