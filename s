# to run this file and start the bot type: ./s in the terminal. if there is an error, type:  chmod +x s

#!/usr/bin/env bash
set -e

VENV_DIR="$(dirname "$0")/venv"
PYTHON="$VENV_DIR/bin/python"

if [ ! -f "$PYTHON" ]; then
    python3 -m venv "$VENV_DIR"
fi

"$PYTHON" -m pip install -r "$(dirname "$0")/requirements.txt" -q
"$PYTHON" app.py
