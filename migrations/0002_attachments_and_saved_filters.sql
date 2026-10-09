-- پیوست رسید/فاکتور به هر تراکنش، و پیش‌نویس‌های ذخیره‌شده فیلتر صفحه تراکنش‌ها

CREATE TABLE IF NOT EXISTS transaction_attachments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  transaction_id INTEGER NOT NULL REFERENCES transactions(id),
  file_name TEXT NOT NULL,
  stored_path TEXT NOT NULL,
  mime_type TEXT,
  size_bytes INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS transaction_attachments_txn_idx ON transaction_attachments(transaction_id);

CREATE TABLE IF NOT EXISTS saved_filters (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  filters TEXT NOT NULL, -- JSON: شکل colFilters صفحه تراکنش‌ها
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
