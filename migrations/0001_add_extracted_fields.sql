-- افزودن ستون‌های استخراج‌شده از شرح تراکنش (description) — درخواست کاربر: نمایش نام طرف حساب،
-- شماره کارت، شبا، نام بانک و دلیل تراکنش به‌صورت ستون‌های جدا در جدول تراکنش‌ها.
-- این مقادیر توسط src/lib/description-parser.ts استخراج می‌شوند (deterministic، بدون AI) —
-- وقتی الگویی در متن یافت نشود، مقدار NULL باقی می‌ماند (نه حدس زده می‌شود).
-- توجه: ستون counterparty از قبل (migration 0000) وجود داشت ولی هیچ‌وقت پر نمی‌شد — حالا با
-- همین parser پر می‌شود، ستون جدیدی برای نام طرف حساب اضافه نشده.

ALTER TABLE transactions ADD COLUMN card_number TEXT;
ALTER TABLE transactions ADD COLUMN iban TEXT;
ALTER TABLE transactions ADD COLUMN bank_name TEXT;
ALTER TABLE transactions ADD COLUMN reason TEXT;

CREATE INDEX IF NOT EXISTS transactions_counterparty_idx ON transactions(counterparty);
CREATE INDEX IF NOT EXISTS transactions_card_number_idx ON transactions(card_number);
