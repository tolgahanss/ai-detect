"""Hızlı birim testi — bcrypt ve JWT fonksiyonlarını doğrular."""

from auth.service import hash_password, verify_password, create_access_token, decode_access_token

# 1. Sifre Hash
print("[1] bcrypt hash testi...")
pw_hash = hash_password("GucluSifre123")
print(f"    Hash: {pw_hash[:40]}...")
assert pw_hash.startswith("$2b$"), "bcrypt hash formatı yanlış!"
print("    OK")

# 2. Sifre Dogrulama
print("[2] bcrypt verify testi...")
assert verify_password("GucluSifre123", pw_hash), "Doğru şifre doğrulanamadı!"
assert not verify_password("YanlisSifre", pw_hash), "Yanlış şifre doğrulandı!"
print("    OK")

# 3. JWT Token Uretimi
print("[3] JWT token uretim testi...")
token = create_access_token({"sub": "test-user-id", "email": "test@example.com"})
print(f"    Token: {token[:50]}...")
assert len(token) > 50, "Token çok kısa!"
print("    OK")

# 4. JWT Token Cozme
print("[4] JWT token cozme testi...")
decoded = decode_access_token(token)
assert decoded["sub"] == "test-user-id", "sub claim yanlış!"
assert decoded["email"] == "test@example.com", "email claim yanlış!"
assert "exp" in decoded, "exp claim eksik!"
assert "iat" in decoded, "iat claim eksik!"
print(f"    sub: {decoded['sub']}, email: {decoded['email']}")
print("    OK")

# 5. Gecersiz Token
print("[5] Gecersiz token testi...")
import jwt as pyjwt
try:
    decode_access_token("gecersiz.token.burada")
    assert False, "Gecersiz token kabul edildi!"
except pyjwt.InvalidTokenError:
    print("    Gecersiz token reddedildi - OK")

print("\nTum birim testleri basarili!")
