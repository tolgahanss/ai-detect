"""
Auth dependency'leri — FastAPI dependency injection.
JWT token'dan kullanıcı bilgisini çıkarır ve doğrular.
"""

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from auth.service import decode_access_token, db_get_user_by_id
from database import get_supabase

# Swagger UI'da "Authorize" butonu gösterir
# tokenUrl, /auth/login endpoint'ine işaret eder
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """
    Authorization header'daki Bearer token'ı doğrular ve kullanıcıyı döndürür.

    Kullanım:
        @app.get("/protected")
        async def protected_route(user = Depends(get_current_user)):
            return {"user": user}

    Raises:
        401 Unauthorized: Token eksik, geçersiz veya süresi dolmuş
        401 Unauthorized: Kullanıcı bulunamadı veya deaktif
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Kimlik doğrulama başarısız. Geçersiz veya süresi dolmuş token.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Erişim token'ı gereklidir. Authorization header'da Bearer token gönderin.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(token)
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token süresi dolmuş. Lütfen tekrar giriş yapın.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise credentials_exception

    # Kullanıcıyı veritabanından al
    try:
        supabase = get_supabase()
        user = db_get_user_by_id(supabase, user_id)
    except Exception:
        # DB bağlantı hatası → güvenli fail: erişimi reddet
        raise credentials_exception

    if user is None:
        raise credentials_exception

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu hesap devre dışı bırakılmış.",
        )

    return user


async def get_current_user_optional(
    token: str = Depends(oauth2_scheme),
) -> dict | None:
    """
    Opsiyonel kimlik doğrulama — token yoksa None döner, varsa doğrular.
    Hem giriş yapmış hem yapmamış kullanıcılara açık endpoint'ler için.
    """
    if token is None:
        return None
    try:
        return await get_current_user(token)
    except HTTPException:
        return None


async def require_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Admin yetkisi kontrolü — sadece role='admin' olan kullanıcılar geçer.

    Kullanım:
        @app.get("/admin/dashboard")
        async def admin_dashboard(admin = Depends(require_admin)):
            return {"admin": admin}

    Raises:
        401 Unauthorized: Token eksik veya geçersiz (get_current_user tarafından)
        403 Forbidden: Kullanıcı admin değil
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu endpoint'e erişim yalnızca admin kullanıcılara açıktır.",
        )
    return current_user
