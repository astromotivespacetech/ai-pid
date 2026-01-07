#!/usr/bin/env bash
set -e

ENV_NAME="${1:-venv}"

python3 -m venv "$ENV_NAME"
echo "Created virtual environment: $ENV_NAME"
echo "Installing dependencies from requirements.txt..."

source "$ENV_NAME/bin/activate"
python -m pip install --upgrade pip
pip install -r requirements.txt

echo "Done. Activate with: source $ENV_NAME/bin/activate"
