import os
from pathlib import Path
from dotenv import load_dotenv

_ENV_PATH = Path(__file__).parent.parent / ".env"


def reload():
    load_dotenv(_ENV_PATH, override=True)


def get(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def save(updates: dict[str, str]):
    """Update or create .env, preserving existing keys not in updates."""
    current: dict[str, str] = {}
    if _ENV_PATH.exists():
        with open(_ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    current[k.strip()] = v.strip()
    current.update({k: v for k, v in updates.items() if v})  # skip empty values
    with open(_ENV_PATH, "w", encoding="utf-8") as f:
        for k, v in current.items():
            f.write(f"{k}={v}\n")
    reload()


reload()
