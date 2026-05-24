-- ═══════════════════════════════════════════════════════════
-- Migration 002: Taramalar, Ödemeler ve Kredi Tabloları
-- Bu SQL'i Supabase Dashboard → SQL Editor'da çalıştırın.
-- ═══════════════════════════════════════════════════════════

-- ─────────────────────── 1. Taramalar (Scans) ─────────────

CREATE TABLE IF NOT EXISTS public.scans (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    file_name TEXT,
    file_type TEXT CHECK (file_type IN ('pdf', 'docx')),
    file_size_bytes BIGINT,
    result JSONB,                    -- Tarama sonucu (AI detection vb.)
    status TEXT DEFAULT 'completed' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.scans ENABLE ROW LEVEL SECURITY;

CREATE POLICY "allow_insert_scans"
    ON public.scans FOR INSERT WITH CHECK (true);

CREATE POLICY "allow_select_scans"
    ON public.scans FOR SELECT USING (true);

CREATE INDEX IF NOT EXISTS idx_scans_user_id ON public.scans (user_id);
CREATE INDEX IF NOT EXISTS idx_scans_created_at ON public.scans (created_at);

-- ─────────────────── 2. Ödemeler (Payments) ───────────────

CREATE TABLE IF NOT EXISTS public.payments (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    lemon_squeezy_id TEXT,           -- LemonSqueezy sipariş/ödeme ID'si
    amount_usd NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    currency TEXT DEFAULT 'USD',
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'paid', 'refunded', 'failed')),
    provider TEXT DEFAULT 'lemonsqueezy',
    plan_name TEXT,                  -- Satın alınan paket adı
    credits_added INT DEFAULT 0,    -- Ödeme ile eklenen kredi miktarı
    metadata JSONB,                  -- Ek webhook verisi
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.payments ENABLE ROW LEVEL SECURITY;

CREATE POLICY "allow_insert_payments"
    ON public.payments FOR INSERT WITH CHECK (true);

CREATE POLICY "allow_select_payments"
    ON public.payments FOR SELECT USING (true);

CREATE INDEX IF NOT EXISTS idx_payments_user_id ON public.payments (user_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON public.payments (status);
CREATE INDEX IF NOT EXISTS idx_payments_created_at ON public.payments (created_at);

-- Otomatik updated_at trigger'ı (fonksiyon zaten var)
CREATE TRIGGER set_payments_updated_at
    BEFORE UPDATE ON public.payments
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ─────────────── 3. Kullanıcı Kredileri (User Credits) ────

CREATE TABLE IF NOT EXISTS public.user_credits (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID UNIQUE NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    credits INT DEFAULT 0,           -- Mevcut kredi bakiyesi
    total_used INT DEFAULT 0,        -- Toplam kullanılan kredi
    total_purchased INT DEFAULT 0,   -- Toplam satın alınan kredi
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.user_credits ENABLE ROW LEVEL SECURITY;

CREATE POLICY "allow_insert_user_credits"
    ON public.user_credits FOR INSERT WITH CHECK (true);

CREATE POLICY "allow_select_user_credits"
    ON public.user_credits FOR SELECT USING (true);

CREATE POLICY "allow_update_user_credits"
    ON public.user_credits FOR UPDATE USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_user_credits_user_id ON public.user_credits (user_id);
CREATE INDEX IF NOT EXISTS idx_user_credits_credits ON public.user_credits (credits);

-- Otomatik updated_at
CREATE TRIGGER set_user_credits_updated_at
    BEFORE UPDATE ON public.user_credits
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ═══════════════════════════════════════════════════════════
-- Migration 002 tamamlandı!
-- Tablolar: scans, payments, user_credits
-- ═══════════════════════════════════════════════════════════
