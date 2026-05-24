"""
Auth yardımcı fonksiyonlar — Premium kontrol ve erişim yetkilendirme.

Bu modül, kullanıcının premium durumunu ve rapor erişim hakkını
merkezi bir noktadan kontrol eder. Hem main.py hem plagiarism.py
bu fonksiyonları kullanır.
"""

from datetime import datetime, timezone
from typing import Optional


def is_user_premium(user: Optional[dict]) -> bool:
    """
    Kullanıcının aktif premium aboneliği olup olmadığını kontrol eder.

    Şartlar:
      1. is_premium == True olmalı
      2. premium_until None ise (ömür boyu) → True
      3. premium_until dolmamışsa → True
      4. premium_until dolmuşsa → False
    """
    if user is None:
        return False

    if not user.get("is_premium", False):
        return False

    premium_until = user.get("premium_until")

    # premium_until None veya boş ise → ömür boyu premium
    if premium_until is None or premium_until == "":
        return True

    # String ise datetime'a çevir
    if isinstance(premium_until, str):
        try:
            premium_until = datetime.fromisoformat(premium_until.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return True  # Parse edilemezse güvenli tarafta kal

    # Süre kontrolü
    now = datetime.now(timezone.utc)
    return premium_until > now


def can_user_access_full_report(user: Optional[dict]) -> bool:
    """
    Kullanıcının sansürsüz raporu görüp göremeyeceğini belirler.

    Sansürsüz erişim şartları (OR):
      - Kullanıcı aktif premium ise → True
      - Kullanıcının credit_count > 0 ise → True
      - Aksi halde → False (rapor bulanıklaştırılır)
    """
    if user is None:
        return False

    # Premium kullanıcılar her zaman sansürsüz görebilir
    if is_user_premium(user):
        return True

    # Kredisi olan kullanıcılar da sansürsüz görebilir
    credit_count = user.get("credit_count", 0)
    return credit_count > 0
