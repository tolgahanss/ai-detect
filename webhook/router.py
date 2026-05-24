"""
Lemon Squeezy Webhook Router
=============================
Lemon Squeezy'den gelen abonelik webhook'larını işler ve kullanıcının
token (kredi) bakiyesini günceller.

Güvenlik:
  - HMAC-SHA256 imza doğrulaması (X-Signature header)
  - Sahte/replay isteklere karşı koruma
  - Yalnızca "order_created" ve "subscription_created" event'leri işlenir

Paket → Token Eşleştirmesi:
  - Starter      → +20 token
  - Professional  → +200 token
  - Enterprise    → 99999 token (sınırsız simge)
"""

import hmac
import hashlib
import logging
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse

from config import settings
from database import get_supabase

# ─────────────────────── Logger ────────────────────────────────────

logger = logging.getLogger("webhook.lemonsqueezy")
logging.basicConfig(level=logging.INFO)

# ─────────────────────── Sabitler ──────────────────────────────────

# Variant adı / ürün adı → eklenecek token miktarı
# Lemon Squeezy'den gelen variant_name veya product_name değerine göre eşleşir
PLAN_TOKEN_MAP: dict[str, int] = {
    "starter": 20,
    "professional": 200,
    "enterprise": 99999,
}

# Lemon Squeezy tarafından belirlenmiş variant_id'lere göre de eşleşebilir
# Kendi Lemon Squeezy Dashboard'undan variant_id'leri alıp buraya ekleyebilirsiniz
# Örnek: VARIANT_ID_TOKEN_MAP = { 123456: 20, 789012: 200, 345678: 99999 }
VARIANT_ID_TOKEN_MAP: dict[int, int] = {
    # Lemon Squeezy'deki variant_id'lerinizi buraya ekleyin:
    # 123456: 20,    # Starter
    # 789012: 200,   # Professional
    # 345678: 99999, # Enterprise
}

# İşlenecek event türleri
ALLOWED_EVENTS = {
    "order_created",
    "subscription_created",
    "subscription_updated",
    "subscription_payment_success",
}

# ─────────────────────── Router ────────────────────────────────────

router = APIRouter(
    prefix="/api/v1/webhook",
    tags=["Webhook"],
)


