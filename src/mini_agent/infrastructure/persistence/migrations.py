from __future__ import annotations

import re
from pathlib import Path

from alembic import command
from alembic.config import Config

_SCHEMA_PATTERN = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
_PROJECT_ROOT = Path(__file__).resolve().parents[4]


def validate_schema_name(schema: str) -> str:
    if _SCHEMA_PATTERN.fullmatch(schema) is None:
        raise ValueError("database schema must be a safe PostgreSQL identifier")
    return schema


def alembic_config(
    database_url: str,
    *,
    schema: str | None = None,
) -> Config:
    config = Config(str(_PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    config.attributes["database_url"] = database_url
    if schema is not None:
        config.attributes["schema"] = validate_schema_name(schema)
    return config


def upgrade_database_to_head(
    database_url: str,
    *,
    schema: str | None = None,
) -> None:
    command.upgrade(alembic_config(database_url, schema=schema), "head")
