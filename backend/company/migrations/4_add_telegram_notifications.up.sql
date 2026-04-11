-- Add Telegram notification columns to companies table
ALTER TABLE companies ADD COLUMN IF NOT EXISTS violation_alerts BOOLEAN DEFAULT TRUE;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS telegram_notifications BOOLEAN DEFAULT FALSE;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS telegram_bot_token TEXT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS telegram_chat_id TEXT;