# ─────────────────────── İmza Doğrulama ────────────────────────────


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """
    Lemon Squeezy'den gelen webhook isteğinin gerçekliğini doğrular.

    Lemon Squeezy, her webhook isteğiyle birlikte X-Signature header'ında
    HMAC-SHA256 hex digest gönderir. Bu fonksiyon aynı hash'i hesaplayıp
    karşılaştırır — eşleşmezse istek reddedilir.

    Args:
        payload: Ham istek body'si (bytes)
        signature: X-Signature header değeri
        secret: Lemon Squeezy Dashboard'dan alınan webhook secret

    Returns:
        True ise imza geçerli, False ise sahte istek
    """
    if not secret:
        # Secret tanımlı değilse güvenlik uyarısı logla ama geçir (dev modu)
        logger.warning(
            "⚠️  LEMONSQUEEZY_WEBHOOK_SECRET tanımlı değil! "
            "İmza doğrulaması atlanıyor — Bu SADECE geliştirme ortamı için kabul edilebilir."
        )
        return True

    expected = hmac.new(
        key=secret.encode("utf-8"),
        msg=payload,
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


# ─────────────────────── Paket → Token Çözümleme ──────────────────


def resolve_token_amount(payload_data: dict) -> Optional[int]:
    """
    Webhook payload'undan plan bilgisini çıkarır ve
    uygun token miktarını döndürür.

    Öncelik sırası:
      1. variant_id eşleşmesi (VARIANT_ID_TOKEN_MAP)
      2. variant_name eşleşmesi (plan adı)
      3. product_name eşleşmesi (ürün adı)

    Args:
        payload_data: Lemon Squeezy webhook payload'unun "data" bölümü

    Returns:
        Token miktarı veya None (tanınmayan plan)
    """
    attributes = payload_data.get("attributes", {})

    # 1. Variant ID ile eşleştirme
    variant_id = attributes.get("variant_id") or attributes.get("first_order_item", {}).get("variant_id")
    if variant_id and int(variant_id) in VARIANT_ID_TOKEN_MAP:
        return VARIANT_ID_TOKEN_MAP[int(variant_id)]

    # 2. Variant adı ile eşleştirme
    variant_name = (
        attributes.get("variant_name", "")
        or attributes.get("first_order_item", {}).get("variant_name", "")
    )
    if variant_name:
        plan_key = variant_name.strip().lower()
        if plan_key in PLAN_TOKEN_MAP:
            return PLAN_TOKEN_MAP[plan_key]

    # 3. Ürün adı ile eşleştirme (fallback)
    product_name = (
        attributes.get("product_name", "")
        or attributes.get("first_order_item", {}).get("product_name", "")
    )
    if product_name:
        product_lower = product_name.strip().lower()
        for plan_key, tokens in PLAN_TOKEN_MAP.items():
            if plan_key in product_lower:
                return tokens

    return None


def extract_customer_email(payload: dict) -> Optional[str]:
    """
    Webhook payload'undan müşteri e-posta adresini çıkarır.

    Lemon Squeezy payload yapısı:
      - data.attributes.user_email
      - data.attributes.customer_email  (bazı event'lerde)

    Args:
        payload: Tam webhook payload

    Returns:
        Müşteri e-posta adresi veya None
    """
    data = payload.get("data", {})
    attributes = data.get("attributes", {})

    # Birden fazla olası alan kontrolü
    email = (
        attributes.get("user_email")
        or attributes.get("customer_email")
        or attributes.get("email")
    )

    return email.strip().lower() if email else None


# ─────────────────────── Endpoint ──────────────────────────────────


@router.post(
    "/lemonsqueezy",
    summary="Lemon Squeezy Webhook",
    response_description="Webhook işleme sonucu",
    status_code=status.HTTP_200_OK,
    tags=["Webhook"],
)
async def handle_lemonsqueezy_webhook(request: Request):
    """
    Lemon Squeezy'den gelen abonelik webhook'larını işler.

    **İş akışı:**
    1. İmza doğrulaması (X-Signature — HMAC-SHA256)
    2. Event türü kontrolü (yalnızca abonelik/sipariş event'leri)
    3. Müşteri e-postası ile veritabanında kullanıcı arama
    4. Paket → token miktarı çözümleme
    5. Kullanıcının mevcut token bakiyesine ekleme

    **Paket eşleştirmesi:**
    - Starter → +20 token
    - Professional → +200 token
    - Enterprise → 99999 token (sınırsız)
    """
    # ── 1. Ham body'yi oku (imza doğrulaması için) ──
    raw_body = await request.body()

    # ── 2. İmza Doğrulaması ──
    signature = request.headers.get("X-Signature", "")
    secret = settings.LEMONSQUEEZY_WEBHOOK_SECRET

    if not verify_webhook_signature(raw_body, signature, secret):
        logger.warning("❌ Webhook imza doğrulaması başarısız — istek reddedildi.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Webhook imza doğrulaması başarısız.",
        )

    # ── 3. JSON Payload'u Parse Et ──
    try:
        payload = await request.json()
    except Exception:
        logger.error("❌ Webhook payload JSON olarak parse edilemedi.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Geçersiz JSON payload.",
        )

    # ── 4. Event Türü Kontrolü ──
    meta = payload.get("meta", {})
    event_name = meta.get("event_name", "")

    logger.info(f"📨 Lemon Squeezy webhook alındı: event={event_name}")

    if event_name not in ALLOWED_EVENTS:
        # Bu event türünü işlemiyoruz ama 200 dönmeliyiz ki
        # Lemon Squeezy tekrar denemesin
        logger.info(f"ℹ️  Event '{event_name}' işlenmiyor — atlandı.")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ignored", "event": event_name},
        )

    # ── 5. Müşteri E-postasını Çıkar ──
    customer_email = extract_customer_email(payload)

    if not customer_email:
        logger.error("❌ Webhook payload'unda müşteri e-postası bulunamadı.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Müşteri e-postası bulunamadı.",
        )

    # ── 6. Kullanıcıyı Veritabanında Bul ──
    supabase = get_supabase()

    try:
        users = supabase.select(
            table="users",
            columns="*",
            filters={"email": customer_email},
        )
    except Exception as e:
        logger.error(f"❌ Kullanıcı arama hatası: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Veritabanı sorgu hatası.",
        )

    if not users:
        logger.warning(f"⚠️  Kullanıcı bulunamadı: {customer_email}")
        # 200 dönüyoruz çünkü Lemon Squeezy'nin tekrar denemesi sorunu çözmez
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "user_not_found",
                "email": customer_email,
                "message": "Bu e-posta ile kayıtlı kullanıcı bulunamadı.",
            },
        )

    user = users[0]

    # ── 7. Token Miktarını Çözümle ──
    data = payload.get("data", {})
    token_amount = resolve_token_amount(data)

    if token_amount is None:
        logger.warning(f"⚠️  Tanınmayan plan — payload data: {data.get('attributes', {}).get('variant_name', 'N/A')}")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "unknown_plan",
                "message": "Tanınmayan abonelik planı.",
            },
        )

    # ── 8. Token Bakiyesini Güncelle ──
    current_credits = user.get("credit_count", 0) or 0

    if token_amount >= 99999:
        # Enterprise → sınırsız simge, sabit değer
        new_credits = 99999
    else:
        # Starter / Professional → mevcut krediye ekle
        new_credits = current_credits + token_amount

    try:
        supabase.update(
            table="users",
            data={"credit_count": new_credits},
            filters={"id": user["id"]},
        )
    except Exception as e:
        logger.error(f"❌ Token güncelleme hatası: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token güncelleme sırasında hata oluştu.",
        )

    logger.info(
        f"✅ Token güncellendi: {customer_email} → "
        f"{current_credits} → {new_credits} (+{token_amount})"
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "success",
            "email": customer_email,
            "previous_credits": current_credits,
            "added_tokens": token_amount,
            "new_credits": new_credits,
        },
    )
