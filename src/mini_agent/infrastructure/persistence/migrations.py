from __future__ import annotations

import re
from pathlib import Path

from alembic import command
from alembic.config import Config

from mini_agent.infrastructure.persistence.database import (
    test_database_connect_args,
)

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
    testing: bool = False,
) -> Config:
    if testing:
        test_database_connect_args(database_url)
    config = Config(str(_PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    config.attributes["database_url"] = database_url
    config.attributes["testing"] = testing
    if schema is not None:
        config.attributes["schema"] = validate_schema_name(schema)
    return config


def upgrade_database_to_head(
    database_url: str,
    *,
    schema: str | None = None,
    testing: bool = False,
) -> None:
    command.upgrade(
        alembic_config(database_url, schema=schema, testing=testing),
        "head",
    )
