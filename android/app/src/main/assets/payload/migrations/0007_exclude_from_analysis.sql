-- پرچم استثنا از آنالیز — برای تراکنش‌هایی مثل واریز بین کارت‌های خودتان یا واریز/برداشت به
-- «باکس» که پول واقعاً جابه‌جا شده (پس باید در موجودی حساب لحاظ شود) ولی درآمد/هزینه واقعی
-- نیست و نباید در گزارش‌ها، داشبورد، تفکیک دسته‌بندی، یا تشخیص تکرارشونده/غیرعادی حساب شود.
-- توجه: موجودی حساب (balance) هرگز تحت تأثیر این پرچم قرار نمی‌گیرد — فقط محاسبات تحلیلی.

ALTER TABLE transactions ADD COLUMN excluded_from_analysis INTEGER NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS transactions_excluded_idx ON transactions(excluded_from_analysis);
