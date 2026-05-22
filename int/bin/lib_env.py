"""
lib_env.py — minimal .env loader (no external dependencies).
Reads the project-root .env file and injects values into os.environ,
skipping keys that are already set in the environment.
"""

import os
from pathlib import Path

# Project root is two directories above this file (int/bin/ → int/ → root)
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def load_dotenv() -> None:
    if not _ENV_PATH.exists():
        return
    with open(_ENV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key   = key.strip()
            value = value.strip().strip('"').strip("'").strip()
            if key and value and key not in os.environ:
                os.environ[key] = value
