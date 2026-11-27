"""Bring legacy SQL/Workbench tables up to the current model schema.

Legacy cart rows stored a product ID, while the current model stores a variant
ID. Rows are converted only when the product has exactly one defensible
variant. Ambiguous rows stop the migration and retain product_id for an
operator to choose the correct variant explicitly.
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import inspect, text


revision = "0002_legacy_schema_alignment"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

_CHANGE_LOG = "_t1shop_legacy_schema_changes"


def _quote(identifier: str) -> str:
    return "`" + identifier.replace("`", "``") + "`"


def _columns(bind, table_name: str) -> set[str]:
    return {column["name"] for column in inspect(bind).get_columns(table_name)}


def _record_added_column(bind, table_name: str, column_name: str) -> None:
    names = set(inspect(bind).get_table_names())
    if _CHANGE_LOG not in names:
        bind.execute(
            text(
                f"CREATE TABLE {_quote(_CHANGE_LOG)} ("
                "table_name VARCHAR(64) NOT NULL, "
                "column_name VARCHAR(64) NOT NULL, "
                "PRIMARY KEY (table_name, column_name)) "
                "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
            )
        )
    bind.execute(
        text(
            f"INSERT IGNORE INTO {_quote(_CHANGE_LOG)} "
            "(table_name, column_name) VALUES (:table_name, :column_name)"
        ),
        {"table_name": table_name, "column_name": column_name},
    )


def _add_column(bind, table_name: str, column_name: str, definition: str) -> None:
    if column_name in _columns(bind, table_name):
        return
    # Record first: MySQL implicitly commits the marker when ALTER TABLE runs.
    # If a later data check stops the migration, downgrade still knows which
    # columns were introduced by this revision.
    _record_added_column(bind, table_name, column_name)
    bind.execute(
        text(
            f"ALTER TABLE {_quote(table_name)} ADD COLUMN "
            f"{_quote(column_name)} {definition}"
        )
    )


def _ensure_index(bind, table_name: str, index_name: str, columns: tuple[str, ...]) -> None:
    if not set(columns).issubset(_columns(bind, table_name)):
        return
    indexes = inspect(bind).get_indexes(table_name)
    if any(index.get("name") == index_name for index in indexes):
        return
    column_sql = ", ".join(_quote(column) for column in columns)
    bind.execute(
        text(
            f"CREATE INDEX {_quote(index_name)} ON {_quote(table_name)} "
            f"({column_sql})"
        )
    )


def _has_unique_columns(bind, table_name: str, columns: tuple[str, ...]) -> bool:
    expected = set(columns)
    inspector = inspect(bind)
    constraints = inspector.get_unique_constraints(table_name)
    indexes = inspector.get_indexes(table_name)
    return any(
        set(item.get("column_names") or ()) == expected
        for item in [*constraints, *indexes]
        if item in constraints or item.get("unique") is True
    )


def _ensure_unique(bind, table_name: str, constraint_name: str, columns: tuple[str, ...]) -> None:
    if _has_unique_columns(bind, table_name, columns):
        return
    column_sql = ", ".join(_quote(column) for column in columns)
    bind.execute(
        text(
            f"ALTER TABLE {_quote(table_name)} ADD CONSTRAINT "
            f"{_quote(constraint_name)} UNIQUE ({column_sql})"
        )
    )


def _ensure_foreign_key(
    bind,
    table_name: str,
    column_name: str,
    referred_table: str,
    referred_column: str,
    constraint_name: str,
    ondelete: str,
) -> None:
    foreign_keys = inspect(bind).get_foreign_keys(table_name)
    for foreign_key in foreign_keys:
        if column_name in (foreign_key.get("constrained_columns") or ()):
            if (
                foreign_key.get("referred_table") == referred_table
                and foreign_key.get("referred_columns") == [referred_column]
            ):
                return
            raise RuntimeError(
                f"{table_name}.{column_name} đã có khóa ngoại không tương thích; "
                "hãy kiểm tra schema trước khi chạy lại migration."
            )
    bind.execute(
        text(
            f"ALTER TABLE {_quote(table_name)} ADD CONSTRAINT "
            f"{_quote(constraint_name)} FOREIGN KEY ({_quote(column_name)}) "
            f"REFERENCES {_quote(referred_table)} ({_quote(referred_column)}) "
            f"ON DELETE {ondelete} ON UPDATE CASCADE"
        )
    )


def _variant_ids_by_product(bind, product_id: int) -> list[dict]:
    return list(
        bind.execute(
            text(
                "SELECT id, color, size FROM product_variants "
                "WHERE product_id = :product_id ORDER BY id"
            ),
            {"product_id": product_id},
        ).mappings()
    )


def _choose_variant(variants: list[dict]) -> int | None:
    if len(variants) == 1:
        return int(variants[0]["id"])
    generic = [
        variant
        for variant in variants
        if variant["color"] is None and variant["size"] is None
    ]
    if len(generic) == 1:
        return int(generic[0]["id"])
    return None


def _create_legacy_variant(bind, product_id: int) -> int:
    sku = f"LEGACY-P{product_id}"
    existing = bind.execute(
        text("SELECT id, product_id FROM product_variants WHERE sku = :sku"),
        {"sku": sku},
    ).mappings().first()
    if existing:
        if int(existing["product_id"]) != product_id:
            raise RuntimeError(
                f"SKU {sku} đã được dùng cho sản phẩm khác; không thể tạo biến thể chuyển đổi."
            )
        return int(existing["id"])

    product = bind.execute(
        text("SELECT stock FROM products WHERE id = :product_id"),
        {"product_id": product_id},
    ).mappings().first()
    if product is None:
        raise RuntimeError(
            f"Không tìm thấy products.id={product_id} khi chuyển dữ liệu giỏ hàng."
        )
    bind.execute(
        text(
            "INSERT INTO product_variants "
            "(product_id, sku, color, size, stock) "
            "VALUES (:product_id, :sku, NULL, NULL, :stock)"
        ),
        {
            "product_id": product_id,
            "sku": sku,
            "stock": max(int(product["stock"] or 0), 0),
        },
    )
    return int(
        bind.execute(
            text("SELECT id FROM product_variants WHERE sku = :sku"),
            {"sku": sku},
        ).scalar_one()
    )


def _migrate_cart_items(bind) -> None:
    columns = _columns(bind, "cart_items")
    legacy_product_column = "product_id" in columns

    _add_column(bind, "cart_items", "variant_id", "INTEGER NULL")
    _add_column(
        bind,
        "cart_items",
        "created_at",
        "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP",
    )
    _add_column(
        bind,
        "cart_items",
        "updated_at",
        "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP",
    )

    if legacy_product_column:
        rows = list(
            bind.execute(
                text(
                    "SELECT id, product_id FROM cart_items "
                    "WHERE variant_id IS NULL ORDER BY id"
                )
            ).mappings()
        )
        ambiguous: list[tuple[int, int]] = []
        for row in rows:
            product_id = int(row["product_id"])
            variants = _variant_ids_by_product(bind, product_id)
            if not variants:
                variant_id = _create_legacy_variant(bind, product_id)
            else:
                variant_id = _choose_variant(variants)
                if variant_id is None:
                    ambiguous.append((int(row["id"]), product_id))
                    continue
            bind.execute(
                text("UPDATE cart_items SET variant_id = :variant_id WHERE id = :id"),
                {"variant_id": variant_id, "id": int(row["id"])},
            )

        mismatched = list(
            bind.execute(
                text(
                    "SELECT ci.id, ci.product_id, pv.product_id AS variant_product_id "
                    "FROM cart_items AS ci JOIN product_variants AS pv "
                    "ON pv.id = ci.variant_id "
                    "WHERE ci.product_id <> pv.product_id LIMIT 20"
                )
            ).mappings()
        )
        if mismatched:
            detail = ", ".join(
                f"item {row['id']} (product {row['product_id']}, variant product "
                f"{row['variant_product_id']})"
                for row in mismatched
            )
            raise RuntimeError(
                "Dừng migration: các cart_items có product_id không khớp variant_id: "
                f"{detail}. Hãy sửa variant_id theo đúng sản phẩm rồi chạy lại."
            )
        if ambiguous:
            detail = ", ".join(
                f"cart_item_id={item_id}, product_id={product_id}"
                for item_id, product_id in ambiguous
            )
            raise RuntimeError(
                "Dừng migration để tránh gán nhầm biến thể cho giỏ hàng cũ. "
                f"Các dòng cần chọn variant_id: {detail}. Cập nhật từng dòng bằng "
                "variant_id thuộc đúng product_id, sau đó chạy lại bootstrap. "
                "product_id cũ vẫn được giữ nguyên cho tới khi chuyển đổi hoàn tất."
            )

    invalid_quantity = bind.execute(
        text("SELECT id, quantity FROM cart_items WHERE quantity <= 0 LIMIT 20")
    ).mappings().all()
    if invalid_quantity:
        detail = ", ".join(
            f"id={row['id']}, quantity={row['quantity']}" for row in invalid_quantity
        )
        raise RuntimeError(
            "Không thể bật ràng buộc quantity > 0 cho cart_items. "
            f"Hãy sửa các dòng: {detail}."
        )

    missing_variant = bind.execute(
        text("SELECT id FROM cart_items WHERE variant_id IS NULL LIMIT 20")
    ).scalars().all()
    if missing_variant:
        raise RuntimeError(
            "Không thể hoàn tất migration: một số cart_items chưa có variant_id "
            f"(IDs: {', '.join(map(str, missing_variant))})."
        )

    duplicate_variants = bind.execute(
        text(
            "SELECT cart_id, variant_id, COUNT(*) AS row_count "
            "FROM cart_items GROUP BY cart_id, variant_id HAVING COUNT(*) > 1 LIMIT 20"
        )
    ).mappings().all()
    if duplicate_variants:
        detail = "; ".join(
            f"cart_id={row['cart_id']}, variant_id={row['variant_id']}, "
            f"rows={row['row_count']}"
            for row in duplicate_variants
        )
        raise RuntimeError(
            "Không thể tạo ràng buộc mỗi biến thể chỉ xuất hiện một lần trong giỏ. "
            f"Hãy gộp các dòng trùng trước khi chạy lại: {detail}."
        )

    bind.execute(
        text(
            "UPDATE cart_items SET created_at = CURRENT_TIMESTAMP "
            "WHERE created_at IS NULL"
        )
    )
    bind.execute(
        text(
            "UPDATE cart_items SET updated_at = CURRENT_TIMESTAMP "
            "WHERE updated_at IS NULL"
        )
    )
    bind.execute(
        text("ALTER TABLE cart_items MODIFY COLUMN variant_id INTEGER NOT NULL")
    )

    if legacy_product_column:
        for foreign_key in inspect(bind).get_foreign_keys("cart_items"):
            if "product_id" in (foreign_key.get("constrained_columns") or ()):
                name = foreign_key.get("name")
                if name:
                    bind.execute(
                        text(
                            f"ALTER TABLE cart_items DROP FOREIGN KEY {_quote(name)}"
                        )
                    )
        for index in inspect(bind).get_indexes("cart_items"):
            if "product_id" in (index.get("column_names") or ()):
                name = index.get("name")
                if name and name != "PRIMARY":
                    bind.execute(
                        text(f"ALTER TABLE cart_items DROP INDEX {_quote(name)}")
                    )
        bind.execute(text("ALTER TABLE cart_items DROP COLUMN product_id"))

    _ensure_foreign_key(
        bind,
        "cart_items",
        "variant_id",
        "product_variants",
        "id",
        "fk_cart_items_variant_id_product_variants",
        "CASCADE",
    )
    _ensure_unique(
        bind,
        "cart_items",
        "uk_cart_item_cart_variant",
        ("cart_id", "variant_id"),
    )
    _ensure_index(bind, "cart_items", "ix_cart_items_variant_id", ("variant_id",))
    checks = inspect(bind).get_check_constraints("cart_items")
    if not any(
        "quantity" in str(check.get("sqltext", "")).lower()
        and "> 0" in str(check.get("sqltext", ""))
        for check in checks
    ):
        bind.execute(
            text(
                "ALTER TABLE cart_items ADD CONSTRAINT "
                "ck_cart_items_quantity_positive CHECK (quantity > 0)"
            )
        )


def _align_order_items(bind) -> None:
    columns = _columns(bind, "order_items")
    if "variant_id" not in columns:
        _add_column(bind, "order_items", "variant_id", "INTEGER NULL")
        columns.add("variant_id")

    if "product_id" in columns:
        rows = list(
            bind.execute(
                text(
                    "SELECT id, product_id FROM order_items "
                    "WHERE variant_id IS NULL AND product_id IS NOT NULL ORDER BY id"
                )
            ).mappings()
        )
        for row in rows:
            variants = _variant_ids_by_product(bind, int(row["product_id"]))
            variant_id = _choose_variant(variants)
            if variant_id is not None:
                bind.execute(
                    text("UPDATE order_items SET variant_id = :variant_id WHERE id = :id"),
                    {"variant_id": variant_id, "id": int(row["id"])},
                )

    _ensure_foreign_key(
        bind,
        "order_items",
        "variant_id",
        "product_variants",
        "id",
        "fk_order_items_variant_id_product_variants",
        "SET NULL",
    )
    _ensure_index(bind, "order_items", "ix_order_items_variant_id", ("variant_id",))

    invalid = bind.execute(
        text(
            "SELECT id FROM order_items "
            "WHERE quantity <= 0 OR unit_price < 0 OR line_total < 0 LIMIT 20"
        )
    ).scalars().all()
    if invalid:
        raise RuntimeError(
            "Không thể bật các ràng buộc số lượng/giá cho order_items. "
            f"Hãy kiểm tra các dòng ID: {', '.join(map(str, invalid))}."
        )
    checks = inspect(bind).get_check_constraints("order_items")
    existing_sql = " ".join(str(check.get("sqltext", "")).lower() for check in checks)
    required = (
        ("ck_order_items_quantity_positive", "quantity > 0"),
        ("ck_order_items_unit_price_nonnegative", "unit_price >= 0"),
        ("ck_order_items_line_total_nonnegative", "line_total >= 0"),
    )
    for constraint_name, expression in required:
        if expression not in existing_sql:
            bind.execute(
                text(
                    f"ALTER TABLE order_items ADD CONSTRAINT "
                    f"{_quote(constraint_name)} CHECK ({expression})"
                )
            )
            existing_sql += " " + expression


def upgrade() -> None:
    bind = op.get_bind()
    table_names = set(inspect(bind).get_table_names())

    if "carts" in table_names:
        _add_column(
            bind,
            "carts",
            "status",
            "VARCHAR(30) NOT NULL DEFAULT 'Active'",
        )
        _add_column(
            bind,
            "carts",
            "updated_at",
            "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP",
        )
        bind.execute(
            text(
                "UPDATE carts SET updated_at = CURRENT_TIMESTAMP "
                "WHERE updated_at IS NULL"
            )
        )
    if "orders" in table_names:
        _add_column(
            bind,
            "orders",
            "updated_at",
            "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP",
        )
        bind.execute(
            text(
                "UPDATE orders SET updated_at = CURRENT_TIMESTAMP "
                "WHERE updated_at IS NULL"
            )
        )
    if "cart_items" in table_names:
        _migrate_cart_items(bind)
    if "order_items" in table_names:
        _align_order_items(bind)


def downgrade() -> None:
    """Do not silently discard cart variant choices when reversing this revision."""
    bind = op.get_bind()
    names = set(inspect(bind).get_table_names())
    logged_columns: set[tuple[str, str]] = set()
    if _CHANGE_LOG in names:
        logged_columns = {
            (row[0], row[1])
            for row in bind.execute(
                text(
                    f"SELECT table_name, column_name FROM {_quote(_CHANGE_LOG)}"
                )
            )
        }
    legacy_cart_conversion = ("cart_items", "variant_id") in logged_columns

    if (
        legacy_cart_conversion
        and "cart_items" in names
        and "product_id" not in _columns(bind, "cart_items")
    ):
        unconvertible = bind.execute(
            text(
                "SELECT ci.id FROM cart_items AS ci "
                "LEFT JOIN product_variants AS pv ON pv.id = ci.variant_id "
                "WHERE pv.id IS NULL LIMIT 20"
            )
        ).scalars().all()
        if unconvertible:
            raise RuntimeError(
                "Không thể hoàn tác vì không tìm thấy biến thể cho các dòng giỏ hàng: "
                f"{', '.join(map(str, unconvertible))}."
            )
        duplicates = bind.execute(
            text(
                "SELECT ci.cart_id, pv.product_id "
                "FROM cart_items AS ci JOIN product_variants AS pv "
                "ON pv.id = ci.variant_id "
                "GROUP BY ci.cart_id, pv.product_id HAVING COUNT(*) > 1 LIMIT 20"
            )
        ).all()
        if duplicates:
            raise RuntimeError(
                "Không thể hoàn tác: một cart có nhiều biến thể thuộc cùng sản phẩm; "
                "schema cũ chỉ cho phép một dòng mỗi sản phẩm."
            )
        bind.execute(
            text("ALTER TABLE cart_items ADD COLUMN product_id INTEGER NULL")
        )
        bind.execute(
            text(
                "UPDATE cart_items AS ci JOIN product_variants AS pv "
                "ON pv.id = ci.variant_id SET ci.product_id = pv.product_id"
            )
        )
        missing = bind.execute(
            text("SELECT id FROM cart_items WHERE product_id IS NULL LIMIT 20")
        ).scalars().all()
        if missing:
            raise RuntimeError(
                "Không thể hoàn tác cart_items vì không truy ra product_id cho các "
                f"dòng: {', '.join(map(str, missing))}."
            )
        for foreign_key in inspect(bind).get_foreign_keys("cart_items"):
            if "variant_id" in (foreign_key.get("constrained_columns") or ()):
                name = foreign_key.get("name")
                if name:
                    bind.execute(
                        text(f"ALTER TABLE cart_items DROP FOREIGN KEY {_quote(name)}")
                    )
        for index in inspect(bind).get_indexes("cart_items"):
            if "variant_id" in (index.get("column_names") or ()):
                name = index.get("name")
                if name:
                    bind.execute(
                        text(f"ALTER TABLE cart_items DROP INDEX {_quote(name)}")
                    )
        for unique in inspect(bind).get_unique_constraints("cart_items"):
            if set(unique.get("column_names") or ()) == {"cart_id", "variant_id"}:
                name = unique.get("name")
                if name:
                    bind.execute(
                        text(f"ALTER TABLE cart_items DROP INDEX {_quote(name)}")
                    )
        checks = inspect(bind).get_check_constraints("cart_items")
        for check in checks:
            if "quantity" in str(check.get("sqltext", "")).lower():
                name = check.get("name")
                if name:
                    bind.execute(
                        text(f"ALTER TABLE cart_items DROP CHECK {_quote(name)}")
                    )
        bind.execute(
            text("ALTER TABLE cart_items MODIFY COLUMN product_id INTEGER NOT NULL")
        )
        bind.execute(
            text(
                "ALTER TABLE cart_items ADD CONSTRAINT fk_ci_product "
                "FOREIGN KEY (product_id) REFERENCES products (id) "
                "ON DELETE CASCADE ON UPDATE CASCADE"
            )
        )
        bind.execute(
            text(
                "ALTER TABLE cart_items ADD CONSTRAINT uk_cart_product "
                "UNIQUE (cart_id, product_id)"
            )
        )
        bind.execute(text("ALTER TABLE cart_items DROP COLUMN variant_id"))

    if ("order_items", "variant_id") in logged_columns and "order_items" in names:
        for foreign_key in inspect(bind).get_foreign_keys("order_items"):
            if "variant_id" in (foreign_key.get("constrained_columns") or ()):
                name = foreign_key.get("name")
                if name:
                    bind.execute(
                        text(f"ALTER TABLE order_items DROP FOREIGN KEY {_quote(name)}")
                    )

    if _CHANGE_LOG in names:
        changes = list(
            bind.execute(
                text(
                    f"SELECT table_name, column_name FROM {_quote(_CHANGE_LOG)} "
                    "ORDER BY table_name, column_name"
                )
            ).mappings()
        )
        for change in changes:
            table_name = change["table_name"]
            column_name = change["column_name"]
            if table_name in set(inspect(bind).get_table_names()) and column_name in _columns(
                bind, table_name
            ):
                bind.execute(
                    text(
                        f"ALTER TABLE {_quote(table_name)} DROP COLUMN "
                        f"{_quote(column_name)}"
                    )
                )
        bind.execute(text(f"DROP TABLE {_quote(_CHANGE_LOG)}"))
