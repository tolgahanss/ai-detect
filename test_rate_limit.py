"""
Rate Limiting testleri.
Sunucunun http://localhost:8000 üzerinde çalışıyor olması gerekir.
"""

import json
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError


BASE_URL = "http://localhost:8000"


def simple_get(path: str) -> tuple:
    """Basit GET isteği gönderir."""
    req = Request(f"{BASE_URL}{path}", method="GET")
    try:
        resp = urlopen(req)
        return resp.status, json.loads(resp.read())
    except HTTPError as e:
        return e.code, json.loads(e.read()) if e.read() else {}


def simple_post_json(path: str, data: dict) -> tuple:
    """JSON body ile POST isteği gönderir."""
    body = json.dumps(data).encode()
    req = Request(
        f"{BASE_URL}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = urlopen(req)
        return resp.status, json.loads(resp.read())
    except HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"raw": body.decode(errors="replace")}


def test_login_rate_limit():
    """Login endpoint: 6. istek 429 donmeli (dakikada maks. 5)"""
    print("[TEST] /login rate limit (5/dakika)...")
    
    for i in range(5):
        status, _ = simple_post_json("/login", {"username": "test", "password": "1234"})
        assert status == 200, f"  Istek {i+1}: Beklenen 200, alinan {status}"
        print(f"  Istek {i+1}/5 -> {status} OK")

    # 6. istek 429 Too Many Requests donmeli
    status, data = simple_post_json("/login", {"username": "test", "password": "1234"})
    assert status == 429, f"  6. istek: Beklenen 429, alinan {status}"
    print(f"  Istek 6/5 -> {status} RATE LIMITED")
    print("  BASARILI: /login rate limiting calisiyor!\n")


def test_home_endpoint():
    """Ana sayfa endpoint'inin calistigini dogrular"""
    print("[TEST] / ana sayfa endpoint...")
    status, data = simple_get("/")
    assert status == 200, f"Beklenen 200, alinan {status}"
    assert "rate_limits" in data
    print(f"  -> {status} OK, rate_limits bilgisi mevcut")
    print("  BASARILI: Ana sayfa calisiyor!\n")


def test_health_exempt():
    """Health endpoint rate limit'ten muaf olmali"""
    print("[TEST] /health (rate limit muaf)...")
    for i in range(10):
        status, _ = simple_get("/health")
        assert status == 200, f"  Istek {i+1}: Beklenen 200, alinan {status}"
    print(f"  -> 10 istek basarili, rate limit yok")
    print("  BASARILI: /health rate limit'ten muaf!\n")


if __name__ == "__main__":
    print("=" * 55)
    print("  RATE LIMITING TESTLERI")
    print("=" * 55 + "\n")
    
    test_home_endpoint()
    test_health_exempt()
    test_login_rate_limit()
    
    print("=" * 55)
    print("  TUM TESTLER BASARILI!")
    print("=" * 55)
