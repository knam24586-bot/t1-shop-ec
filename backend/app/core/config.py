"""Đọc cấu hình từ file .env (hoặc biến môi trường).

Muốn thêm cấu hình mới: thêm 1 dòng vào class Settings + thêm vào .env.example.
"""
from urllib.parse import quote_plus

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_NAME: str = "KS25 Base API"
    APP_ENV: str = "development"

    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "t1shop_db"

    # Local default is intentionally development-only. Set a random secret in .env
    # before exposing the API beyond a local machine.
    JWT_SECRET: str = "t1-shop-development-secret-change-before-deploy"
    JWT_ISSUER: str = "t1shop-api"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    BOOTSTRAP_ADMIN_EMAIL: str = ""
    BOOTSTRAP_ADMIN_PASSWORD: str = ""
    BOOTSTRAP_ADMIN_NAME: str = "T1 Shop Admin"

    @model_validator(mode="after")
    def validate_auth_settings(self):
        if self.APP_ENV.casefold() == "production":
            if (
                len(self.JWT_SECRET) < 32
                or self.JWT_SECRET
                in {
                    "t1-shop-development-secret-change-before-deploy",
                    "replace-this-with-a-random-secret-before-deploy",
                }
            ):
                raise ValueError("Production requires a unique JWT_SECRET of at least 32 characters.")
        if self.JWT_ACCESS_TOKEN_EXPIRE_MINUTES < 1:
            raise ValueError("JWT_ACCESS_TOKEN_EXPIRE_MINUTES must be positive.")
        return self

    # Chuỗi các origin cách nhau bằng dấu phẩy, hoặc "*"
    CORS_ORIGINS: str = "*"
    UPLOAD_DIR: str = "uploads"
    MAX_IMAGE_SIZE_BYTES: int = 5 * 1024 * 1024
    ALLOWED_IMAGE_TYPES: str = "image/jpeg,image/png,image/gif,image/webp"

    @property
    def database_url(self) -> str:
        # mysql+pymysql://user:password@host:port/database
        # quote_plus: để mật khẩu có ký tự đặc biệt (@, #, /...) không làm hỏng URL
        return (
            f"mysql+pymysql://{self.DB_USER}:{quote_plus(self.DB_PASSWORD)}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def allowed_image_types(self) -> set[str]:
        return {
            image_type.strip()
            for image_type in self.ALLOWED_IMAGE_TYPES.split(",")
            if image_type.strip()
        }


settings = Settings()
