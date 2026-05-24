"""
Upload endpoint için otomatik testler.
Doğrudan çalıştırılarak veya pytest ile kullanılabilir.
Sunucunun http://localhost:8000 üzerinde çalışıyor olması gerekir.
"""

import io
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError


BASE_URL = "http://localhost:8000"


def multipart_upload(filename: str, content: bytes, field_name: str = "file") -> tuple[int, dict]:
    """Basit multipart/form-data POST isteği gönderir (requests olmadan)."""
    boundary = "----TestBoundary12345"
    body = (
        f"------TestBoundary12345\r\n"
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + content + b"\r\n------TestBoundary12345--\r\n"

    req = Request(
        f"{BASE_URL}/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary=----TestBoundary12345"},
        method="POST",
    )
    try:
        resp = urlopen(req)
        return resp.status, json.loads(resp.read())
    except HTTPError as e:
        return e.code, json.loads(e.read())


def test_invalid_extension():
    """Geçersiz uzantı → 400"""
    status, data = multipart_upload("malware.exe", b"MZ\x90\x00" * 10)
    assert status == 400, f"Beklenen 400, alınan {status}"
    assert "uzantı" in data["detail"].lower() or "uzantısı" in data["detail"].lower()
    print("✅ Geçersiz uzantı testi başarılı")


def test_fake_pdf():
    """PDF uzantılı ama içeriği farklı dosya → 400"""
    status, data = multipart_upload("fake.pdf", b"This is not a real PDF file content at all")
    assert status == 400, f"Beklenen 400, alınan {status}"
    assert "mime" in data["detail"].lower() or "eşleşmiyor" in data["detail"].lower()
    print("✅ Sahte PDF testi başarılı")


def test_valid_pdf():
    """Gerçek minimal PDF → 200"""
    # Minimal geçerli PDF dosyası
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
    status, data = multipart_upload("real.pdf", pdf_content)
    assert status == 200, f"Beklenen 200, alınan {status}: {data}"
    assert data["detected_mime_type"] == "application/pdf"
    print("✅ Geçerli PDF testi başarılı")


def test_oversized_file():
    """20MB'dan büyük dosya → 400"""
    # 21 MB sahte PDF header + padding
    big_content = b"%PDF-1.4\n" + (b"\x00" * (21 * 1024 * 1024))
    status, data = multipart_upload("big.pdf", big_content)
    assert status == 400, f"Beklenen 400, alınan {status}"
    assert "boyut" in data["detail"].lower()
    print("✅ Büyük dosya boyutu testi başarılı")


if __name__ == "__main__":
    print("🔍 Upload testleri çalıştırılıyor...\n")
    test_invalid_extension()
    test_fake_pdf()
    test_valid_pdf()
    # Büyük dosya testi ağ üzerinden yavaş olabilir, isteğe bağlı
    # test_oversized_file()
    print("\n🎉 Tüm testler başarılı!")
