import json
import os
import pathlib

import psycopg
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://hackathon:hackathon@localhost:5432/hotel_hackathon"
)


@pytest.fixture(scope="session")
def db():
    with psycopg.connect(DATABASE_URL) as conn:
        yield conn


@pytest.fixture(scope="session")
def scrape_manifest():
    return json.loads((ROOT / "etl" / "SCRAPE_MANIFEST.json").read_text())


@pytest.fixture(scope="session")
def load_proof():
    return json.loads((ROOT / "etl" / "LOAD_PROOF.json").read_text())
