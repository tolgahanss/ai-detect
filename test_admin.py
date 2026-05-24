"""
Admin paneli guvenlik testleri.
Sunucunun http://localhost:8000 uzerinde calisiyor olmasi gerekir.
"""

import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError

# auth servisinden JWT uretimi
import sys
sys.path.insert(0, ".")
from auth.service import create_access_token

BASE_URL = "http://localhost:8000"


def api(method, path, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(f"{BASE_URL}{path}", headers=headers, method=method)
    try:
        resp = urlopen(req)
        return resp.status, json.loads(resp.read())
    except HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw.decode(errors="replace")}


def test_1_no_token():
    """Token olmadan admin erisimi -> 401"""
    print("[TEST 1] Token olmadan /admin/dashboard...")
    s, d = api("GET", "/admin/dashboard")
    assert s == 401, f"Beklenen 401, alinan {s}"
    print(f"  -> {s} UNAUTHORIZED")
    print("  BASARILI: Yetkisiz erisim engellendi!\n")


def test_2_invalid_token():
    """Gecersiz token -> 401"""
    print("[TEST 2] Gecersiz token ile /admin/dashboard...")
    s, d = api("GET", "/admin/dashboard", token="sahte.token.burada")
    assert s == 401, f"Beklenen 401, alinan {s}"
    print(f"  -> {s} UNAUTHORIZED")
    print("  BASARILI: Gecersiz token reddedildi!\n")


def test_3_normal_user_token():
    """Normal user tokeni -> 403 (admin degil)"""
    print("[TEST 3] Normal user tokeni ile /admin/dashboard...")
    user_token = create_access_token({
        "sub": "fake-user-id",
        "email": "user@test.com",
        "role": "user",
    })
    s, d = api("GET", "/admin/dashboard", token=user_token)
    # 403 bekliyoruz (auth gecer ama role kontrolu basarisiz)
    # VEYA 401 (cunku fake user_id Supabase'de yok)
    assert s in (401, 403), f"Beklenen 401/403, alinan {s}"
    detail = d.get("detail", "")
    print(f"  -> {s}: {detail}")
    print("  BASARILI: Normal kullanici admin paneline erisemedi!\n")


def test_4_admin_users_no_token():
    """Token olmadan /admin/users -> 401"""
    print("[TEST 4] Token olmadan /admin/users...")
    s, d = api("GET", "/admin/users")
    assert s == 401, f"Beklenen 401, alinan {s}"
    print(f"  -> {s} UNAUTHORIZED")
    print("  BASARILI: /admin/users yetkisiz erisim engellendi!\n")


def test_5_upload_still_works():
    """Mevcut upload hala calisiyor mu?"""
    print("[TEST 5] Upload hala calisiyor mu?...")
    boundary = "----TestBoundary12345"
    pdf_content = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj
xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
trailer<</Size 4/Root 1 0 R>>
startxref
190
%%EOF"""
    body = (
        f"------TestBoundary12345\r\n"
        f'Content-Disposition: form-data; name="file"; filename="test.pdf"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + pdf_content + b"\r\n------TestBoundary12345--\r\n"

    req = Request(
        f"{BASE_URL}/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary=----TestBoundary12345"},
        method="POST",
    )
    try:
        resp = urlopen(req)
        s = resp.status
        d = json.loads(resp.read())
    except HTTPError as e:
        s = e.code
        d = json.loads(e.read())

    assert s == 200, f"Beklenen 200, alinan {s}: {d}"
    print(f"  -> {s} OK, upload calisiyor")
    print("  BASARILI!\n")


if __name__ == "__main__":
    print("=" * 60)
    print("  ADMIN PANELI GUVENLIK TESTLERI")
    print("=" * 60 + "\n")

    test_1_no_token()
    test_2_invalid_token()
    test_3_normal_user_token()
    test_4_admin_users_no_token()
    test_5_upload_still_works()

    print("=" * 60)
    print("  TUM ADMIN GUVENLIK TESTLERI BASARILI!")
    print("=" * 60)
