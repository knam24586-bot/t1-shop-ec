"""Single database bootstrap and ordered schema-upgrade entry point.

Run from backend/: ``python -m app.db.migrate``.
SQLAlchemy models are the schema source of truth; ``sql/init.sql`` is a generated
MySQL reference snapshot for inspection and is not a second bootstrap path.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.schema import CreateIndex, CreateTable
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import Base, engine
from app.models import (  # noqa: F401
    Cart,
    CartItem,
    Category,
    Item,
    Order,
    OrderItem,
    Payment,
    Product,
    ProductImage,
    ProductVariant,
    Store,
    User,
    Vendor,
    Voucher,
    Wishlist,
)

INITIAL_REVISION = "001_current_models"
LEGACY_REVISION = "002_legacy_cart_and_store_ownership"


def ensure_database_exists() -> None:
    """Create DB_NAME when the configured DB account has permission to do so."""
    server_url = make_url(settings.database_url).set(database=None)
    server_engine = create_engine(server_url, pool_pre_ping=True)
    try:
        with server_engine.begin() as conn:
            exists = conn.execute(
                text(
                    "SELECT 1 FROM INFORMATION_SCHEMA.SCHEMATA "
                    "WHERE SCHEMA_NAME = :database_name"
                ),
                {"database_name": settings.DB_NAME},
            ).first()
            if exists:
                return
            database_name = conn.dialect.identifier_preparer.quote(settings.DB_NAME)
            conn.exec_driver_sql(
                f"CREATE DATABASE {database_name} "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        server_engine.dispose()


def _table_names(conn) -> set[str]:
    return set(inspect(conn).get_table_names())


def _columns(conn, table_name: str) -> set[str]:
    return {column["name"] for column in inspect(conn).get_columns(table_name)}


def _has_foreign_key(conn, table_name: str, column_name: str) -> bool:
    return any(
        column_name in (foreign_key.get("constrained_columns") or [])
        for foreign_key in inspect(conn).get_foreign_keys(table_name)
    )


def _index_exists(conn, table_name: str, columns: list[str], unique: bool = False) -> bool:
    return any(
        (index.get("column_names") or []) == columns
        and (not unique or index.get("unique"))
        for index in inspect(conn).get_indexes(table_name)
    )


def _quoted(conn, identifier: str) -> str:
    return conn.dialect.identifier_preparer.quote(identifier)


def upgrade_legacy_schema(target_engine: Engine = engine) -> None:
    """Make the previous hand-written init.sql schema match current models."""
    with target_engine.begin() as conn:
        tables = _table_names(conn)

        if "users" in tables and "store_id" not in _columns(conn, "users"):
            conn.exec_driver_sql(
                "ALTER TABLE users ADD COLUMN store_id INT NULL AFTER status"
            )
        if "users" in tables:
            if "phone" not in _columns(conn, "users"):
                conn.exec_driver_sql("ALTER TABLE users ADD COLUMN phone VARCHAR(30) NULL AFTER email")
            if not _index_exists(conn, "users", ["store_id"]):
                conn.exec_driver_sql("CREATE INDEX ix_users_store_id ON users (store_id)")
            if not _has_foreign_key(conn, "users", "store_id"):
                conn.exec_driver_sql(
                    "ALTER TABLE users ADD CONSTRAINT fk_users_store "
                    "FOREIGN KEY (store_id) REFERENCES stores (id) "
                    "ON DELETE SET NULL ON UPDATE CASCADE"
                )

        if "products" in tables and "store_id" in _columns(conn, "products"):
            if not _index_exists(conn, "products", ["store_id"]):
                conn.exec_driver_sql(
                    "CREATE INDEX ix_products_store_id ON products (store_id)"
                )
            if not _has_foreign_key(conn, "products", "store_id"):
                conn.exec_driver_sql(
                    "ALTER TABLE products ADD CONSTRAINT fk_products_store "
                    "FOREIGN KEY (store_id) REFERENCES stores (id) "
                    "ON DELETE SET NULL ON UPDATE CASCADE"
                )

        if "carts" in tables:
            columns = _columns(conn, "carts")
            if "status" not in columns:
                conn.exec_driver_sql(
                    "ALTER TABLE carts ADD COLUMN status VARCHAR(30) "
                    "NOT NULL DEFAULT 'Active' AFTER user_id"
                )
            if "updated_at" not in columns:
                conn.exec_driver_sql(
                    "ALTER TABLE carts ADD COLUMN updated_at DATETIME "
                    "NOT NULL DEFAULT CURRENT_TIMESTAMP"
                )

        if "cart_items" in tables:
            columns = _columns(conn, "cart_items")
            if "created_at" not in columns:
                conn.exec_driver_sql(
                    "ALTER TABLE cart_items ADD COLUMN created_at DATETIME "
                    "NOT NULL DEFAULT CURRENT_TIMESTAMP"
                )
            if "updated_at" not in columns:
                conn.exec_driver_sql(
                    "ALTER TABLE cart_items ADD COLUMN updated_at DATETIME "
                    "NOT NULL DEFAULT CURRENT_TIMESTAMP"
                )
            columns = _columns(conn, "cart_items")
            if "variant_id" not in columns:
                conn.exec_driver_sql(
                    "ALTER TABLE cart_items ADD COLUMN variant_id INT NULL AFTER cart_id"
                )
            columns = _columns(conn, "cart_items")
            if "product_id" in columns:
                # Preserve old product-only cart rows by linking each row to an existing
                # variant, creating a legacy variant only if a product has none.
                missing_products = list(conn.execute(
                    text(
                        "SELECT DISTINCT ci.product_id FROM cart_items ci "
                        "LEFT JOIN product_variants pv ON pv.product_id = ci.product_id "
                        "WHERE ci.variant_id IS NULL AND pv.id IS NULL"
                    )
                ).scalars())
                for product_id in missing_products:
                    product_stock = conn.execute(
                        text("SELECT stock FROM products WHERE id = :product_id"),
                        {"product_id": product_id},
                    ).scalar_one_or_none()
                    if product_stock is None:
                        raise RuntimeError(
                            f"Cannot migrate cart item for missing product {product_id}."
                        )
                    conn.execute(
                        text(
                            "INSERT INTO product_variants (product_id, sku, stock) "
                            "VALUES (:product_id, :sku, :stock)"
                        ),
                        {
                            "product_id": product_id,
                            "sku": f"LEGACY-CART-{product_id}-{uuid4().hex[:8].upper()}",
                            "stock": max(int(product_stock), 0),
                        },
                    )
                conn.exec_driver_sql(
                    "UPDATE cart_items ci JOIN product_variants pv "
                    "ON pv.product_id = ci.product_id "
                    "SET ci.variant_id = pv.id WHERE ci.variant_id IS NULL"
                )

            null_variants = conn.execute(
                text("SELECT COUNT(*) FROM cart_items WHERE variant_id IS NULL")
            ).scalar_one()
            if null_variants:
                raise RuntimeError(
                    f"Cannot migrate {null_variants} cart item(s) without a matching product variant."
                )

            # Remove the former product FK and indexes before dropping product_id.
            for foreign_key in inspect(conn).get_foreign_keys("cart_items"):
                if "product_id" in (foreign_key.get("constrained_columns") or []):
                    name = foreign_key.get("name")
                    if name:
                        conn.exec_driver_sql(
                            f"ALTER TABLE cart_items DROP FOREIGN KEY {_quoted(conn, name)}"
                        )
            for index in inspect(conn).get_indexes("cart_items"):
                if "product_id" in (index.get("column_names") or []):
                    name = index.get("name")
                    if name:
                        conn.exec_driver_sql(
                            f"ALTER TABLE cart_items DROP INDEX {_quoted(conn, name)}"
                        )
            if "variant_id" in _columns(conn, "cart_items"):
                conn.exec_driver_sql(
                    "ALTER TABLE cart_items MODIFY COLUMN variant_id INT NOT NULL"
                )
            if "product_id" in _columns(conn, "cart_items"):
                conn.exec_driver_sql("ALTER TABLE cart_items DROP COLUMN product_id")
            if not _index_exists(conn, "cart_items", ["cart_id", "variant_id"], unique=True):
                conn.exec_driver_sql(
                    "CREATE UNIQUE INDEX uk_cart_item_cart_variant "
                    "ON cart_items (cart_id, variant_id)"
                )
            if not _index_exists(conn, "cart_items", ["variant_id"]):
                conn.exec_driver_sql(
                    "CREATE INDEX ix_cart_items_variant_id ON cart_items (variant_id)"
                )
            if not _has_foreign_key(conn, "cart_items", "variant_id"):
                conn.exec_driver_sql(
                    "ALTER TABLE cart_items ADD CONSTRAINT fk_cart_items_variant "
                    "FOREIGN KEY (variant_id) REFERENCES product_variants (id) "
                    "ON DELETE CASCADE ON UPDATE CASCADE"
                )

        if "products" in tables and "product_variants" in tables:
            conn.exec_driver_sql(
                "UPDATE products p SET p.stock = ("
                "SELECT COALESCE(SUM(pv.stock), 0) FROM product_variants pv "
                "WHERE pv.product_id = p.id) "
                "WHERE EXISTS (SELECT 1 FROM product_variants pv WHERE pv.product_id = p.id)"
            )

        if "orders" in tables and "updated_at" not in _columns(conn, "orders"):
            conn.exec_driver_sql(
                "ALTER TABLE orders ADD COLUMN updated_at DATETIME "
                "NOT NULL DEFAULT CURRENT_TIMESTAMP"
            )

        if "order_items" in tables:
            if "variant_id" not in _columns(conn, "order_items"):
                conn.exec_driver_sql(
                    "ALTER TABLE order_items ADD COLUMN variant_id INT NULL AFTER order_id"
                )
            if not _has_foreign_key(conn, "order_items", "variant_id"):
                conn.exec_driver_sql(
                    "ALTER TABLE order_items ADD CONSTRAINT fk_order_items_variant "
                    "FOREIGN KEY (variant_id) REFERENCES product_variants (id) "
                    "ON DELETE SET NULL ON UPDATE CASCADE"
                )


def _create_revision_table() -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "revision VARCHAR(64) NOT NULL PRIMARY KEY, "
            "applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
        )


def _applied_revisions() -> set[str]:
    with engine.connect() as conn:
        return set(conn.execute(text("SELECT revision FROM schema_migrations")).scalars())


def _record_revision(revision: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO schema_migrations (revision) VALUES (:revision)"),
            {"revision": revision},
        )


def _seed_demo_catalog() -> None:
    with Session(engine) as db:
        category = db.scalar(select(Category).where(Category.slug == "t1-demo"))
        if category is None:
            category = Category(name="T1 Shop", slug="t1-demo", status="Active")
            db.add(category)
            db.flush()

        product = db.scalar(select(Product).where(Product.slug == "t1-demo-hoodie"))
        if product is None:
            product = Product(
                category_id=category.id,
                name="T1 Shop Hoodie",
                slug="t1-demo-hoodie",
                description="Sản phẩm mẫu để trải nghiệm luồng giỏ hàng và thanh toán COD.",
                price="499000.00",
                rating="5.0",
                stock=25,
                image_url="https://images.unsplash.com/photo-1556821840-3a63f95609a7?auto=format&fit=crop&w=700&q=80",
                status="Published",
            )
            product.variants = [
                ProductVariant(sku="T1-DEMO-HOODIE-001", color="Black", size="M", stock=25)
            ]
            db.add(product)
        elif not product.variants:
            product.variants.append(
                ProductVariant(
                    sku="T1-DEMO-HOODIE-001",
                    color="Black",
                    size="M",
                    stock=max(product.stock, 0),
                )
            )

        email = settings.BOOTSTRAP_ADMIN_EMAIL.strip().lower()
        password = settings.BOOTSTRAP_ADMIN_PASSWORD
        if email and password:
            if len(password) < 12:
                raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD must contain at least 12 characters.")
            existing_admin = db.scalar(select(User).where(User.email == email))
            if existing_admin is None:
                db.add(
                    User(
                        full_name=settings.BOOTSTRAP_ADMIN_NAME.strip() or "T1 Shop Admin",
                        email=email,
                        password_hash=hash_password(password),
                        role="ADMIN",
                        status="Active",
                    )
                )
        db.commit()


def run_migrations() -> None:
    ensure_database_exists()
    _create_revision_table()
    applied = _applied_revisions()
    if INITIAL_REVISION not in applied:
        Base.metadata.create_all(bind=engine)
        _record_revision(INITIAL_REVISION)
        print(f"[DB] Applied {INITIAL_REVISION}.")
    if LEGACY_REVISION not in applied:
        upgrade_legacy_schema()
        _record_revision(LEGACY_REVISION)
        print(f"[DB] Applied {LEGACY_REVISION}.")
    _seed_demo_catalog()
    print(f"[DB] Schema ready: {settings.DB_NAME}.")


def write_schema_snapshot() -> Path:
    """Write the review-only SQL snapshot from the mapped model metadata."""
    target = Path(__file__).resolve().parents[2] / "sql" / "init.sql"
    dialect = mysql.dialect()
    statements = [
        "-- Generated from app.models metadata. Do not run separately; use python -m app.db.migrate.",
        f"CREATE DATABASE IF NOT EXISTS `{settings.DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;",
        f"USE `{settings.DB_NAME}`;",
        "CREATE TABLE IF NOT EXISTS schema_migrations (revision VARCHAR(64) NOT NULL PRIMARY KEY, applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;",
    ]
    for table in Base.metadata.sorted_tables:
        create_table = str(CreateTable(table).compile(dialect=dialect)).strip()
        create_table = "\n".join(line.rstrip() for line in create_table.splitlines())
        statements.append(create_table + ";")
        for index in sorted(table.indexes, key=lambda item: item.name or ""):
            statements.append(str(CreateIndex(index).compile(dialect=dialect)).strip() + ";")
    statements.extend(
        [
            "INSERT INTO categories (name, slug, status) VALUES ('T1 Shop', 't1-demo', 'Active') ON DUPLICATE KEY UPDATE name = VALUES(name);",
            "INSERT INTO products (category_id, name, slug, description, price, rating, stock, image_url, status) SELECT id, 'T1 Shop Hoodie', 't1-demo-hoodie', 'Sản phẩm mẫu để trải nghiệm luồng giỏ hàng và thanh toán COD.', 499000.00, 5.0, 25, 'https://images.unsplash.com/photo-1556821840-3a63f95609a7?auto=format&fit=crop&w=700&q=80', 'Published' FROM categories WHERE slug = 't1-demo' ON DUPLICATE KEY UPDATE name = VALUES(name);",
            "INSERT INTO product_variants (product_id, sku, color, size, stock) SELECT id, 'T1-DEMO-HOODIE-001', 'Black', 'M', 25 FROM products WHERE slug = 't1-demo-hoodie' ON DUPLICATE KEY UPDATE sku = VALUES(sku);",
            "",
        ]
    )
    target.write_text("\n\n".join(statements).rstrip() + "\n", encoding="utf-8")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize or upgrade the T1 Shop database.")
    parser.add_argument(
        "--write-sql",
        action="store_true",
        help="Regenerate sql/init.sql as a reference snapshot from current ORM models.",
    )
    args = parser.parse_args()
    if args.write_sql:
        print(f"[DB] Wrote model snapshot to {write_schema_snapshot()}.")
    else:
        run_migrations()
