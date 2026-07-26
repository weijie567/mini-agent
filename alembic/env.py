from __future__ import annotations

import os
import re
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.schema import CreateSchema

from mini_agent.infrastructure.persistence.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
_SCHEMA_PATTERN = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _database_url() -> str:
    return os.environ.get(
        "MINI_AGENT_DATABASE_URL",
        config.get_main_option("sqlalchemy.url"),
    )


def _schema_name() -> str | None:
    configured = config.attributes.get("schema")
    if configured is None:
        configured = os.environ.get("MINI_AGENT_DB_SCHEMA")
    if configured is None or configured == "":
        return None
    if not isinstance(configured, str) or _SCHEMA_PATTERN.fullmatch(configured) is None:
        raise ValueError("database schema must be a safe PostgreSQL identifier")
    return configured


def run_migrations_offline() -> None:
    schema = _schema_name()
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        version_table_schema=schema,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    schema = _schema_name()

    with connectable.connect() as connection:
        if schema is not None:
            connection.execute(CreateSchema(schema, if_not_exists=True))
            connection.commit()
            connection.exec_driver_sql(f'SET search_path TO "{schema}", public')
            connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            version_table_schema=schema,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
