"""Backward-compatible entry point for the unified database migrator."""
from app.db.migrate import run_migrations

run_migration = run_migrations


if __name__ == "__main__":
    run_migrations()
