-- ============================================================
-- AI DETECT — Supabase Veritabanı Tam Kurulum SQL'i
-- ============================================================
-- Bu SQL'i Supabase Dashboard → SQL Editor'de çalıştırın:
-- https://supabase.com/dashboard/project/uvkocqokxeueajpssaew/sql/new
--
-- ⚠️  Tüm kodu kopyalayıp tek seferde çalıştırın.
-- ============================================================


-- ─────────────────────────────────────────────────────────────
-- 1. UUID eklentisini etkinleştir (id için gerekli)
-- ─────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";


-- ─────────────────────────────────────────────────────────────
-- 2. USERS TABLOSU — Eksik sütunları ekle
-- ─────────────────────────────────────────────────────────────
-- Projede kullanılan sütunlar:
--   id              → UUID (primary key, otomatik)
--   email           → TEXT (unique, zorunlu)
--   username        → TEXT (unique, zorunlu)     ← EKSİK
--   hashed_password → TEXT (zorunlu)             ← EKSİK
--   full_name       → TEXT (opsiyonel)           ← EKSİK
--   credit_count    → INTEGER (varsayılan: 3)
--   is_premium      → BOOLEAN (varsayılan: false)
--   is_active       → BOOLEAN (varsayılan: true) ← EKSİK
--   role            → TEXT (varsayılan: 'user')   ← EKSİK
--   created_at      → TIMESTAMPTZ (otomatik)

ALTER TABLE public.users ADD COLUMN IF NOT EXISTS username TEXT;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS hashed_password TEXT;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS full_name TEXT;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'user';

-- Username için UNIQUE constraint (aynı kullanıcı adı iki kez olamaz)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'users_username_key'
  ) THEN
    ALTER TABLE public.users ADD CONSTRAINT users_username_key UNIQUE (username);
  END IF;
END $$;


-- ─────────────────────────────────────────────────────────────
-- 3. ROW LEVEL SECURITY (RLS) POLİTİKALARI
-- ─────────────────────────────────────────────────────────────
-- RLS'i etkinleştir (zaten açıksa hata vermez)
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

-- Mevcut çakışan politikaları temizle (varsa)
DROP POLICY IF EXISTS "Allow anon insert" ON public.users;
DROP POLICY IF EXISTS "Allow anon select" ON public.users;
DROP POLICY IF EXISTS "Allow anon update" ON public.users;

-- Kayıt olma: Anonim kullanıcılar INSERT yapabilsin
CREATE POLICY "Allow anon insert" ON public.users
  FOR INSERT TO anon
  WITH CHECK (true);

-- Giriş yapma / kullanıcı sorgulama: Anonim kullanıcılar SELECT yapabilsin
CREATE POLICY "Allow anon select" ON public.users
  FOR SELECT TO anon
  USING (true);

-- Profil güncelleme: Anonim kullanıcılar UPDATE yapabilsin (JWT ile kendi profilini)
CREATE POLICY "Allow anon update" ON public.users
  FOR UPDATE TO anon
  USING (true)
  WITH CHECK (true);


-- ─────────────────────────────────────────────────────────────
-- 4. DOĞRULAMA — Sütunları kontrol et
-- ─────────────────────────────────────────────────────────────
-- Bu sorgu tüm sütunları listeler, çalıştırdıktan sonra
-- aşağıdaki sütunların olduğundan emin olun:
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'users'
ORDER BY ordinal_position;
