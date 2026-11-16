"""Migration script cho bảng carts và cart_items.
Tự động đồng bộ schema (thêm cột status, updated_at, variant_id nếu bảng đã tồn tại từ init.sql,
hoặc tạo mới bảng nếu chưa có). Tuyệt đối không làm thay đổi các file cũ trong sql/.
"""
from __future__ import annotations

import sys
from sqlalchemy import inspect, text

from app.db.session import engine, Base
from app.models.cart import Cart  # noqa: F401
from app.models.cart_item import CartItem  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.variant import ProductVariant  # noqa: F401


def run_migration():
    print("[MIGRATION] Bắt đầu kiểm tra và cập nhật schema cho bảng carts và cart_items...")
    with engine.connect() as conn:
        inspector = inspect(conn)
        existing_tables = inspector.get_table_names()

        # ----------------------------------------------------
        # 1. Bảng product_variants
        # ----------------------------------------------------
        if "product_variants" not in existing_tables:
            print("[MIGRATION] Bảng 'product_variants' chưa tồn tại -> Đang tạo mới qua metadata...")
            Base.metadata.create_all(bind=conn, tables=[ProductVariant.__table__])
            conn.commit()
            print("[MIGRATION] Đã tạo mới bảng 'product_variants' thành công!")

        # ----------------------------------------------------
        # 2. Bảng carts
        # ----------------------------------------------------
        if "carts" not in existing_tables:
            print("[MIGRATION] Bảng 'carts' chưa tồn tại -> Đang tạo mới qua metadata...")
            Base.metadata.create_all(bind=conn, tables=[Cart.__table__])
            conn.commit()
            print("[MIGRATION] Đã tạo mới bảng 'carts' thành công!")
        else:
            columns = [col["name"] for col in inspector.get_columns("carts")]
            if "status" not in columns:
                print("[MIGRATION] Bảng 'carts' thiếu cột 'status' -> Đang chạy ALTER TABLE...")
                conn.execute(
                    text(
                        "ALTER TABLE carts ADD COLUMN status VARCHAR(30) NOT NULL "
                        "DEFAULT 'Active' AFTER user_id;"
                    )
                )
            if "updated_at" not in columns:
                print("[MIGRATION] Bảng 'carts' thiếu cột 'updated_at' -> Đang chạy ALTER TABLE...")
                conn.execute(
                    text(
                        "ALTER TABLE carts ADD COLUMN updated_at DATETIME "
                        "DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER created_at;"
                    )
                )
            conn.commit()

        # ----------------------------------------------------
        # 3. Bảng cart_items
        # ----------------------------------------------------
        if "cart_items" not in existing_tables:
            print("[MIGRATION] Bảng 'cart_items' chưa tồn tại -> Đang tạo mới qua metadata...")
            Base.metadata.create_all(bind=conn, tables=[CartItem.__table__])
            conn.commit()
            print("[MIGRATION] Đã tạo mới bảng 'cart_items' thành công!")
        else:
            columns = [col["name"] for col in inspector.get_columns("cart_items")]
            if "variant_id" not in columns:
                print("[MIGRATION] Bảng 'cart_items' thiếu cột 'variant_id' -> Đang chạy ALTER TABLE...")
                conn.execute(
                    text(
                        "ALTER TABLE cart_items ADD COLUMN variant_id INT NOT NULL AFTER cart_id, "
                        "ADD CONSTRAINT fk_ci_variant FOREIGN KEY (variant_id) "
                        "REFERENCES product_variants (id) ON DELETE CASCADE ON UPDATE CASCADE, "
                        "ADD UNIQUE KEY uk_cart_item_cart_variant (cart_id, variant_id);"
                    )
                )
            conn.commit()

        print("[MIGRATION] Đồng bộ migration cho carts & cart_items hoàn tất thành công!")


if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        print(f"[MIGRATION LỖI] {e}", file=sys.stderr)
        sys.exit(1)
