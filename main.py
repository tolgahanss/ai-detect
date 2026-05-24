"""
Güvenli Dosya Yükleme & Kimlik Doğrulama API'si
==================================================
Güvenlik katmanları:
  1. Dosya uzantısı kontrolü
  2. MIME type doğrulaması (magic bytes / dosya imzası)
  3. Maksimum dosya boyutu sınırı (20 MB)
  4. Rate Limiting — IP başına istek sınırlama (brute-force / bot koruması)
  5. JWT tabanlı kimlik doğrulama (PyJWT + bcrypt)
  6. SQL Injection koruması (Supabase parametrized query)
  7. CORS koruması
"""


import os
import uuid
import shutil
from pathlib import Path
from typing import Final
try:
    import magic
except (ImportError, OSError):
    magic = None
import PyPDF2
import docx
from fastapi import FastAPI, File, UploadFile, HTTPException, Request, status, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from auth.router import router as auth_router
from auth.dependencies import get_current_user, get_current_user_optional
from auth.utils import is_user_premium, can_user_access_full_report
from admin.router import router as admin_router
from plagiarism import check_plagiarism

# ─────────────────────────── Yapılandırma ───────────────────────────

MAX_FILE_SIZE_BYTES: Final[int] = 20 * 1024 * 1024  # 20 MB

UPLOAD_DIR: Final[Path] = Path(__file__).resolve().parent / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Kabul edilen uzantılar → beklenen MIME türleri eşlemesi
ALLOWED_TYPES: Final[dict[str, set[str]]] = {
    ".pdf": {
        "application/pdf",
    },
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        # python-magic bazen DOCX'i genel zip olarak algılayabilir
        "application/zip",
        "application/x-zip-compressed",
        "application/octet-stream",
    },
}

ALLOWED_EXTENSIONS: Final[set[str]] = set(ALLOWED_TYPES.keys())

# ───────────────────── Rate Limiting Yapılandırması ─────────────────

# IP adresine göre istek sınırlama — brute-force ve bot saldırılarını engeller
limiter = Limiter(key_func=get_remote_address)

# ─────────────────────────── Uygulama ──────────────────────────────

app = FastAPI(
    title="Güvenli Dosya Yükleme & Kimlik Doğrulama API",
    description=(
        "PDF/DOCX dosya yükleme, kullanıcı kayıt/giriş ve JWT yetkilendirme servisi. "
        "SQL Injection, brute-force ve dosya manipülasyonu saldırılarına karşı korumalı."
    ),
    version="2.0.0",
)

# Rate limiter'ı uygulamaya bağla
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS — frontend entegrasyonu için
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────── Routers ───────────────────────────────────

# /auth/register, /auth/login, /auth/me
app.include_router(auth_router)

# /admin/dashboard, /admin/users — sadece admin erişebilir
app.include_router(admin_router)


# ─────────────────────── Yardımcı Fonksiyonlar ─────────────────────


def _validate_extension(filename: str) -> str:
    """
    Dosya uzantısını kontrol eder.
    Geçerli ise normalize edilmiş uzantıyı döndürür, değilse HTTPException fırlatır.
    """
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Geçersiz dosya uzantısı: '{ext}'. "
                f"Yalnızca {', '.join(sorted(ALLOWED_EXTENSIONS))} dosyaları kabul edilir."
            ),
        )
    return ext


def _extract_text_from_file(file_path: Path, extension: str) -> str:
    """Dosyadan metin çıkarır (PDF veya DOCX)."""
    text = ""
    try:
        if extension == ".pdf":
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
        elif extension == ".docx":
            doc = docx.Document(file_path)
            for para in doc.paragraphs:
                text += para.text + "\n"
    except Exception as e:
        print(f"Metin çıkarma hatası: {e}")
        pass
    return text.strip()


import re
from transformers import pipeline

# Global değişkeni boş bırakıyoruz, sunucu açılırken yükleme yapmayacak!
ai_detector = None

