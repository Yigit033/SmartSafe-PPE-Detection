-- SmartSafe SaaS - Supabase RLS Security Setup
-- Bu SQL dosyasını Supabase SQL Editor'da çalıştırın

-- 1. RLS'yi tüm tablolar için aktifleştir
ALTER TABLE public.companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cameras ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.detections ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.violations ENABLE ROW LEVEL SECURITY;

-- 2. Companies tablosu için güvenlik politikaları
CREATE POLICY "Companies can view their own data" ON public.companies
  FOR SELECT USING (auth.uid()::text = company_id OR auth.role() = 'service_role');

CREATE POLICY "Companies can update their own data" ON public.companies
  FOR UPDATE USING (auth.uid()::text = company_id OR auth.role() = 'service_role');

CREATE POLICY "Service role can manage companies" ON public.companies
  FOR ALL USING (auth.role() = 'service_role');

-- 3. Users tablosu için güvenlik politikaları
CREATE POLICY "Users can view their company data" ON public.users
  FOR SELECT USING (auth.uid()::text = company_id OR auth.role() = 'service_role');

CREATE POLICY "Users can update their own data" ON public.users
  FOR UPDATE USING (auth.uid()::text = user_id OR auth.role() = 'service_role');

CREATE POLICY "Service role can manage users" ON public.users
  FOR ALL USING (auth.role() = 'service_role');

-- 4. Cameras tablosu için güvenlik politikaları
CREATE POLICY "Companies can manage their cameras" ON public.cameras
  FOR ALL USING (auth.uid()::text = company_id OR auth.role() = 'service_role');

-- 5. Sessions tablosu için güvenlik politikaları
CREATE POLICY "Users can view their sessions" ON public.sessions
  FOR SELECT USING (auth.uid()::text = user_id OR auth.role() = 'service_role');

CREATE POLICY "Service role can manage sessions" ON public.sessions
  FOR ALL USING (auth.role() = 'service_role');

-- 6. Detections tablosu için güvenlik politikaları
CREATE POLICY "Companies can view their detections" ON public.detections
  FOR SELECT USING (auth.uid()::text = company_id OR auth.role() = 'service_role');

CREATE POLICY "Service role can manage detections" ON public.detections
  FOR ALL USING (auth.role() = 'service_role');

-- 7. Violations tablosu için güvenlik politikaları
CREATE POLICY "Companies can view their violations" ON public.violations
  FOR SELECT USING (auth.uid()::text = company_id OR auth.role() = 'service_role');

CREATE POLICY "Service role can manage violations" ON public.violations
  FOR ALL USING (auth.role() = 'service_role');

-- 8. Service role için bypass politikası (API erişimi için)
CREATE POLICY "Bypass RLS for service role" ON public.companies
  FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Bypass RLS for service role" ON public.users
  FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Bypass RLS for service role" ON public.cameras
  FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Bypass RLS for service role" ON public.sessions
  FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Bypass RLS for service role" ON public.detections
  FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Bypass RLS for service role" ON public.violations
  FOR ALL USING (auth.role() = 'service_role');

-- 9. Missing columns için ALTER TABLE statements
-- account_type kolonu ekle (eğer yoksa)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='companies' AND column_name='account_type') THEN
        ALTER TABLE public.companies ADD COLUMN account_type VARCHAR(20) DEFAULT 'full';
    END IF;
END $$;

-- demo_expires_at kolonu ekle (eğer yoksa)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='companies' AND column_name='demo_expires_at') THEN
        ALTER TABLE public.companies ADD COLUMN demo_expires_at TIMESTAMP;
    END IF;
END $$;

-- demo_limits kolonu ekle (eğer yoksa)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='companies' AND column_name='demo_limits') THEN
        ALTER TABLE public.companies ADD COLUMN demo_limits JSON;
    END IF;
END $$;

-- billing_cycle kolonu ekle (eğer yoksa)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='companies' AND column_name='billing_cycle') THEN
        ALTER TABLE public.companies ADD COLUMN billing_cycle VARCHAR(20) DEFAULT 'monthly';
    END IF;
END $$;

-- next_billing_date kolonu ekle (eğer yoksa)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='companies' AND column_name='next_billing_date') THEN
        ALTER TABLE public.companies ADD COLUMN next_billing_date TIMESTAMP;
    END IF;
END $$;

