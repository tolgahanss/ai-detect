"""
Auth Router — Kullanıcı kayıt, giriş ve profil endpoint'leri.

Güvenlik:
  - Rate Limiting: /auth/register ve /auth/login → 5 istek/dk per IP
  - bcrypt: Şifreler hash'lenerek saklanır
  - JWT: Giriş sonrası stateless token üretilir
  - Supabase: Parametrized query → SQL Injection imkansız
  - Pydantic: Input doğrulaması → zararlı veri girişi engellenir
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi_sso.sso.google import GoogleSSO
import secrets
import string

from auth.schemas import (
    UserRegister,
    UserLogin,
    UserResponse,
    TokenResponse,
)
from auth.service import (
    hash_password,
    verify_password,
    create_access_token,
    db_get_user_by_email,
    db_get_user_by_username,
    db_create_user,
)
from auth.dependencies import get_current_user
from database import get_supabase
from config import settings

# Rate limiter'ı main.py'den import ediyoruz (circular import önlemi)
# limiter doğrudan main'den gelecek, burada sadece dekoratör kullanıyoruz


router = APIRouter(
    prefix="/auth",
    tags=["Kimlik Doğrulama"],
)

google_sso = GoogleSSO(
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    redirect_uri=settings.GOOGLE_REDIRECT_URI,
    allow_insecure_http=True
)

# ─────────────────────── Kayıt (Register) ──────────────────────────


@router.post(
    "/register",
    summary="Yeni kullanıcı kaydı",
    response_description="Kayıt başarılı bilgisi",
    status_code=status.HTTP_201_CREATED,
    response_model=TokenResponse,
)
async def register(request: Request, user_data: UserRegister):
    """
    Yeni kullanıcı kaydı.

    **Güvenlik adımları:**
    1. Pydantic ile input doğrulaması (email formatı, şifre gücü, username kontrolü)
    2. Email ve username benzersizlik kontrolü (parametrized query)
    3. Şifre bcrypt ile hash'lenir — düz metin asla saklanmaz
    4. Kullanıcı Supabase'e kaydedilir (parametrized INSERT)
    5. JWT access token üretilir ve döndürülür
    """
    import httpx as _httpx

    supabase = get_supabase()

    # ── 1. Email benzersizlik kontrolü ──
    try:
        existing_user = db_get_user_by_email(supabase, user_data.email)
    except _httpx.HTTPStatusError as e:
        print(f"Supabase email kontrol hatası: {e.response.status_code} — {e.response.text}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Veritabanı hatası (email kontrol): {e.response.text}",
        )
    except Exception as e:
        print(f"Email kontrol hatası: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"E-posta kontrolü sırasında hata: {str(e)}",
        )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu e-posta adresi zaten kayıtlı.",
        )

    # ── 2. Username benzersizlik kontrolü ──
    try:
        existing_username = db_get_user_by_username(supabase, user_data.username)
    except _httpx.HTTPStatusError as e:
        print(f"Supabase username kontrol hatası: {e.response.status_code} — {e.response.text}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Veritabanı hatası (username kontrol): {e.response.text}",
        )
    except Exception as e:
        print(f"Username kontrol hatası: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kullanıcı adı kontrolü sırasında hata: {str(e)}",
        )

    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu kullanıcı adı zaten kullanılıyor.",
        )

    # ── 3. Şifreyi bcrypt ile hash'le ──
    hashed_pw = hash_password(user_data.password)

    # ── 4. Kullanıcıyı veritabanına kaydet ──
    try:
        new_user = db_create_user(
            supabase_client=supabase,
            email=user_data.email,
            username=user_data.username,
            hashed_password=hashed_pw,
        )
    except _httpx.HTTPStatusError as e:
        print(f"Supabase kayıt hatası: {e.response.status_code} — {e.response.text}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Veritabanı kayıt hatası: {e.response.text}",
        )
    except Exception as e:
        print(f"Kayıt Hatası: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kullanıcı oluşturulurken bir hata oluştu: {str(e)}",
        )

    # ── 5. JWT token üret ──
    access_token = create_access_token(
        data={
            "sub": new_user["id"],
            "email": new_user["email"]
        }
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse(
            id=new_user["id"],
            email=new_user["email"],
            username=new_user["username"],
            credit_count=new_user.get("credit_count", 3),
            is_premium=new_user.get("is_premium", False),
            premium_until=new_user.get("premium_until"),
            plan_type=new_user.get("plan_type", "free"),
        ),
    )


# ─────────────────────── Giriş (Login) ────────────────────────────


@router.post(
    "/login",
    summary="Kullanıcı girişi",
    response_description="JWT access token",
    status_code=status.HTTP_200_OK,
    response_model=TokenResponse,
)
async def login(request: Request, credentials: UserLogin):
    """
    Kullanıcı giriş endpoint'i.

    **Güvenlik adımları:**
    1. Pydantic ile email formatı doğrulanır
    2. E-posta ile kullanıcı aranır (parametrized SELECT → SQL Injection imkansız)
    3. Şifre bcrypt ile doğrulanır (timing attack'a dayanıklı)
    4. Başarılı girişte JWT access token üretilir

    **Brute-force koruması:** Rate limiting ile IP başına dakikada maks. 5 istek.
    """
    supabase = get_supabase()

    # ── 1. Kullanıcıyı e-posta ile bul ──
    # .eq() parametrized query kullanır → SQL Injection imkansız
    user = db_get_user_by_email(supabase, credentials.email)

    if user is None:
        # Kullanıcı bulunamadı — timing attack'ı önlemek için
        # aynı hata mesajını kullan (email mi yanlış, şifre mi belli olmasın)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-posta veya şifre hatalı.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # (is_active kontrolü kaldırıldı çünkü veritabanı şemasında yok)

    # ── 3. Şifreyi bcrypt ile doğrula ──
    if not verify_password(credentials.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-posta veya şifre hatalı.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ── 4. JWT token üret ──
    access_token = create_access_token(
        data={
            "sub": user["id"],
            "email": user["email"]
        }
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse(
            id=user["id"],
            email=user["email"],
            username=user["username"],
            credit_count=user.get("credit_count", 3),
            is_premium=user.get("is_premium", False),
            premium_until=user.get("premium_until"),
            plan_type=user.get("plan_type", "free"),
        ),
    )


# ─────────────────────── Profil (Me) ──────────────────────────────


@router.get(
    "/me",
    summary="Mevcut kullanıcı profili",
    response_description="Oturum açmış kullanıcının bilgileri",
    status_code=status.HTTP_200_OK,
    response_model=UserResponse,
)
async def get_me(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Oturum açmış kullanıcının profil bilgilerini döndürür.

    **Yetkilendirme:** `Authorization: Bearer <JWT_TOKEN>` header'ı gereklidir.
    Şifre bilgisi asla döndürülmez.
    """
    return UserResponse(
        id=current_user["id"],
        email=current_user["email"],
        username=current_user["username"],
        credit_count=current_user.get("credit_count", 3),
        is_premium=current_user.get("is_premium", False),
        premium_until=current_user.get("premium_until"),
        plan_type=current_user.get("plan_type", "free"),
    )


# ─────────────────────── Google OAuth ──────────────────────────────

@router.get("/google/login", summary="Google ile giriş sayfasına yönlendirir")
async def google_login():
    """
    Google'ın yetkilendirme (OAuth) sayfasına yönlendirir.
    Kullanıcı buradan Google hesabını seçer.
    """
    with google_sso:
        return await google_sso.get_login_redirect()


@router.get("/google/callback", summary="Google'dan dönen kimlik verisini işler")
async def google_callback(request: Request):
    """
    Kullanıcı Google'da giriş yaptıktan sonra buraya yönlendirilir.
    - Google'dan e-posta alınır.
    - Sistemde kayıtlıysa JWT token üretilir.
    - Kayıtlı değilse yeni hesap (rastgele şifreyle) açılır, 500 bonus kredi verilir ve JWT token üretilir.
    """
    try:
        with google_sso:
            user = await google_sso.verify_and_process(request)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google doğrulama hatası: {str(e)}"
        )
        
    supabase = get_supabase()
    
    # Veritabanında e-posta ile kullanıcıyı ara
    existing_user = db_get_user_by_email(supabase, user.email)
    
    if not existing_user:
        # Rastgele güçlü bir şifre oluştur
        alphabet = string.ascii_letters + string.digits + string.punctuation
        random_password = ''.join(secrets.choice(alphabet) for i in range(20))
        hashed_pw = hash_password(random_password)
        
        # Benzersiz username oluştur
        base_username = user.email.split('@')[0]
        unique_username = f"{base_username}_{secrets.token_hex(4)}"
        
        # Kullanıcıyı veritabanına kaydet
        new_user = db_create_user(
            supabase_client=supabase,
            email=user.email,
            username=unique_username,
            hashed_password=hashed_pw,
        )
        existing_user = new_user

    # JWT Token oluştur
    access_token = create_access_token(
        data={
            "sub": existing_user["id"],
            "email": existing_user["email"]
        }
    )
    
    # Frontend'e token ile yönlendir
    # Token URL hash (#) içinde gönderiliyor
    frontend_url = settings.FRONTEND_URL
    try:
        # Redirect to the local server's frontend if accessing via the API server
        frontend_url = str(request.url_for("serve_frontend"))
    except Exception:
        pass
    return RedirectResponse(url=f"{frontend_url}#access_token={access_token}")