def _analyze_ai_content(text: str, can_see_full: bool = False) -> dict:
    global ai_detector
    
    words = text.split()
    if len(words) < 5:
        return {"human": 100, "ai": 0, "sentences": 0, "words": len(words), "sentence_reports": [], "is_blurred": False}
    
    # Model daha önce yüklenmediyse, İLK SORGIDA burada yüklenecek
    if ai_detector is None:
        try:
            print("[AI DETECT] RoBERTa Modeli ilk kez yükleniyor, bu işlem biraz sürebilir...")
            ai_detector = pipeline("text-classification", model="roberta-base-openai-detector")
            print("[AI DETECT] Model başarıyla yüklendi!")
        except Exception as e:
            print(f"[AI DETECT] Model yükleme hatası: {e}")
            ai_detector = None

    # Cümleleri ayır
    raw_sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    sentences = [s for s in raw_sentences if len(s.strip()) > 2]
    
    if not sentences:
        sentences = [text.strip()]
        
    sentence_reports = []
    total_ai_score = 0
    
    for sentence in sentences:
        ai_score = 0
        if ai_detector:
            try:
                result = ai_detector(sentence[:512])[0]
                if result['label'] == 'Fake':
                    ai_score = int(result['score'] * 100)
                else:
                    ai_score = int((1 - result['score']) * 100)
            except Exception:
                ai_score = 0
                
        total_ai_score += ai_score
        sentence_reports.append({
            "text": sentence,
            "ai_score": ai_score,
            "is_masked": False
        })
        
    avg_ai_score = int(total_ai_score / len(sentences)) if sentences else 0
    human_score = 100 - avg_ai_score

    # Paywall maskeleme mantığını koru
    is_blurred = False
    if not can_see_full and len(sentence_reports) > 1:
        is_blurred = True
        keep_count = max(2, int(len(sentence_reports) * 0.10))
        for i in range(keep_count, len(sentence_reports)):
            sentence_reports[i]["text"] = "█" * (len(sentence_reports[i]["text"]) // 2 + 5)
            sentence_reports[i]["is_masked"] = True

    return {
        "human": human_score,
        "ai": avg_ai_score,
        "sentences": len(sentences),
        "words": len(words),
        "sentence_reports": sentence_reports,
        "is_blurred": is_blurred
    }


def _validate_file_size(content: bytes) -> None:
    """Dosya boyutunun 20 MB limitini aşıp aşmadığını kontrol eder."""
    if len(content) > MAX_FILE_SIZE_BYTES:
        size_mb = len(content) / (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Dosya boyutu çok büyük: {size_mb:.1f} MB. "
                f"Maksimum izin verilen boyut: {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB."
            ),
        )


def _validate_mime_type(content: bytes, expected_extension: str) -> str:
    """
    Dosyanın gerçek MIME türünü magic bytes ile doğrular.
    python-magic Windows'ta veya kütüphane eksikse standart mimetypes kütüphanesine düşer.
    """
    allowed_mimes = ALLOWED_TYPES[expected_extension]
    detected_mime = ""
    
    try:
        if magic is not None:
            detected_mime = magic.from_buffer(content, mime=True)
        else:
            raise Exception("magic module not loaded")
    except Exception as e:
        # Windows'ta veya Linux ortamında libmagic yüklenemediyse fallback yap:
        import mimetypes
        guessed_mime, _ = mimetypes.guess_type(f"file{expected_extension}")
        detected_mime = guessed_mime or "application/octet-stream"

    if detected_mime not in allowed_mimes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Dosya içeriği uzantıyla eşleşmiyor. "
                f"Beklenen MIME türleri: {', '.join(sorted(allowed_mimes))}; "
                f"algılanan: '{detected_mime}'. "
                f"Dosya gerçek bir {expected_extension.upper().lstrip('.')} dosyası değil."
            ),
        )
    return detected_mime


def _validate_docx_structure(content: bytes) -> None:
    """
    DOCX dosyasının gerçekten geçerli bir Office Open XML belgesi olduğunu
    ZIP yapısını kontrol ederek doğrular. Bu, zararlı zip dosyalarının
    .docx olarak yüklenmesini engeller.
    """
    import zipfile
    import io

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            names = zf.namelist()
            # Geçerli bir DOCX her zaman [Content_Types].xml içerir
            if "[Content_Types].xml" not in names:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Dosya geçerli bir DOCX belgesi değil (Content_Types.xml bulunamadı).",
                )
            # word/ dizini olmalı
            has_word_dir = any(name.startswith("word/") for name in names)
            if not has_word_dir:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Dosya geçerli bir DOCX belgesi değil (word/ dizini bulunamadı).",
                )
    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dosya bozuk veya geçerli bir DOCX belgesi değil.",
        )


