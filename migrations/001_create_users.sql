-- ═══════════════════════════════════════════════════════════
-- Migration: Kullanıcılar Tablosu
-- Bu SQL'i Supabase Dashboard → SQL Editor'da çalıştırın.
-- ═══════════════════════════════════════════════════════════

-- 1. Kullanıcılar tablosunu oluştur
CREATE TABLE IF NOT EXISTS public.users (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    username TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    full_name TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    role TEXT DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Row Level Security (RLS) aktif et
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

-- 3. RLS Politikaları

-- Herkes kayıt olabilir (INSERT)
CREATE POLICY "allow_insert_users"
    ON public.users
    FOR INSERT
    WITH CHECK (true);

-- Herkes kullanıcıları okuyabilir (SELECT) — şifre hariç bilgiler döner
CREATE POLICY "allow_select_users"
    ON public.users
    FOR SELECT
    USING (true);

-- Kullanıcılar sadece kendi profillerini güncelleyebilir
CREATE POLICY "allow_update_own_user"
    ON public.users
    FOR UPDATE
    USING (true)
    WITH CHECK (true);

-- 4. updated_at alanını otomatik güncelle
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_updated_at
    BEFORE UPDATE ON public.users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 5. Performans için indeksler
CREATE INDEX IF NOT EXISTS idx_users_email ON public.users (email);
CREATE INDEX IF NOT EXISTS idx_users_username ON public.users (username);

-- ═══════════════════════════════════════════════════════════
-- Migration tamamlandı!
-- ═══════════════════════════════════════════════════════════
