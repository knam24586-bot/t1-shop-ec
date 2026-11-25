"""Add account identity fields required by registration and JWT sessions."""
from __future__ import annotations

from alembic import op
from sqlalchemy import inspect, text


revision = "0003_auth_identity"
down_revision = "0002_legacy_schema_alignment"
branch_labels = None
depends_on = None
_CHANGE_LOG = "_t1shop_auth_migration_changes"


def _columns(bind, table_name: str) -> set[str]:
    return {column["name"] for column in inspect(bind).get_columns(table_name)}


def _record_change(bind, object_type: str, object_name: str) -> None:
    if _CHANGE_LOG not in inspect(bind).get_table_names():
        bind.execute(
            text(
                f"CREATE TABLE `{_CHANGE_LOG}` ("
                "object_type VARCHAR(20) NOT NULL, "
                "object_name VARCHAR(100) NOT NULL, "
                "PRIMARY KEY (object_type, object_name)) "
                "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
            )
        )
    bind.execute(
        text(
            f"INSERT IGNORE INTO `{_CHANGE_LOG}` "
            "(object_type, object_name) VALUES (:object_type, :object_name)"
        ),
        {"object_type": object_type, "object_name": object_name},
    )


def upgrade() -> None:
    bind = op.get_bind()
    columns = _columns(bind, "users")

    if "phone" not in columns:
        _record_change(bind, "column", "phone")
        bind.execute(text("ALTER TABLE users ADD COLUMN phone VARCHAR(30) NULL"))
    if "token_version" not in columns:
        _record_change(bind, "column", "token_version")
        bind.execute(
            text(
                "ALTER TABLE users ADD COLUMN token_version "
                "INTEGER NOT NULL DEFAULT 0"
            )
        )
    if "store_id" not in columns:
        _record_change(bind, "column", "store_id")
        bind.execute(text("ALTER TABLE users ADD COLUMN store_id INTEGER NULL"))

    duplicates = bind.execute(
        text(
            "SELECT phone, COUNT(*) AS row_count FROM users "
            "WHERE phone IS NOT NULL GROUP BY phone HAVING COUNT(*) > 1 LIMIT 20"
        )
    ).mappings().all()
    if duplicates:
        phones = ", ".join(str(row["phone"]) for row in duplicates)
        raise RuntimeError(
            "Không thể thêm tính duy nhất cho số điện thoại vì dữ liệu cũ bị trùng: "
            f"{phones}. Hãy chuẩn hóa các số điện thoại rồi chạy lại migration."
        )

    inspector = inspect(bind)
    unique_constraints = inspector.get_unique_constraints("users")
    unique_indexes = inspector.get_indexes("users")
    phone_is_unique = any(
        item.get("column_names") == ["phone"]
        for item in unique_constraints
    ) or any(
        item.get("column_names") == ["phone"] and item.get("unique")
        for item in unique_indexes
    )
    if not phone_is_unique:
        _record_change(bind, "unique", "uk_users_phone")
        bind.execute(
            text(
                "ALTER TABLE users ADD CONSTRAINT uk_users_phone UNIQUE (phone)"
            )
        )

    inspector = inspect(bind)
    if not any(index.get("name") == "ix_users_store_id" for index in inspector.get_indexes("users")):
        _record_change(bind, "index", "ix_users_store_id")
        bind.execute(text("CREATE INDEX ix_users_store_id ON users (store_id)"))

    foreign_keys = inspect(bind).get_foreign_keys("users")
    matching_store_fk = any(
        item.get("constrained_columns") == ["store_id"]
        and item.get("referred_table") == "stores"
        and item.get("referred_columns") == ["id"]
        for item in foreign_keys
    )
    if not matching_store_fk:
        if any("store_id" in (item.get("constrained_columns") or ()) for item in foreign_keys):
            raise RuntimeError(
                "users.store_id đang có khóa ngoại khác với stores.id; "
                "hãy kiểm tra schema trước khi chạy lại migration."
            )
        _record_change(bind, "foreign_key", "fk_users_store_id_stores")
        bind.execute(
            text(
                "ALTER TABLE users ADD CONSTRAINT fk_users_store_id_stores "
                "FOREIGN KEY (store_id) REFERENCES stores (id) "
                "ON DELETE SET NULL ON UPDATE CASCADE"
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _CHANGE_LOG not in inspect(bind).get_table_names():
        return

    changes = {
        (row[0], row[1])
        for row in bind.execute(
            text(f"SELECT object_type, object_name FROM `{_CHANGE_LOG}`")
        )
    }
    foreign_keys = {item.get("name") for item in inspect(bind).get_foreign_keys("users")}
    if ("foreign_key", "fk_users_store_id_stores") in changes and "fk_users_store_id_stores" in foreign_keys:
        bind.execute(
            text("ALTER TABLE users DROP FOREIGN KEY `fk_users_store_id_stores`")
        )

    index_names = {item.get("name") for item in inspect(bind).get_indexes("users")}
    if ("index", "ix_users_store_id") in changes and "ix_users_store_id" in index_names:
        bind.execute(text("DROP INDEX ix_users_store_id ON users"))

    unique_names = {item.get("name") for item in inspect(bind).get_unique_constraints("users")}
    if ("unique", "uk_users_phone") in changes and "uk_users_phone" in unique_names:
        bind.execute(text("ALTER TABLE users DROP INDEX `uk_users_phone`"))

    for column in ("store_id", "token_version", "phone"):
        if ("column", column) in changes and column in _columns(bind, "users"):
            bind.execute(text(f"ALTER TABLE users DROP COLUMN `{column}`"))
    bind.execute(text(f"DROP TABLE `{_CHANGE_LOG}`"))
