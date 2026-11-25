"""Initial database schema from the SQLAlchemy models.

The revision is conditional so existing databases can be adopted without
dropping their tables. Existing legacy tables are reconciled in the next
revision. Do not edit this snapshot after it has been applied.
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import inspect, text


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

_TRACKER = "_t1shop_migration_baseline"
_TABLE_NAMES = ['categories',
 'items',
 'payment_webhook_logs',
 'users',
 'vendors',
 'vouchers',
 'carts',
 'orders',
 'products',
 'stores',
 'order_cancellations',
 'order_status_histories',
 'payments',
 'product_images',
 'product_variants',
 'store_orders',
 'wishlists',
 'cart_items',
 'inventory_movements',
 'order_items']
_TABLE_DDL = {'categories': 'CREATE TABLE IF NOT EXISTS categories (\n'
               '\tid INTEGER NOT NULL AUTO_INCREMENT, \n'
               '\tname VARCHAR(150) NOT NULL, \n'
               '\tslug VARCHAR(150) NOT NULL, \n'
               "\tstatus VARCHAR(30) NOT NULL DEFAULT 'Active', \n"
               '\tparent_id INTEGER, \n'
               '\tcreated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, \n'
               '\tPRIMARY KEY (id), \n'
               '\tUNIQUE (slug), \n'
               '\tFOREIGN KEY(parent_id) REFERENCES categories (id) ON DELETE RESTRICT '
               'ON UPDATE CASCADE\n'
               ')ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci',
 'items': 'CREATE TABLE IF NOT EXISTS items (\n'
          '\tid INTEGER NOT NULL AUTO_INCREMENT, \n'
          '\tname VARCHAR(150) NOT NULL, \n'
          '\tdescription TEXT, \n'
          '\tprice NUMERIC(12, 2) NOT NULL, \n'
          '\tcreated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, \n'
          '\tPRIMARY KEY (id)\n'
          ')ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci',
 'payment_webhook_logs': 'CREATE TABLE IF NOT EXISTS payment_webhook_logs (\n'
                         '\tid INTEGER NOT NULL AUTO_INCREMENT, \n'
                         '\ttransaction_reference VARCHAR(100) NOT NULL, \n'
                         '\tgateway VARCHAR(50) NOT NULL, \n'
                         '\traw_payload TEXT NOT NULL, \n'
                         '\tis_valid_signature BOOL NOT NULL, \n'
                         '\tresponse_code VARCHAR(20), \n'
                         '\tmessage VARCHAR(255) NOT NULL, \n'
                         '\tip_address VARCHAR(50), \n'
                         '\tcreated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, \n'
                         '\tPRIMARY KEY (id)\n'
                         ')ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci',
 'users': 'CREATE TABLE IF NOT EXISTS users (\n'
          '\tid INTEGER NOT NULL AUTO_INCREMENT, \n'
          '\tfull_name VARCHAR(150) NOT NULL, \n'
          '\temail VARCHAR(255) NOT NULL, \n'
          '\tpassword_hash VARCHAR(255) NOT NULL, \n'
          "\t`role` VARCHAR(50) NOT NULL DEFAULT 'CUSTOMER', \n"
          "\tstatus VARCHAR(30) NOT NULL DEFAULT 'Active', \n"
          '\tcreated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, \n'
          '\tPRIMARY KEY (id), \n'
          '\tUNIQUE (email)\n'
          ')ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci',
 'vendors': 'CREATE TABLE IF NOT EXISTS vendors (\n'
            '\tid INTEGER NOT NULL AUTO_INCREMENT, \n'
            '\tname VARCHAR(150) NOT NULL, \n'
            '\temail VARCHAR(255), \n'
            '\tphone VARCHAR(30), \n'
            '\taddress VARCHAR(255), \n'
            "\tstatus VARCHAR(30) NOT NULL DEFAULT 'Active', \n"
            '\tcreated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, \n'
            '\tPRIMARY KEY (id), \n'
            '\tUNIQUE (name)\n'
            ')ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci',
 'vouchers': 'CREATE TABLE IF NOT EXISTS vouchers (\n'
             '\tid INTEGER NOT NULL AUTO_INCREMENT, \n'
             '\tcode VARCHAR(50) NOT NULL, \n'
             '\tname VARCHAR(150), \n'
             '\tdescription VARCHAR(255), \n'
             "\tdiscount_type VARCHAR(30) NOT NULL DEFAULT 'PERCENTAGE', \n"
             '\tdiscount_value NUMERIC(12, 2) NOT NULL, \n'
             '\tmax_discount_amount NUMERIC(12, 2), \n'
             "\tmin_order_amount NUMERIC(12, 2) NOT NULL DEFAULT '0.00', \n"
             '\tvalid_from DATETIME NOT NULL, \n'
             '\tvalid_to DATETIME NOT NULL, \n'
             '\tusage_limit INTEGER, \n'
             "\tused_count INTEGER NOT NULL DEFAULT '0', \n"
             "\tstatus VARCHAR(30) NOT NULL DEFAULT 'ACTIVE', \n"
             '\tcreated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, \n'
             '\tupdated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, \n'
             '\tPRIMARY KEY (id), \n'
             '\tCONSTRAINT uk_vouchers_code UNIQUE (code), \n'
             '\tCONSTRAINT ck_vouchers_discount_value_positive CHECK (discount_value > '
             '0), \n'
             '\tCONSTRAINT ck_vouchers_min_order_amount_nonnegative CHECK '
             '(min_order_amount >= 0), \n'
             '\tCONSTRAINT ck_vouchers_date_range CHECK (valid_to >= valid_from), \n'
             '\tCONSTRAINT ck_vouchers_used_count_nonnegative CHECK (used_count >= 0)\n'
             ')ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci',
 'carts': 'CREATE TABLE IF NOT EXISTS carts (\n'
          '\tid INTEGER NOT NULL AUTO_INCREMENT, \n'
          '\tuser_id INTEGER NOT NULL, \n'
          "\tstatus VARCHAR(30) NOT NULL DEFAULT 'Active', \n"
          '\tcreated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, \n'
          '\tupdated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, \n'
          '\tPRIMARY KEY (id), \n'
          '\tCONSTRAINT uk_carts_user UNIQUE (user_id), \n'
          '\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE ON UPDATE '
          'CASCADE\n'
          ')ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci',
 'orders': 'CREATE TABLE IF NOT EXISTS orders (\n'
           '\tid INTEGER NOT NULL AUTO_INCREMENT, \n'
           '\torder_code VARCHAR(40) NOT NULL, \n'
           '\tcustomer_id INTEGER NOT NULL, \n'
           '\ttotal_price NUMERIC(12, 2) NOT NULL, \n'
           '\tshipping_address VARCHAR(255) NOT NULL, \n'
           "\tstatus VARCHAR(30) NOT NULL DEFAULT 'PENDING', \n"
           '\tcreated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, \n'
           '\tupdated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, \n'
           '\tPRIMARY KEY (id), \n'
           '\tCONSTRAINT uk_orders_code UNIQUE (order_code), \n'
           '\tCONSTRAINT ck_orders_total_price_nonnegative CHECK (total_price >= 0), \n'
           '\tFOREIGN KEY(customer_id) REFERENCES users (id) ON DELETE RESTRICT ON '
           'UPDATE CASCADE\n'
           ')ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci',
 'products': 'CREATE TABLE IF NOT EXISTS products (\n'
             '\tid INTEGER NOT NULL AUTO_INCREMENT, \n'
             '\tcategory_id INTEGER NOT NULL, \n'
             '\tstore_id INTEGER, \n'
             '\tname VARCHAR(255) NOT NULL, \n'
             '\tslug VARCHAR(255) NOT NULL, \n'
             '\tdescription TEXT, \n'
             '\tprice NUMERIC(12, 2) NOT NULL, \n'
             "\trating NUMERIC(2, 1) NOT NULL DEFAULT '0', \n"
             "\tstock INTEGER NOT NULL DEFAULT '0', \n"
             '\timage_url VARCHAR(500), \n'
             "\tstatus VARCHAR(30) NOT NULL DEFAULT 'Published', \n"
             '\tcreated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, \n'
             '\tPRIMARY KEY (id), \n'
             '\tFOREIGN KEY(category_id) REFERENCES categories (id) ON DELETE RESTRICT '
             'ON UPDATE CASCADE\n'
             ')ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci',
 'stores': 'CREATE TABLE IF NOT EXISTS stores (\n'
           '\tid INTEGER NOT NULL AUTO_INCREMENT, \n'
           '\tvendor_id INTEGER NOT NULL, \n'
           '\tname VARCHAR(150) NOT NULL, \n'
           '\temail VARCHAR(255), \n'
           '\tphone VARCHAR(30), \n'
           '\taddress VARCHAR(255), \n'
           "\tstatus VARCHAR(30) NOT NULL DEFAULT 'Active', \n"
           '\tcreated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, \n'
           '\tPRIMARY KEY (id), \n'
           '\tCONSTRAINT uk_stores_vendor_name UNIQUE (vendor_id, name), \n'
           '\tFOREIGN KEY(vendor_id) REFERENCES vendors (id) ON DELETE CASCADE ON '
           'UPDATE CASCADE\n'
           ')ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci',
 'order_cancellations': 'CREATE TABLE IF NOT EXISTS order_cancellations (\n'
                        '\tid INTEGER NOT NULL AUTO_INCREMENT, \n'
                        '\torder_id INTEGER NOT NULL, \n'
                        '\torder_code VARCHAR(40) NOT NULL, \n'
                        '\tuser_id INTEGER NOT NULL, \n'
                        '\treason VARCHAR(500) NOT NULL, \n'
                        "\tcancelled_by VARCHAR(50) NOT NULL DEFAULT 'CUSTOMER', \n"
                        "\tinventory_restocked BOOL NOT NULL DEFAULT '1', \n"
                        '\tcancelled_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, \n'
                        '\tPRIMARY KEY (id), \n'
                        '\tCONSTRAINT uk_order_cancellations_order_id UNIQUE '
                        '(order_id), \n'
                        '\tFOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE '
                        'CASCADE ON UPDATE CASCADE, \n'
                        '\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE '
                        'RESTRICT ON UPDATE CASCADE\n'
                        ')ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci',
 'order_status_histories': 'CREATE TABLE IF NOT EXISTS order_status_histories (\n'
                           '\tid INTEGER NOT NULL AUTO_INCREMENT, \n'
                           '\torder_id INTEGER NOT NULL, \n'
                           '\torder_code VARCHAR(40) NOT NULL, \n'
                           '\tstore_id INTEGER, \n'
                           '\tprevious_status VARCHAR(30) NOT NULL, \n'
                           '\tnew_status VARCHAR(30) NOT NULL, \n'
                           '\treason VARCHAR(500), \n'
                           "\tchanged_by_role VARCHAR(50) NOT NULL DEFAULT 'VENDOR', \n"
                           '\tchanged_by_user_id INTEGER, \n'
                           '\tcreated_at DATETIME NOT NULL DEFAULT '
                           'CURRENT_TIMESTAMP, \n'
                           '\tPRIMARY KEY (id), \n'
                           '\tFOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE '
                           'CASCADE ON UPDATE CASCADE\n'
                           ')ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci',
 'payments': 'CREATE TABLE IF NOT EXISTS payments (\n'
             '\tid INTEGER NOT NULL AUTO_INCREMENT, \n'
             '\torder_id INTEGER NOT NULL, \n'
             '\tmethod VARCHAR(50) NOT NULL, \n'
             '\tamount NUMERIC(12, 2) NOT NULL, \n'
             "\tstatus VARCHAR(30) NOT NULL DEFAULT 'PENDING', \n"
             '\ttransaction_reference VARCHAR(100), \n'
             "\tattempt_number INTEGER NOT NULL DEFAULT '1', \n"
             '\tcreated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, \n'
             '\tupdated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, \n'
             '\tPRIMARY KEY (id), \n'
             '\tCONSTRAINT uk_payments_order_attempt UNIQUE (order_id, '
             'attempt_number), \n'
             '\tCONSTRAINT uk_payments_transaction_ref UNIQUE '
             '(transaction_reference), \n'
             '\tCONSTRAINT ck_payments_amount_positive CHECK (amount > 0), \n'
             '\tCONSTRAINT ck_payments_attempt_positive CHECK (attempt_number >= 1), \n'
             '\tFOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE CASCADE ON '
             'UPDATE CASCADE\n'
             ')ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci',
 'product_images': 'CREATE TABLE IF NOT EXISTS product_images (\n'
                   '\tid INTEGER NOT NULL AUTO_INCREMENT, \n'
                   '\tproduct_id INTEGER NOT NULL, \n'
                   '\turl VARCHAR(500) NOT NULL, \n'
                   '\tfilename VARCHAR(255) NOT NULL, \n'
                   '\tcontent_type VARCHAR(100) NOT NULL, \n'
                   '\tsize_bytes INTEGER NOT NULL, \n'
                   '\tcreated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, \n'
                   '\tPRIMARY KEY (id), \n'
                   '\tFOREIGN KEY(product_id) REFERENCES products (id) ON DELETE '
                   'CASCADE ON UPDATE CASCADE\n'
                   ')ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci',
 'product_variants': 'CREATE TABLE IF NOT EXISTS product_variants (\n'
                     '\tid INTEGER NOT NULL AUTO_INCREMENT, \n'
                     '\tproduct_id INTEGER NOT NULL, \n'
                     '\tsku VARCHAR(100) NOT NULL, \n'
                     '\tcolor VARCHAR(100), \n'
                     '\tsize VARCHAR(50), \n'
                     "\tstock INTEGER NOT NULL DEFAULT '0', \n"
                     '\tPRIMARY KEY (id), \n'
                     '\tCONSTRAINT ck_product_variants_stock_nonnegative CHECK (stock '
                     '>= 0), \n'
                     '\tFOREIGN KEY(product_id) REFERENCES products (id) ON DELETE '
                     'CASCADE ON UPDATE CASCADE, \n'
                     '\tUNIQUE (sku)\n'
                     ')ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci',
 'store_orders': 'CREATE TABLE IF NOT EXISTS store_orders (\n'
                 '\tid INTEGER NOT NULL AUTO_INCREMENT, \n'
                 '\torder_id INTEGER NOT NULL, \n'
                 '\tstore_id INTEGER NOT NULL, \n'
                 '\tcreated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, \n'
                 '\tPRIMARY KEY (id), \n'
                 '\tCONSTRAINT uk_store_orders_order_id UNIQUE (order_id), \n'
                 '\tFOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE CASCADE ON '
                 'UPDATE CASCADE, \n'
                 '\tFOREIGN KEY(store_id) REFERENCES stores (id) ON DELETE CASCADE ON '
                 'UPDATE CASCADE\n'
                 ')ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci',
 'wishlists': 'CREATE TABLE IF NOT EXISTS wishlists (\n'
              '\tid INTEGER NOT NULL AUTO_INCREMENT, \n'
              '\tuser_id INTEGER NOT NULL, \n'
              '\tproduct_id INTEGER NOT NULL, \n'
              '\tcreated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, \n'
              '\tPRIMARY KEY (id), \n'
              '\tCONSTRAINT uk_wishlist_user_product UNIQUE (user_id, product_id), \n'
              '\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE ON '
              'UPDATE CASCADE, \n'
              '\tFOREIGN KEY(product_id) REFERENCES products (id) ON DELETE CASCADE ON '
              'UPDATE CASCADE\n'
              ')ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci',
 'cart_items': 'CREATE TABLE IF NOT EXISTS cart_items (\n'
               '\tid INTEGER NOT NULL AUTO_INCREMENT, \n'
               '\tcart_id INTEGER NOT NULL, \n'
               '\tvariant_id INTEGER NOT NULL, \n'
               "\tquantity INTEGER NOT NULL DEFAULT '1', \n"
               '\tcreated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, \n'
               '\tupdated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, \n'
               '\tPRIMARY KEY (id), \n'
               '\tCONSTRAINT uk_cart_item_cart_variant UNIQUE (cart_id, variant_id), \n'
               '\tCONSTRAINT ck_cart_items_quantity_positive CHECK (quantity > 0), \n'
               '\tFOREIGN KEY(cart_id) REFERENCES carts (id) ON DELETE CASCADE ON '
               'UPDATE CASCADE, \n'
               '\tFOREIGN KEY(variant_id) REFERENCES product_variants (id) ON DELETE '
               'CASCADE ON UPDATE CASCADE\n'
               ')ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci',
 'inventory_movements': 'CREATE TABLE IF NOT EXISTS inventory_movements (\n'
                        '\tid INTEGER NOT NULL AUTO_INCREMENT, \n'
                        '\tvariant_id INTEGER NOT NULL, \n'
                        '\tmovement_type VARCHAR(30) NOT NULL, \n'
                        '\tquantity INTEGER NOT NULL, \n'
                        '\tstock_before INTEGER NOT NULL, \n'
                        '\tstock_after INTEGER NOT NULL, \n'
                        '\treason VARCHAR(255), \n'
                        '\tcreated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, \n'
                        '\tPRIMARY KEY (id), \n'
                        '\tFOREIGN KEY(variant_id) REFERENCES product_variants (id) ON '
                        'DELETE CASCADE ON UPDATE CASCADE\n'
                        ')ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci',
 'order_items': 'CREATE TABLE IF NOT EXISTS order_items (\n'
                '\tid INTEGER NOT NULL AUTO_INCREMENT, \n'
                '\torder_id INTEGER NOT NULL, \n'
                '\tvariant_id INTEGER, \n'
                '\tproduct_id INTEGER, \n'
                '\tunit_price NUMERIC(12, 2) NOT NULL, \n'
                "\tquantity INTEGER NOT NULL DEFAULT '1', \n"
                '\tline_total NUMERIC(12, 2) NOT NULL, \n'
                '\tPRIMARY KEY (id), \n'
                '\tCONSTRAINT ck_order_items_quantity_positive CHECK (quantity > 0), \n'
                '\tCONSTRAINT ck_order_items_unit_price_nonnegative CHECK (unit_price '
                '>= 0), \n'
                '\tCONSTRAINT ck_order_items_line_total_nonnegative CHECK (line_total '
                '>= 0), \n'
                '\tFOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE CASCADE ON '
                'UPDATE CASCADE, \n'
                '\tFOREIGN KEY(variant_id) REFERENCES product_variants (id) ON DELETE '
                'SET NULL ON UPDATE CASCADE, \n'
                '\tFOREIGN KEY(product_id) REFERENCES products (id) ON DELETE SET NULL '
                'ON UPDATE CASCADE\n'
                ')ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci'}
_INDEX_DDL = [('payment_webhook_logs',
  'ix_payment_webhook_logs_gateway',
  ('gateway',),
  'CREATE INDEX ix_payment_webhook_logs_gateway ON payment_webhook_logs (gateway)'),
 ('payment_webhook_logs',
  'ix_payment_webhook_logs_transaction_reference',
  ('transaction_reference',),
  'CREATE INDEX ix_payment_webhook_logs_transaction_reference ON payment_webhook_logs '
  '(transaction_reference)'),
 ('vouchers',
  'ix_vouchers_status',
  ('status',),
  'CREATE INDEX ix_vouchers_status ON vouchers (status)'),
 ('orders',
  'ix_orders_customer_id',
  ('customer_id',),
  'CREATE INDEX ix_orders_customer_id ON orders (customer_id)'),
 ('orders',
  'ix_orders_status',
  ('status',),
  'CREATE INDEX ix_orders_status ON orders (status)'),
 ('products',
  'ix_products_category_id',
  ('category_id',),
  'CREATE INDEX ix_products_category_id ON products (category_id)'),
 ('products',
  'ix_products_slug',
  ('slug',),
  'CREATE UNIQUE INDEX ix_products_slug ON products (slug)'),
 ('products',
  'ix_products_store_id',
  ('store_id',),
  'CREATE INDEX ix_products_store_id ON products (store_id)'),
 ('stores',
  'ix_stores_vendor_id',
  ('vendor_id',),
  'CREATE INDEX ix_stores_vendor_id ON stores (vendor_id)'),
 ('order_cancellations',
  'ix_order_cancellations_order_code',
  ('order_code',),
  'CREATE INDEX ix_order_cancellations_order_code ON order_cancellations (order_code)'),
 ('order_cancellations',
  'ix_order_cancellations_user_id',
  ('user_id',),
  'CREATE INDEX ix_order_cancellations_user_id ON order_cancellations (user_id)'),
 ('order_status_histories',
  'ix_order_status_histories_order_code',
  ('order_code',),
  'CREATE INDEX ix_order_status_histories_order_code ON order_status_histories '
  '(order_code)'),
 ('order_status_histories',
  'ix_order_status_histories_order_id',
  ('order_id',),
  'CREATE INDEX ix_order_status_histories_order_id ON order_status_histories '
  '(order_id)'),
 ('order_status_histories',
  'ix_order_status_histories_store_id',
  ('store_id',),
  'CREATE INDEX ix_order_status_histories_store_id ON order_status_histories '
  '(store_id)'),
 ('payments',
  'ix_payments_method',
  ('method',),
  'CREATE INDEX ix_payments_method ON payments (method)'),
 ('payments',
  'ix_payments_order_id',
  ('order_id',),
  'CREATE INDEX ix_payments_order_id ON payments (order_id)'),
 ('payments',
  'ix_payments_status',
  ('status',),
  'CREATE INDEX ix_payments_status ON payments (status)'),
 ('product_images',
  'ix_product_images_product_id',
  ('product_id',),
  'CREATE INDEX ix_product_images_product_id ON product_images (product_id)'),
 ('product_variants',
  'ix_product_variants_product_id',
  ('product_id',),
  'CREATE INDEX ix_product_variants_product_id ON product_variants (product_id)'),
 ('store_orders',
  'ix_store_orders_store_id',
  ('store_id',),
  'CREATE INDEX ix_store_orders_store_id ON store_orders (store_id)'),
 ('wishlists',
  'ix_wishlists_product_id',
  ('product_id',),
  'CREATE INDEX ix_wishlists_product_id ON wishlists (product_id)'),
 ('wishlists',
  'ix_wishlists_user_id',
  ('user_id',),
  'CREATE INDEX ix_wishlists_user_id ON wishlists (user_id)'),
 ('cart_items',
  'ix_cart_items_cart_id',
  ('cart_id',),
  'CREATE INDEX ix_cart_items_cart_id ON cart_items (cart_id)'),
 ('cart_items',
  'ix_cart_items_variant_id',
  ('variant_id',),
  'CREATE INDEX ix_cart_items_variant_id ON cart_items (variant_id)'),
 ('inventory_movements',
  'ix_inventory_movements_variant_created',
  ('variant_id', 'created_at'),
  'CREATE INDEX ix_inventory_movements_variant_created ON inventory_movements '
  '(variant_id, created_at)'),
 ('inventory_movements',
  'ix_inventory_movements_variant_id',
  ('variant_id',),
  'CREATE INDEX ix_inventory_movements_variant_id ON inventory_movements (variant_id)'),
 ('order_items',
  'ix_order_items_order_id',
  ('order_id',),
  'CREATE INDEX ix_order_items_order_id ON order_items (order_id)'),
 ('order_items',
  'ix_order_items_product_id',
  ('product_id',),
  'CREATE INDEX ix_order_items_product_id ON order_items (product_id)'),
 ('order_items',
  'ix_order_items_variant_id',
  ('variant_id',),
  'CREATE INDEX ix_order_items_variant_id ON order_items (variant_id)')]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    if _TRACKER not in existing:
        bind.execute(text(
            "CREATE TABLE _t1shop_migration_baseline ("
            "table_name VARCHAR(64) NOT NULL PRIMARY KEY, "
            "existed_before BOOLEAN NOT NULL) "
            "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
        ))
    recorded = {
        row[0]
        for row in bind.execute(text("SELECT table_name FROM _t1shop_migration_baseline"))
    }
    for table_name in _TABLE_NAMES:
        if table_name not in recorded:
            bind.execute(
                text(
                    "INSERT INTO _t1shop_migration_baseline "
                    "(table_name, existed_before) VALUES (:name, :existed)"
                ),
                {"name": table_name, "existed": table_name in existing},
            )

    for table_name in _TABLE_NAMES:
        if table_name not in set(inspect(bind).get_table_names()):
            bind.execute(text(_TABLE_DDL[table_name]))

    for table_name, index_name, columns, ddl in _INDEX_DDL:
        inspector = inspect(bind)
        if table_name not in inspector.get_table_names():
            continue
        existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
        if not set(columns).issubset(existing_columns):
            continue
        existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
        if index_name not in existing_indexes:
            bind.execute(text(ddl))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if _TRACKER not in inspector.get_table_names():
        return
    created_by_revision = {
        row[0]
        for row in bind.execute(
            text(
                "SELECT table_name FROM _t1shop_migration_baseline "
                "WHERE existed_before = 0"
            )
        )
    }
    for table_name in reversed(_TABLE_NAMES):
        if table_name in created_by_revision and table_name in inspect(bind).get_table_names():
            op.drop_table(table_name)
    op.drop_table(_TRACKER)
