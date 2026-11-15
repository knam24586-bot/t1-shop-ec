"""Các schema request/response cho API sản phẩm."""
from datetime import datetime
from decimal import Decimal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator


PRODUCT_STATUSES = {"Published", "Draft", "Archived"}


class ProductVariantBase(BaseModel):
    sku: str = Field(min_length=1, max_length=100)
    color: str | None = Field(default=None, max_length=100)
    size: str | None = Field(default=None, max_length=50)
    stock: int = Field(default=0, ge=0)


class ProductVariantCreate(ProductVariantBase):
    pass


class ProductVariantResponse(ProductVariantBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class ProductBase(BaseModel):
    category_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255)
    description: str | None = None
    price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    stock: int = Field(default=0, ge=0)
    image_url: AnyHttpUrl | None = None
    status: str = "Published"
    store_id: int | None = Field(default=None, gt=0)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in PRODUCT_STATUSES:
            raise ValueError(f"status must be one of {sorted(PRODUCT_STATUSES)}")
        return value

    @field_validator("slug", "name")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class ProductCreate(ProductBase):
    variants: list[ProductVariantCreate] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    category_id: int | None = Field(default=None, gt=0)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    price: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    stock: int | None = Field(default=None, ge=0)
    image_url: AnyHttpUrl | None = None
    status: str | None = None
    store_id: int | None = Field(default=None, gt=0)
    variants: list[ProductVariantCreate] | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is not None and value not in PRODUCT_STATUSES:
            raise ValueError(f"status must be one of {sorted(PRODUCT_STATUSES)}")
        return value

    @field_validator("slug", "name")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class ProductResponse(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    variants: list[ProductVariantResponse] = Field(default_factory=list)
