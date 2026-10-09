-- ستون نوع تراکنش خام بانک (مثل «خرید اینترنتی»، «انتقال به کارت») — درخواست کاربر: علاوه بر
-- type داخلی نرمال‌شده (income/expense/transfer/adjustment)، متن اصلی ستون G فایل بانکی هم
-- به‌صورت جدا نگه داشته شود و در جدول تراکنش‌ها قابل نمایش باشد.

ALTER TABLE transactions ADD COLUMN raw_transaction_type TEXT;
