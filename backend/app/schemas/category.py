"""Schema request/response cho Category API."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CategoryBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    slug: str = Field(min_length=1, max_length=150, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    status: str = Field(default="Active", min_length=1, max_length=30)
    parent_id: int | None = Field(default=None, gt=0)


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    slug: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    status: str | None = Field(default=None, min_length=1, max_length=30)
    parent_id: int | None = Field(default=None, gt=0)


class CategoryRead(CategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
