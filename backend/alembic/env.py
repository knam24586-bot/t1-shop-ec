"""Alembic environment; SQLAlchemy models are the schema source of truth."""
from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import settings
from app.db.session import Base
import app.models  # noqa: F401  # Register every model on Base.metadata.


config = context.config
target_metadata = Base.metadata


def _database_url() -> str:
    # A temporary URL can be supplied for migration authoring with:
    # alembic -x database_url=sqlite:///... revision --autogenerate ...
    return context.get_x_argument(as_dictionary=True).get(
        "database_url", settings.database_url
    )


def _include_object(obj, name, object_type, reflected, compare_to):
    # This bookkeeping table lets the initial migration downgrade without
    # deleting tables that existed before Alembic was adopted.
    if object_type == "table" and name == "_t1shop_migration_baseline":
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_database_url(), poolclass=pool.NullPool)
    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
                compare_server_default=True,
                include_object=_include_object,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
