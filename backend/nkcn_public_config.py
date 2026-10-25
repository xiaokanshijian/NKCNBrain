"""Runtime configuration for the public distribution. Never stores credentials."""
import os
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

def secret(name):
    """Empty means unconfigured; never use hardcoded key fallbacks."""
    return os.environ.get(name, "").strip()

def required(name):
    value = secret(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value

def endpoint(name, default):
    return os.environ.get(name, "").strip() or default

def redact(value):
    if isinstance(value, dict):
        return {k: ("[redacted]" if re.search(r"(?i)(api.?key|secret|password|token)", k)
                    else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value

def validate_public_config(value):
    """Persist references, never credentials, in tracked model definitions."""
    if isinstance(value, dict):
        for key, item in value.items():
            if re.search(r"(?i)(api.?key|api.?secret|secret.?key|password|access.?token)", key):
                if isinstance(item, str) and item and not re.fullmatch(r"env:[A-Z_][A-Z0-9_]*", item):
                    raise ValueError(f"{key} must use an env:VARIABLE reference")
            validate_public_config(item)
    elif isinstance(value, list):
        for item in value:
            validate_public_config(item)
