"""Apply database migrations and then seed local demo data."""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from app.db.seed import seed_demo_data
from app.db.session import SessionLocal


def main() -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))

    print("Đang nâng cấp schema database bằng Alembic...")
    command.upgrade(config, "head")

    print("Đang thêm dữ liệu mẫu...")
    with SessionLocal.begin() as db:
        seed_demo_data(db)
    print("Khởi tạo database hoàn tất.")


if __name__ == "__main__":
    main()
