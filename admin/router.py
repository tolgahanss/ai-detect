"""
Admin Panel Router — Sadece admin yetkisine sahip kullanıcılar erişebilir.

Güvenlik:
  - JWT token zorunlu (Authorization: Bearer <token>)
  - Token'daki kullanıcının role='admin' olması zorunlu
  - Yetkisiz erişimde 401/403 döner — hiçbir veri sızmaz
  - Tüm veritabanı sorguları Supabase PostgREST ile parametrize → SQL Injection imkansız
  - Rate limiting aktif (IP başına dakikada 10 istek)
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from auth.dependencies import require_admin
from database import get_supabase


router = APIRouter(
    prefix="/admin",
    tags=["Admin Paneli"],
)


# ─────────────────────── Yardımcı Fonksiyonlar ─────────────────────


def _get_today_start() -> str:
    """Bugünün UTC başlangıç zamanını ISO 8601 formatında döndürür."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT00:00:00+00:00")


def _safe_db_call(func, default=None):
    """
    Veritabanı çağrısını güvenli şekilde yapar.
    Tablo yoksa veya hata olursa varsayılan değeri döndürür.
    """
    try:
        return func()
    except Exception:
        return default


# ─────────────────────── Admin Dashboard ───────────────────────────


@router.get(
    "/dashboard",
    summary="Admin paneli — genel istatistikler",
    response_description="Sistem istatistikleri JSON formatında",
    status_code=status.HTTP_200_OK,
)
async def admin_dashboard(
    request: Request,
    admin_user: dict = Depends(require_admin),
):
    """
    **🔒 Admin Panel — Sistem İstatistikleri**

    Bu endpoint'e sadece `role='admin'` olan kullanıcılar erişebilir.

    **Döndürdüğü veriler:**
    - Toplam üye sayısı
    - Bugün yapılan toplam tarama sayısı
    - LemonSqueezy üzerinden gelen toplam ciro
    - Kredisi biten kullanıcıların listesi

    **Güvenlik kontrolleri:**
    1. JWT token doğrulama (geçerli + süresi dolmamış)
    2. Kullanıcının veritabanında mevcut ve aktif olması
    3. role='admin' kontrolü
    4. Rate limiting (IP başına 10 istek/dk)
    """
    supabase = get_supabase()

    # ── 1. Toplam Üye Sayısı ──
    total_users = _safe_db_call(
        lambda: supabase.count("users"),
        default=0,
    )

    # ── 2. Aktif Üye Sayısı ──
    active_users = _safe_db_call(
        lambda: supabase.count("users", filters={"is_active": True}),
        default=0,
    )

    # ── 3. Bugün Yapılan Tarama Sayısı ──
    today_start = _get_today_start()
    today_scans = _safe_db_call(
        lambda: supabase.count(
            "scans",
            filters={"created_at": ("gte", today_start)},
        ),
        default=0,
    )

    # ── 4. Toplam Tarama Sayısı (Tüm zamanlar) ──
    total_scans = _safe_db_call(
        lambda: supabase.count("scans"),
        default=0,
    )

    # ── 5. LemonSqueezy Toplam Ciro ──
    total_revenue = _safe_db_call(
        lambda: _calculate_total_revenue(supabase),
        default=0.0,
    )

    # ── 6. Kredisi Biten Kullanıcılar ──
    zero_credit_users = _safe_db_call(
        lambda: supabase.select_with_filters(
            table="user_credits",
            columns="user_id, credits, users(email, username, full_name)",
            raw_filters={"credits": "lte.0"},
        ),
        default=[],
    )

    # ── 7. Son 5 Ödeme ──
    recent_payments = _safe_db_call(
        lambda: _get_recent_payments(supabase, limit=5),
        default=[],
    )

    return JSONResponse(
        content={
            "dashboard": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "admin": {
                    "id": admin_user["id"],
                    "email": admin_user["email"],
                    "username": admin_user["username"],
                },
            },
            "users": {
                "total": total_users,
                "active": active_users,
                "inactive": total_users - active_users,
            },
            "scans": {
                "today": today_scans,
                "total": total_scans,
            },
            "revenue": {
                "total_usd": total_revenue,
                "source": "LemonSqueezy",
            },
            "zero_credit_users": [
                {
                    "user_id": u.get("user_id"),
                    "credits": u.get("credits", 0),
                    "email": u.get("users", {}).get("email", "N/A")
                        if isinstance(u.get("users"), dict) else "N/A",
                    "username": u.get("users", {}).get("username", "N/A")
                        if isinstance(u.get("users"), dict) else "N/A",
                    "full_name": u.get("users", {}).get("full_name")
                        if isinstance(u.get("users"), dict) else None,
                }
                for u in (zero_credit_users or [])
            ],
            "recent_payments": recent_payments,
        }
    )


# ─────────────────────── Ciro Hesaplama ────────────────────────────


def _calculate_total_revenue(supabase) -> float:
    """
    LemonSqueezy'den gelen toplam ciroyu hesaplar.

    payments tablosundaki status='paid' olan kayıtların
    amount_usd toplamını döndürür.
    """
    payments = supabase.select_with_filters(
        table="payments",
        columns="amount_usd",
        raw_filters={"status": "eq.paid"},
    )
    return round(sum(p.get("amount_usd", 0) for p in payments), 2)


def _get_recent_payments(supabase, limit: int = 5) -> list:
    """Son N ödemeyi getirir (en yeniden en eskiye)."""
    payments = supabase.select_with_filters(
        table="payments",
        columns="id, user_id, amount_usd, currency, status, provider, created_at, "
                "users(email, username)",
        raw_filters={"order": "created_at.desc", "limit": str(limit)},
    )
    return [
        {
            "id": p.get("id"),
            "user_id": p.get("user_id"),
            "amount_usd": p.get("amount_usd"),
            "currency": p.get("currency", "USD"),
            "status": p.get("status"),
            "provider": p.get("provider"),
            "created_at": p.get("created_at"),
            "email": p.get("users", {}).get("email", "N/A")
                if isinstance(p.get("users"), dict) else "N/A",
        }
        for p in (payments or [])
    ]


# ─────────────────────── Kullanıcı Listesi ─────────────────────────


@router.get(
    "/users",
    summary="Tüm kullanıcı listesi (admin)",
    status_code=status.HTTP_200_OK,
)
async def list_users(
    request: Request,
    admin_user: dict = Depends(require_admin),
):
    """
    **🔒 Admin Only** — Sistemdeki tüm kullanıcıları listeler.
    Şifre bilgisi asla döndürülmez.
    """
    supabase = get_supabase()

    users = _safe_db_call(
        lambda: supabase.select(
            table="users",
            columns="id, email, username, full_name, is_active, role, created_at",
        ),
        default=[],
    )

    return JSONResponse(
        content={
            "total": len(users),
            "users": users,
        }
    )
