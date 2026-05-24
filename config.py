"""
Uygulama yapılandırması.
Ortam değişkenlerini .env dosyasından okur ve doğrular.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Uygulama yapılandırma modeli — tüm ayarlar ortam değişkenlerinden okunur."""

    # ── Supabase ──
    SUPABASE_URL: str = Field(
        ...,
        description="Supabase proje URL'i (örn: https://xxxxx.supabase.co)",
    )
    SUPABASE_KEY: str = Field(
        ...,
        description="Supabase anon (public) API key",
    )

    # ── JWT ──
    JWT_SECRET_KEY: str = Field(
        ...,
        description="JWT token imzalama için gizli anahtar",
    )
    JWT_ALGORITHM: str = Field(
        default="HS256",
        description="JWT imzalama algoritması",
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=30,
        description="Access token geçerlilik süresi (dakika)",
    )

    # ── Google OAuth ──
    GOOGLE_CLIENT_ID: str = Field(
        default="",
        description="Google Cloud OAuth Client ID",
    )
    GOOGLE_CLIENT_SECRET: str = Field(
        default="",
        description="Google Cloud OAuth Client Secret",
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


# Singleton yapılandırma nesnesi
settings = Settings()
