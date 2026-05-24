"""
Auth Pydantic şemaları.
İstek ve yanıt modellerini tanımlar — input doğrulaması ile zararlı veri girişini engeller.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator
import re


# ─────────────────────── İstek (Request) Modelleri ─────────────────


class UserRegister(BaseModel):
    """Kullanıcı kayıt isteği modeli."""

    email: EmailStr = Field(
        ...,
        description="Geçerli e-posta adresi",
        examples=["kullanici@ornek.com"],
    )
    username: str = Field(
        ...,
        min_length=3,
        max_length=30,
        description="Kullanıcı adı (3-30 karakter, alfanümerik)",
        examples=["tolga_dev"],
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Şifre (min 8 karakter, en az 1 büyük harf, 1 rakam)",
        examples=["GucluSifre123"],
    )


    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Şifre güvenlik gereksinimlerini kontrol eder."""
        if not re.search(r"[A-Z]", v):
            raise ValueError("Şifre en az bir büyük harf içermelidir.")
        if not re.search(r"[a-z]", v):
            raise ValueError("Şifre en az bir küçük harf içermelidir.")
        if not re.search(r"[0-9]", v):
            raise ValueError("Şifre en az bir rakam içermelidir.")
        return v


class UserLogin(BaseModel):
    """Kullanıcı giriş isteği modeli."""

    email: EmailStr = Field(
        ...,
        description="Kayıtlı e-posta adresi",
        examples=["kullanici@ornek.com"],
    )
    password: str = Field(
        ...,
        min_length=1,
        description="Kullanıcı şifresi",
        examples=["GucluSifre123"],
    )


# ─────────────────────── Yanıt (Response) Modelleri ────────────────


class UserResponse(BaseModel):
    """Kullanıcı bilgi yanıtı — şifre asla döndürülmez."""

    id: str
    email: str
    username: str
    credit_count: int = 3
    is_premium: bool = False
    premium_until: Optional[str] = None
    role: str = "user"



class TokenResponse(BaseModel):
    """JWT token yanıtı."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token türü")
    expires_in: int = Field(..., description="Token geçerlilik süresi (saniye)")
    user: UserResponse = Field(..., description="Kullanıcı bilgileri")


class MessageResponse(BaseModel):
    """Basit mesaj yanıtı."""

    message: str
    detail: Optional[str] = None
