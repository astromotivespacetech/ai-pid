# Virtual environment setup

Use the included scripts to create and install dependencies in a virtual environment.

- Windows (PowerShell):

``powershell
.\scripts\setup_env.ps1
```

- macOS / Linux:

```bash
./scripts/setup_env.sh
```

Both scripts accept an optional first argument to name the venv (default: `venv`).

Alternatively, manually run:

```bash
python -m venv venv
# Windows PowerShell
.\venv\Scripts\Activate.ps1
# macOS / Linux
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

This file describes a cross-platform approach for quickly setting up the project's virtual environment.
