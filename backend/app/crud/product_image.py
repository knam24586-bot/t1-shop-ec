"""CRUD và lưu trữ file ảnh sản phẩm."""
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.product_image import ProductImage


IMAGE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def image_storage_dir() -> Path:
    directory = Path(settings.UPLOAD_DIR) / "products"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def image_has_valid_signature(content_type: str, header: bytes) -> bool:
    signatures = {
        "image/jpeg": header.startswith(b"\xff\xd8\xff"),
        "image/png": header.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/gif": header.startswith((b"GIF87a", b"GIF89a")),
        "image/webp": header[:4] == b"RIFF" and header[8:12] == b"WEBP",
    }
    return signatures.get(content_type, False)


def save_product_image(
    db: Session,
    *,
    product_id: int,
    content_type: str,
    chunks: list[bytes],
    size_bytes: int,
) -> ProductImage:
    extension = IMAGE_EXTENSIONS[content_type]
    filename = f"{uuid4().hex}{extension}"
    directory = image_storage_dir()
    path = directory / filename
    path.write_bytes(b"".join(chunks))

    image = ProductImage(
        product_id=product_id,
        url=f"/uploads/products/{filename}",
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
    )
    try:
        db.add(image)
        db.commit()
        db.refresh(image)
    except SQLAlchemyError:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    return image


def get_product_images(db: Session, product_id: int) -> list[ProductImage]:
    query = (
        select(ProductImage)
        .where(ProductImage.product_id == product_id)
        .order_by(ProductImage.id.desc())
    )
    return list(db.scalars(query))


def get_product_image(db: Session, product_id: int, image_id: int) -> ProductImage | None:
    query = select(ProductImage).where(
        ProductImage.id == image_id,
        ProductImage.product_id == product_id,
    )
    return db.scalars(query).first()


def delete_product_image(db: Session, image: ProductImage) -> None:
    path = image_storage_dir() / image.filename
    db.delete(image)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    path.unlink(missing_ok=True)
