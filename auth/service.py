"""
Auth servis katmanı.
Şifre hash'leme (bcrypt), JWT token üretimi/doğrulama ve veritabanı işlemleri.

Güvenlik:
  - Şifreler bcrypt ile hash'lenir, düz metin asla saklanmaz
  - JWT token'lar HS256 ile imzalanır
  - Supabase PostgREST API parametrized query kullanır → SQL Injection imkansız
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt

from config import settings

# ─────────────────────── Şifre Hash'leme (bcrypt) ──────────────────


def hash_password(password: str) -> str:
    """
    Şifreyi bcrypt ile hash'ler.
    Her çağrıda farklı salt üretir → aynı şifre farklı hash verir.
    """
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Düz metin şifreyi hash ile karşılaştırır.
    Timing attack'lara karşı sabit zamanlı karşılaştırma yapar.
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


# ─────────────────────── JWT Token İşlemleri ───────────────────────


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    JWT access token üretir.

    Args:
        data: Token payload'ına eklenecek veriler (örn: {"sub": user_id})
        expires_delta: Özel geçerlilik süresi (varsayılan: settings'ten okunur)

    Returns:
        Kodlanmış JWT token string'i
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    })

    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """
    JWT token'ı çözer ve doğrular.

    Raises:
        jwt.ExpiredSignatureError: Token süresi dolmuş
        jwt.InvalidTokenError: Token geçersiz veya bozuk
    """
    payload = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
    return payload


# ─────────────────────── Veritabanı İşlemleri ──────────────────────


def db_get_user_by_email(supabase_client, email: str) -> Optional[dict]:
    """
    E-posta adresine göre kullanıcı arar.

    PostgREST API filtreleri kullanır — değerler otomatik escape edilir.
    → SQL Injection saldırısı imkansız.
    """
    results = supabase_client.select(
        table="users",
        columns="*",
        filters={"email": email},
    )
    if results:
        return results[0]
    return None


def db_get_user_by_username(supabase_client, username: str) -> Optional[dict]:
    """
    Kullanıcı adına göre kullanıcı arar.

    PostgREST API filtreleri kullanır — değerler otomatik escape edilir.
    → SQL Injection saldırısı imkansız.
    """
    results = supabase_client.select(
        table="users",
        columns="*",
        filters={"username": username},
    )
    if results:
        return results[0]
    return None


def db_get_user_by_id(supabase_client, user_id: str) -> Optional[dict]:
    """
    UUID'ye göre kullanıcı arar.

    PostgREST API filtreleri kullanır — değerler otomatik escape edilir.
    → SQL Injection saldırısı imkansız.
    """
    results = supabase_client.select(
        table="users",
        columns="id, email, username, credit_count, is_premium, premium_until",
        filters={"id": user_id},
    )
    if results:
        return results[0]
    return None


def db_create_user(
    supabase_client,
    email: str,
    username: str,
    hashed_password: str,
) -> dict:
    """
    Yeni kullanıcı oluşturur.
    Veritabanındaki sütunlarla %100 eşleşecek şekilde ayarlandı.
    """
    user_data = {
        "email": email,
        "username": username,
        "hashed_password": hashed_password,
        "credit_count": 3,
        "is_premium": False
    }

    results = supabase_client.insert(table="users", data=user_data)
    return results[0]
