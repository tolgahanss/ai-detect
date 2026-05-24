"""
Auth sistemi testleri.
Sunucunun http://localhost:8000 üzerinde çalışıyor olması gerekir.

Test senaryoları:
  1. Kullanıcı kaydı (başarılı)
  2. Aynı email ile tekrar kayıt (başarısız → 400)
  3. Giriş (başarılı → JWT token)
  4. Yanlış şifre ile giriş (başarısız → 401)
  5. JWT ile profil erişimi (başarılı → 200)
  6. Geçersiz token ile erişim (başarısız → 401)
  7. SQL Injection denemesi (başarısız → güvenli)
"""

import json
import random
import string
from urllib.request import Request, urlopen
from urllib.error import HTTPError


BASE_URL = "http://localhost:8000"


def _random_suffix(length: int = 6) -> str:
    """Benzersiz test verisi icin rastgele suffix."""
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def api_request(
    method: str,
    path: str,
    data: dict = None,
    token: str = None,
) -> tuple:
    """JSON API istegi gonderir."""
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}

    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = json.dumps(data).encode() if data else None
    req = Request(url, data=body, headers=headers, method=method)

    try:
        resp = urlopen(req)
        return resp.status, json.loads(resp.read())
    except HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw.decode(errors="replace")}


# ═══════════════════════════════════════════════════════════
# TEST SENARYOLARI
# ═══════════════════════════════════════════════════════════

_suffix = _random_suffix()
TEST_EMAIL = f"test_{_suffix}@example.com"
TEST_USERNAME = f"testuser_{_suffix}"
TEST_PASSWORD = "GucluSifre123"
TEST_FULLNAME = "Test Kullanicisi"


def test_1_register_success():
    """1. Basarili kullanici kaydi"""
    print("[TEST 1] Kullanici kaydi...")
    status_code, data = api_request("POST", "/auth/register", {
        "email": TEST_EMAIL,
        "username": TEST_USERNAME,
        "password": TEST_PASSWORD,
        "full_name": TEST_FULLNAME,
    })
    assert status_code == 201, f"  Beklenen 201, alinan {status_code}: {data}"
    assert "access_token" in data, "  Token donmedi!"
    assert data["user"]["email"] == TEST_EMAIL
    assert data["user"]["username"] == TEST_USERNAME
    # Sifre donmedigini dogrula
    assert "hashed_password" not in str(data["user"])
    print(f"  -> 201 CREATED, token alindi")
    print(f"  -> Kullanici: {data['user']['username']}")
    print("  BASARILI!\n")
    return data["access_token"]


def test_2_register_duplicate():
    """2. Ayni email ile tekrar kayit → 400"""
    print("[TEST 2] Duplicate kayit denemesi...")
    status_code, data = api_request("POST", "/auth/register", {
        "email": TEST_EMAIL,
        "username": f"baska_{_suffix}",
        "password": TEST_PASSWORD,
    })
    assert status_code == 400, f"  Beklenen 400, alinan {status_code}: {data}"
    print(f"  -> 400 BAD REQUEST: {data.get('detail', '')}")
    print("  BASARILI!\n")


def test_3_login_success():
    """3. Basarili giris → JWT token"""
    print("[TEST 3] Basarili giris...")
    status_code, data = api_request("POST", "/auth/login", {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
    })
    assert status_code == 200, f"  Beklenen 200, alinan {status_code}: {data}"
    assert "access_token" in data, "  Token donmedi!"
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0
    print(f"  -> 200 OK, JWT token alindi")
    print(f"  -> Token suresi: {data['expires_in']}s")
    print("  BASARILI!\n")
    return data["access_token"]


def test_4_login_wrong_password():
    """4. Yanlis sifre → 401"""
    print("[TEST 4] Yanlis sifre ile giris...")
    status_code, data = api_request("POST", "/auth/login", {
        "email": TEST_EMAIL,
        "password": "YanlisSifre999",
    })
    assert status_code == 401, f"  Beklenen 401, alinan {status_code}: {data}"
    print(f"  -> 401 UNAUTHORIZED: {data.get('detail', '')}")
    print("  BASARILI!\n")


def test_5_profile_with_token(token: str):
    """5. JWT token ile profil erisimi → 200"""
    print("[TEST 5] Token ile profil erisimi...")
    status_code, data = api_request("GET", "/auth/me", token=token)
    assert status_code == 200, f"  Beklenen 200, alinan {status_code}: {data}"
    assert data["email"] == TEST_EMAIL
    assert data["username"] == TEST_USERNAME
    # Sifre donmedigini dogrula
    assert "hashed_password" not in str(data)
    assert "password" not in str(data)
    print(f"  -> 200 OK, profil alindi")
    print(f"  -> Email: {data['email']}, Rol: {data['role']}")
    print("  BASARILI!\n")


def test_6_invalid_token():
    """6. Gecersiz token → 401"""
    print("[TEST 6] Gecersiz token ile erisim...")
    status_code, data = api_request(
        "GET", "/auth/me",
        token="gecersiz.token.burada",
    )
    assert status_code == 401, f"  Beklenen 401, alinan {status_code}: {data}"
    print(f"  -> 401 UNAUTHORIZED: {data.get('detail', '')}")
    print("  BASARILI!\n")


def test_7_sql_injection():
    """7. SQL Injection denemeleri — hepsi basarisiz olmali"""
    print("[TEST 7] SQL Injection denemeleri...")
    
    payloads = [
        {"email": "' OR 1=1 --", "password": "test"},
        {"email": "admin@test.com' OR '1'='1", "password": "test"},
        {"email": "test@test.com", "password": "' OR 1=1 --"},
        {"email": "'; DROP TABLE users; --", "password": "test"},
        {"email": "test@test.com\" OR \"\"=\"", "password": "test"},
    ]
    
    for i, payload in enumerate(payloads, 1):
        status_code, data = api_request("POST", "/auth/login", payload)
        # 422 (validation error) veya 401 (unauthorized) donmeli, asla 200 donmemeli
        assert status_code in (401, 422), (
            f"  Payload {i}: TEHLIKE! Beklenen 401/422, alinan {status_code}"
        )
        print(f"  Payload {i}: '{payload['email'][:30]}...' -> {status_code} (guvenli)")
    
    print("  BASARILI! Tum SQL Injection denemeleri engellendi.\n")


# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  KIMLIK DOGRULAMA SISTEMI TESTLERI")
    print("=" * 60 + "\n")

    # 1. Kayit
    token_from_register = test_1_register_success()

    # 2. Duplicate kayit
    test_2_register_duplicate()

    # 3. Giris
    token_from_login = test_3_login_success()

    # 4. Yanlis sifre
    test_4_login_wrong_password()

    # 5. Token ile profil
    test_5_profile_with_token(token_from_login)

    # 6. Gecersiz token
    test_6_invalid_token()

    # 7. SQL Injection
    test_7_sql_injection()

    print("=" * 60)
    print("  TUM AUTH TESTLERI BASARILI!")
    print("=" * 60)
