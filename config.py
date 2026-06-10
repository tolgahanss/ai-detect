from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    """Uygulama yapılandırma modeli — tüm ayarlar varsayılan değerlerle garantiye alındı."""

    # ── Supabase ──
    SUPABASE_URL: str = Field(
        default="https://uvkocqokxeueajpssaew.supabase.co",
        description="Supabase proje URL'i",
    )
    SUPABASE_KEY: str = Field(
        default="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV2a29jcW9reGV1ZWFqcHNzYWV3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzkxNDA3NDIsImV4cCI6MjA5NDcxNjc0Mn0.P14jCGhTRuUPbGXGCly-BzVyT5GCArx1TwqgvmFH8XQ",
        description="Supabase anon (public) API key",
    )

    # ── JWT ──
    JWT_SECRET_KEY: str = Field(
        default="b9ac7f5287fc4c969cfebc06d3e629de7a2c27a7ac3d1657b540d413eeb2424e",
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

    # ── Lemon Squeezy ──
    LEMONSQUEEZY_WEBHOOK_SECRET: str = Field(
        default="",
        description="Lemon Squeezy Webhook imza doğrulama secret'ı",
    )

    # ── URLs ──
    GOOGLE_REDIRECT_URI: str = Field(
        default="http://127.0.0.1:8000/auth/google/callback",
        description="Google OAuth redirect URI",
    )
    FRONTEND_URL: str = Field(
        default="http://127.0.0.1:5500/index.html",
        description="Frontend URL for redirection after OAuth login",
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }

settings = Settings()
