-- Generated from app.models metadata. Do not run separately; use python -m app.db.migrate.

CREATE DATABASE IF NOT EXISTS `t1shop_db` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE `t1shop_db`;

CREATE TABLE IF NOT EXISTS schema_migrations (revision VARCHAR(64) NOT NULL PRIMARY KEY, applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE categories (
	id INTEGER NOT NULL AUTO_INCREMENT,
	name VARCHAR(150) NOT NULL,
	slug VARCHAR(150) NOT NULL,
	status VARCHAR(30) NOT NULL DEFAULT 'Active',
	parent_id INTEGER,
	created_at DATETIME NOT NULL DEFAULT now(),
	PRIMARY KEY (id),
	UNIQUE (slug),
	FOREIGN KEY(parent_id) REFERENCES categories (id) ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE TABLE items (
	id INTEGER NOT NULL AUTO_INCREMENT,
	name VARCHAR(150) NOT NULL,
	description TEXT,
	price NUMERIC(12, 2) NOT NULL,
	created_at DATETIME NOT NULL DEFAULT now(),
	PRIMARY KEY (id)
);

CREATE TABLE vendors (
	id INTEGER NOT NULL AUTO_INCREMENT,
	name VARCHAR(150) NOT NULL,
	email VARCHAR(255),
	phone VARCHAR(30),
	address VARCHAR(255),
	status VARCHAR(30) NOT NULL DEFAULT 'Active',
	created_at DATETIME NOT NULL DEFAULT now(),
	PRIMARY KEY (id),
	UNIQUE (name)
);

CREATE TABLE vouchers (
	id INTEGER NOT NULL AUTO_INCREMENT,
	code VARCHAR(50) NOT NULL,
	name VARCHAR(150),
	description VARCHAR(255),
	discount_type VARCHAR(30) NOT NULL DEFAULT 'PERCENTAGE',
	discount_value NUMERIC(12, 2) NOT NULL,
	max_discount_amount NUMERIC(12, 2),
	min_order_amount NUMERIC(12, 2) NOT NULL DEFAULT '0.00',
	valid_from DATETIME NOT NULL,
	valid_to DATETIME NOT NULL,
	usage_limit INTEGER,
	used_count INTEGER NOT NULL DEFAULT '0',
	status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
	created_at DATETIME NOT NULL DEFAULT now(),
	updated_at DATETIME NOT NULL DEFAULT now(),
	PRIMARY KEY (id),
	CONSTRAINT uk_vouchers_code UNIQUE (code),
	CONSTRAINT ck_vouchers_discount_value_positive CHECK (discount_value > 0),
	CONSTRAINT ck_vouchers_min_order_amount_nonnegative CHECK (min_order_amount >= 0),
	CONSTRAINT ck_vouchers_date_range CHECK (valid_to >= valid_from),
	CONSTRAINT ck_vouchers_used_count_nonnegative CHECK (used_count >= 0)
);

CREATE UNIQUE INDEX ix_vouchers_code ON vouchers (code);

CREATE INDEX ix_vouchers_status ON vouchers (status);

CREATE TABLE stores (
	id INTEGER NOT NULL AUTO_INCREMENT,
	vendor_id INTEGER NOT NULL,
	name VARCHAR(150) NOT NULL,
	email VARCHAR(255),
	phone VARCHAR(30),
	address VARCHAR(255),
	status VARCHAR(30) NOT NULL DEFAULT 'Active',
	created_at DATETIME NOT NULL DEFAULT now(),
	PRIMARY KEY (id),
	CONSTRAINT uq_stores_vendor_name UNIQUE (vendor_id, name),
	FOREIGN KEY(vendor_id) REFERENCES vendors (id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX ix_stores_vendor_id ON stores (vendor_id);

CREATE TABLE products (
	id INTEGER NOT NULL AUTO_INCREMENT,
	category_id INTEGER NOT NULL,
	store_id INTEGER,
	name VARCHAR(255) NOT NULL,
	slug VARCHAR(255) NOT NULL,
	description TEXT,
	price NUMERIC(12, 2) NOT NULL,
	rating NUMERIC(2, 1) NOT NULL DEFAULT '0',
	stock INTEGER NOT NULL DEFAULT '0',
	image_url VARCHAR(500),
	status VARCHAR(30) NOT NULL DEFAULT 'Published',
	created_at DATETIME NOT NULL DEFAULT now(),
	PRIMARY KEY (id),
	FOREIGN KEY(category_id) REFERENCES categories (id) ON DELETE RESTRICT ON UPDATE CASCADE,
	FOREIGN KEY(store_id) REFERENCES stores (id) ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE INDEX ix_products_category_id ON products (category_id);

CREATE UNIQUE INDEX ix_products_slug ON products (slug);

CREATE INDEX ix_products_store_id ON products (store_id);

CREATE TABLE users (
	id INTEGER NOT NULL AUTO_INCREMENT,
	full_name VARCHAR(150) NOT NULL,
	email VARCHAR(255) NOT NULL,
	phone VARCHAR(30),
	password_hash VARCHAR(255) NOT NULL,
	`role` VARCHAR(50) NOT NULL DEFAULT 'CUSTOMER',
	status VARCHAR(30) NOT NULL DEFAULT 'Active',
	store_id INTEGER,
	created_at DATETIME NOT NULL DEFAULT now(),
	PRIMARY KEY (id),
	UNIQUE (email),
	FOREIGN KEY(store_id) REFERENCES stores (id) ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE INDEX ix_users_store_id ON users (store_id);

CREATE TABLE carts (
	id INTEGER NOT NULL AUTO_INCREMENT,
	user_id INTEGER NOT NULL,
	status VARCHAR(30) NOT NULL DEFAULT 'Active',
	created_at DATETIME NOT NULL DEFAULT now(),
	updated_at DATETIME NOT NULL DEFAULT now(),
	PRIMARY KEY (id),
	CONSTRAINT uk_carts_user UNIQUE (user_id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE orders (
	id INTEGER NOT NULL AUTO_INCREMENT,
	order_code VARCHAR(40) NOT NULL,
	customer_id INTEGER NOT NULL,
	total_price NUMERIC(12, 2) NOT NULL,
	shipping_address VARCHAR(255) NOT NULL,
	status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
	created_at DATETIME NOT NULL DEFAULT now(),
	updated_at DATETIME NOT NULL DEFAULT now(),
	PRIMARY KEY (id),
	CONSTRAINT uk_orders_code UNIQUE (order_code),
	CONSTRAINT ck_orders_total_price_nonnegative CHECK (total_price >= 0),
	FOREIGN KEY(customer_id) REFERENCES users (id) ON DELETE RESTRICT ON UPDATE CASCADE
);

CREATE INDEX ix_orders_customer_id ON orders (customer_id);

CREATE UNIQUE INDEX ix_orders_order_code ON orders (order_code);

CREATE INDEX ix_orders_status ON orders (status);

CREATE TABLE product_images (
	id INTEGER NOT NULL AUTO_INCREMENT,
	product_id INTEGER NOT NULL,
	url VARCHAR(500) NOT NULL,
	filename VARCHAR(255) NOT NULL,
	content_type VARCHAR(100) NOT NULL,
	size_bytes INTEGER NOT NULL,
	created_at DATETIME NOT NULL DEFAULT now(),
	PRIMARY KEY (id),
	FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX ix_product_images_product_id ON product_images (product_id);

CREATE TABLE product_variants (
	id INTEGER NOT NULL AUTO_INCREMENT,
	product_id INTEGER NOT NULL,
	sku VARCHAR(100) NOT NULL,
	color VARCHAR(100),
	size VARCHAR(50),
	stock INTEGER NOT NULL DEFAULT '0',
	PRIMARY KEY (id),
	CONSTRAINT ck_product_variants_stock_nonnegative CHECK (stock >= 0),
	FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE CASCADE ON UPDATE CASCADE,
	UNIQUE (sku)
);

CREATE INDEX ix_product_variants_product_id ON product_variants (product_id);

CREATE TABLE wishlists (
	id INTEGER NOT NULL AUTO_INCREMENT,
	user_id INTEGER NOT NULL,
	product_id INTEGER NOT NULL,
	created_at DATETIME NOT NULL DEFAULT now(),
	PRIMARY KEY (id),
	CONSTRAINT uk_wishlist_user_product UNIQUE (user_id, product_id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE ON UPDATE CASCADE,
	FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX ix_wishlists_product_id ON wishlists (product_id);

CREATE INDEX ix_wishlists_user_id ON wishlists (user_id);

CREATE TABLE cart_items (
	id INTEGER NOT NULL AUTO_INCREMENT,
	cart_id INTEGER NOT NULL,
	variant_id INTEGER NOT NULL,
	quantity INTEGER NOT NULL DEFAULT '1',
	created_at DATETIME NOT NULL DEFAULT now(),
	updated_at DATETIME NOT NULL DEFAULT now(),
	PRIMARY KEY (id),
	CONSTRAINT uk_cart_item_cart_variant UNIQUE (cart_id, variant_id),
	CONSTRAINT ck_cart_items_quantity_positive CHECK (quantity > 0),
	FOREIGN KEY(cart_id) REFERENCES carts (id) ON DELETE CASCADE ON UPDATE CASCADE,
	FOREIGN KEY(variant_id) REFERENCES product_variants (id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX ix_cart_items_cart_id ON cart_items (cart_id);

CREATE INDEX ix_cart_items_variant_id ON cart_items (variant_id);

CREATE TABLE order_items (
	id INTEGER NOT NULL AUTO_INCREMENT,
	order_id INTEGER NOT NULL,
	variant_id INTEGER,
	product_id INTEGER,
	unit_price NUMERIC(12, 2) NOT NULL,
	quantity INTEGER NOT NULL DEFAULT '1',
	line_total NUMERIC(12, 2) NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_order_items_quantity_positive CHECK (quantity > 0),
	CONSTRAINT ck_order_items_unit_price_nonnegative CHECK (unit_price >= 0),
	CONSTRAINT ck_order_items_line_total_nonnegative CHECK (line_total >= 0),
	FOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE CASCADE ON UPDATE CASCADE,
	FOREIGN KEY(variant_id) REFERENCES product_variants (id) ON DELETE SET NULL ON UPDATE CASCADE,
	FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE INDEX ix_order_items_order_id ON order_items (order_id);

CREATE INDEX ix_order_items_product_id ON order_items (product_id);

CREATE INDEX ix_order_items_variant_id ON order_items (variant_id);

CREATE TABLE payments (
	id INTEGER NOT NULL AUTO_INCREMENT,
	order_id INTEGER NOT NULL,
	method VARCHAR(50) NOT NULL,
	amount NUMERIC(12, 2) NOT NULL,
	status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
	transaction_reference VARCHAR(100),
	attempt_number INTEGER NOT NULL DEFAULT '1',
	created_at DATETIME NOT NULL DEFAULT now(),
	updated_at DATETIME NOT NULL DEFAULT now(),
	PRIMARY KEY (id),
	CONSTRAINT uk_payments_order_attempt UNIQUE (order_id, attempt_number),
	CONSTRAINT uk_payments_transaction_ref UNIQUE (transaction_reference),
	CONSTRAINT ck_payments_amount_positive CHECK (amount > 0),
	CONSTRAINT ck_payments_attempt_positive CHECK (attempt_number >= 1),
	FOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX ix_payments_method ON payments (method);

CREATE INDEX ix_payments_order_id ON payments (order_id);

CREATE INDEX ix_payments_status ON payments (status);

CREATE UNIQUE INDEX ix_payments_transaction_reference ON payments (transaction_reference);

INSERT INTO categories (name, slug, status) VALUES ('T1 Shop', 't1-demo', 'Active') ON DUPLICATE KEY UPDATE name = VALUES(name);

INSERT INTO products (category_id, name, slug, description, price, rating, stock, image_url, status) SELECT id, 'T1 Shop Hoodie', 't1-demo-hoodie', 'Sản phẩm mẫu để trải nghiệm luồng giỏ hàng và thanh toán COD.', 499000.00, 5.0, 25, 'https://images.unsplash.com/photo-1556821840-3a63f95609a7?auto=format&fit=crop&w=700&q=80', 'Published' FROM categories WHERE slug = 't1-demo' ON DUPLICATE KEY UPDATE name = VALUES(name);

INSERT INTO product_variants (product_id, sku, color, size, stock) SELECT id, 'T1-DEMO-HOODIE-001', 'Black', 'M', 25 FROM products WHERE slug = 't1-demo-hoodie' ON DUPLICATE KEY UPDATE sku = VALUES(sku);