-- auto_renewal kolonu ekle (eğer yoksa)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='companies' AND column_name='auto_renewal') THEN
        ALTER TABLE public.companies ADD COLUMN auto_renewal BOOLEAN DEFAULT TRUE;
    END IF;
END $$;

-- payment_method kolonu ekle (eğer yoksa)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='companies' AND column_name='payment_method') THEN
        ALTER TABLE public.companies ADD COLUMN payment_method VARCHAR(50);
    END IF;
END $$;

-- payment_status kolonu ekle (eğer yoksa)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='companies' AND column_name='payment_status') THEN
        ALTER TABLE public.companies ADD COLUMN payment_status VARCHAR(20) DEFAULT 'active';
    END IF;
END $$;

-- current_balance kolonu ekle (eğer yoksa)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='companies' AND column_name='current_balance') THEN
        ALTER TABLE public.companies ADD COLUMN current_balance DECIMAL(10,2) DEFAULT 0.00;
    END IF;
END $$;

-- total_paid kolonu ekle (eğer yoksa)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='companies' AND column_name='total_paid') THEN
        ALTER TABLE public.companies ADD COLUMN total_paid DECIMAL(10,2) DEFAULT 0.00;
    END IF;
END $$;

-- last_payment_date kolonu ekle (eğer yoksa)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='companies' AND column_name='last_payment_date') THEN
        ALTER TABLE public.companies ADD COLUMN last_payment_date TIMESTAMP;
    END IF;
END $$;

-- last_payment_amount kolonu ekle (eğer yoksa)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name='companies' AND column_name='last_payment_amount') THEN
        ALTER TABLE public.companies ADD COLUMN last_payment_amount DECIMAL(10,2);
    END IF;
END $$;

-- 10. Eksik tablolar için CREATE TABLE statements
CREATE TABLE IF NOT EXISTS public.subscription_history (
    id SERIAL PRIMARY KEY,
    company_id VARCHAR(255) REFERENCES companies(company_id),
    subscription_type VARCHAR(50) NOT NULL,
    billing_cycle VARCHAR(20) NOT NULL,
    start_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP NOT NULL,
    monthly_price DECIMAL(10,2) NOT NULL,
    yearly_price DECIMAL(10,2),
    actual_paid DECIMAL(10,2) NOT NULL,
    payment_method VARCHAR(50),
    payment_status VARCHAR(20) NOT NULL,
    change_reason VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS public.billing_history (
    id SERIAL PRIMARY KEY,
    company_id VARCHAR(255) REFERENCES companies(company_id),
    invoice_number VARCHAR(50) UNIQUE NOT NULL,
    billing_date TIMESTAMP NOT NULL,
    due_date TIMESTAMP NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    tax_amount DECIMAL(10,2) DEFAULT 0.00,
    total_amount DECIMAL(10,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    payment_status VARCHAR(20) DEFAULT 'pending',
    payment_method VARCHAR(50),
    paid_date TIMESTAMP,
    invoice_pdf_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS public.payment_methods (
    id SERIAL PRIMARY KEY,
    company_id VARCHAR(255) REFERENCES companies(company_id),
    payment_type VARCHAR(50) NOT NULL,
    card_last4 VARCHAR(4),
    card_brand VARCHAR(20),
    expiry_month INTEGER,
    expiry_year INTEGER,
    is_default BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- RLS'yi yeni tablolar için de aktifleştir
ALTER TABLE public.subscription_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.billing_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payment_methods ENABLE ROW LEVEL SECURITY;

-- Yeni tablolar için güvenlik politikaları
CREATE POLICY "Companies can view their subscription history" ON public.subscription_history
  FOR SELECT USING (auth.uid()::text = company_id OR auth.role() = 'service_role');

CREATE POLICY "Companies can view their billing history" ON public.billing_history
  FOR SELECT USING (auth.uid()::text = company_id OR auth.role() = 'service_role');

CREATE POLICY "Companies can view their payment methods" ON public.payment_methods
  FOR SELECT USING (auth.uid()::text = company_id OR auth.role() = 'service_role');

-- Service role bypass için yeni tablolar
CREATE POLICY "Service role can manage subscription history" ON public.subscription_history
  FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role can manage billing history" ON public.billing_history
  FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role can manage payment methods" ON public.payment_methods
  FOR ALL USING (auth.role() = 'service_role');

-- Başarı mesajı
SELECT 'SmartSafe SaaS Supabase security setup completed successfully!' as result;