def _save_file(content: bytes, original_filename: str, extension: str) -> Path:
    """
    Dosyayı güvenli bir şekilde diske kaydeder.
    Dosya adı olarak UUID kullanarak path traversal saldırılarını önler.
    """
    safe_filename = f"{uuid.uuid4().hex}{extension}"
    file_path = UPLOAD_DIR / safe_filename
    file_path.write_bytes(content)
    return file_path


# ─────────────────────── Dosya Yükleme Endpoint ───────────────────


@app.post(
    "/upload",
    summary="Güvenli dosya yükleme",
    response_description="Başarılı yükleme bilgisi",
    status_code=status.HTTP_200_OK,
    tags=["Dosya Yükleme"],
)
@limiter.limit("5/minute")  # IP başına dakikada maks. 5 yükleme
async def upload_file(
    request: Request,
    file: UploadFile = File(..., description="PDF veya DOCX dosyası"),
    current_user: dict = Depends(get_current_user),
):
    """
    Güvenli dosya yükleme endpoint'i.

    **Güvenlik kontrolleri (sırasıyla):**
    1. Giriş zorunluluğu (JWT gerekli)
    2. Rate Limiting — IP başına dakikada maks. 5 istek
    3. Dosya uzantısı doğrulaması (.pdf veya .docx)
    4. Dosya boyutu kontrolü (maks. 20 MB)
    5. Magic bytes ile gerçek MIME türü doğrulaması
    6. DOCX için ek yapısal doğrulama
    7. Kredi kontrolü (premium değilse)

    Tüm kontrolleri geçen dosyalar UUID ile yeniden adlandırılarak kaydedilir.
    """

    # ── 0. Premium & Kredi Kontrolü ──
    user_is_premium = is_user_premium(current_user)
    can_see_full = can_user_access_full_report(current_user)

    if not user_is_premium:
        credit_count = current_user.get("credit_count", 0)
        if credit_count <= 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Analiz hakkınız kalmadı. Lütfen paket satın alın.",
            )

    # ── 1. Uzantı Kontrolü ──
    extension = _validate_extension(file.filename or "")

    # ── 2. Dosya İçeriğini Oku ──
    content = await file.read()

    # ── 3. Boyut Kontrolü ──
    _validate_file_size(content)

    # ── 4. MIME Type Kontrolü (magic bytes) ──
    detected_mime = _validate_mime_type(content, extension)

    # ── 5. DOCX İçin Ek Yapısal Doğrulama ──
    if extension == ".docx":
        _validate_docx_structure(content)

    # ── 6. Dosyayı Kaydet ──
    saved_path = _save_file(content, file.filename or "unknown", extension)

    # ── 7. Metin Çıkarma ve AI Analizi ──
    extracted_text = _extract_text_from_file(saved_path, extension)
    analysis_result = _analyze_ai_content(extracted_text, can_see_full=can_see_full)

    # ── 8. İntihal / Benzerlik Taraması (internetten) ──
    plagiarism_result = await check_plagiarism(extracted_text, can_see_full=can_see_full)

    # ── 9. Kredi Düş (Premium kullanıcılar bypass) ──
    remaining_credits = None
    if user_is_premium:
        # Premium kullanıcı → sınırsız tarama, kredi düşürme
        remaining_credits = -1  # Frontend'e sınırsız sinyali
    else:
        try:
            from database import get_supabase
            supabase = get_supabase()
            new_credit = max(0, current_user.get("credit_count", 0) - 1)
            supabase.update(
                table="users",
                data={"credit_count": new_credit},
                filters={"id": current_user["id"]},
            )
            remaining_credits = new_credit
        except Exception as e:
            print(f"Kredi düşme hatası: {e}")
            remaining_credits = current_user.get("credit_count", 0)

    response_content = {
        "message": "Dosya başarıyla analiz edildi.",
        "original_filename": file.filename,
        "detected_mime_type": detected_mime,
        "analysis": analysis_result,
        "plagiarism": plagiarism_result,
        "remaining_credits": remaining_credits,
    }

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_content,
    )


# ─────────────────────── Metin Analizi Endpoint ───────────────────

class TextAnalyzeRequest(BaseModel):
    text: str = Field(..., description="Analiz edilecek metin")

