"""Secrets bootstrap — must be imported before anything reads os.environ.

In deployment (App Runner) the whole Secrets Manager JSON blob is injected as a
single env var, APP_SECRETS_JSON. This unpacks it into individual env vars
(DATABASE_URL, ANTHROPIC_API_KEY, BASIC_AUTH_USER, BASIC_AUTH_PASS) so the rest
of the app reads plain env vars exactly as it does locally. Individual env vars
already set win (setdefault), so local dev / tests are unaffected.
"""
from __future__ import annotations

import json
import os


def load_secrets() -> None:
    raw = os.environ.get("APP_SECRETS_JSON")
    if not raw:
        return
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return
    for key, value in data.items():
        if value is not None:
            os.environ.setdefault(key, str(value))


load_secrets()
