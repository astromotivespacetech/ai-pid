param(
    [string]$EnvName = "venv"
)

python -m venv $EnvName

Write-Host "Created virtual environment: $EnvName"
Write-Host "Installing dependencies from requirements.txt..."

& "$EnvName\Scripts\Activate.ps1"
python -m pip install --upgrade pip
pip install -r requirements.txt

Write-Host "Done. To activate the venv later run: .\$EnvName\Scripts\Activate.ps1"