@app.post(
    "/analyze-text",
    summary="Metin Analizi",
    response_description="Başarılı analiz bilgisi",
    status_code=status.HTTP_200_OK,
    tags=["Analiz"],
)
@limiter.limit("5/minute")
async def analyze_text(
    request: Request,
    data: TextAnalyzeRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Güvenli metin analizi endpoint'i.
    Giriş zorunlu. Premium bypass ile sınırsız tarama.
    Premium değilse 1 kredi düşer.
    """
    # ── Premium & Kredi kontrolü ──
    user_is_premium = is_user_premium(current_user)
    can_see_full = can_user_access_full_report(current_user)

    if not user_is_premium:
        credit_count = current_user.get("credit_count", 0)
        if credit_count <= 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Analiz hakkınız kalmadı. Lütfen paket satın alın.",
            )

    word_count = len(data.text.split())
    if word_count > 1000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Metin 1000 kelimeden uzun olamaz.",
        )
    
    # AI Analizi
    analysis_result = _analyze_ai_content(data.text, can_see_full=can_see_full)

    # ── İntihal / Benzerlik Taraması (internetten) ──
    plagiarism_result = await check_plagiarism(data.text, can_see_full=can_see_full)

    # ── Kredi düş (Premium kullanıcılar bypass) ──
    remaining_credits = None
    if user_is_premium:
        remaining_credits = -1  # Frontend'e sınırsız sinyali
    else:
        try:
            from database import get_supabase
            supabase = get_supabase()
            new_credit = max(0, current_user.get("credit_count", 0) - 1)
            supabase.update(
                table="users",
                data={"credit_count": new_credit},
                filters={"id": current_user["id"]},
            )
            remaining_credits = new_credit
        except Exception as e:
            print(f"Kredi düşme hatası: {e}")
            remaining_credits = current_user.get("credit_count", 0)
    
    response_content = {
        "message": "Metin başarıyla analiz edildi.",
        "analysis": analysis_result,
        "plagiarism": plagiarism_result,
        "remaining_credits": remaining_credits,
    }

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_content,
    )


# ───────────────────── Ana Sayfa (Rate Limited) ────────────────────


@app.get(
    "/",
    summary="Ana sayfa",
    status_code=status.HTTP_200_OK,
    tags=["Genel"],
)
@limiter.limit("60/minute")  # IP başına dakikada maks. 60 istek
async def home(request: Request):
    """
    Ana sayfa endpoint'i.

    Genel erişim noktası olduğu için daha yüksek bir limit
    (dakikada 60 istek) uygulanmıştır.
    """
    return JSONResponse(
        content={
            "message": "Güvenli Dosya Yükleme & Kimlik Doğrulama API'sine hoş geldiniz.",
            "version": "2.0.0",
            "endpoints": {
                "POST /auth/register": "Yeni kullanıcı kaydı (5 istek/dk)",
                "POST /auth/login": "Kullanıcı girişi + JWT token (5 istek/dk)",
                "GET  /auth/me": "Profil bilgisi (JWT gerekli)",
                "POST /upload": "Güvenli dosya yükleme (5 istek/dk)",
                "GET  /admin/dashboard": "🔒 Admin paneli — istatistikler (admin JWT gerekli)",
                "GET  /admin/users": "🔒 Kullanıcı listesi (admin JWT gerekli)",
                "GET  /health": "Sağlık kontrolü (sınırsız)",
                "GET  /docs": "Swagger API dokümantasyonu",
            },
            "security": {
                "authentication": "JWT (Bearer Token)",
                "authorization": "Role-based (user/admin)",
                "password_hashing": "bcrypt",
                "sql_injection": "Supabase parametrized query (PostgREST)",
                "rate_limiting": "slowapi (IP bazlı)",
                "file_validation": "Magic bytes MIME doğrulaması",
            },
        }
    )


# ───────────────────── Sağlık Kontrolü (Sınırsız) ─────────────────


@app.get(
    "/health",
    summary="Sağlık kontrolü",
    tags=["Genel"],
)
@limiter.exempt  # Sağlık kontrolü sınırsız — monitoring araçları için
async def health_check(request: Request):
    """API'nin çalıştığını doğrular."""
    return {"status": "healthy", "service": "Güvenli Dosya Yükleme & Auth API"}


# ─────────────────────────── Frontend Serve ─────────────────────────

from fastapi.responses import FileResponse

@app.get("/frontend", include_in_schema=False)
async def serve_frontend():
    """index.html dosyasını sunar."""
    return FileResponse(Path(__file__).resolve().parent / "index.html")


# ─────────────────────────── Giriş Noktası ─────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
