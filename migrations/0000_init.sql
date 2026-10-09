-- Phase 1/2 schema — mirrors src/db/schema/*.ts exactly.
-- Runtime uses better-sqlite3 directly (see docs/architecture.md ADR-002) —
-- this file is the single source of truth for actual table structure.

CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  type TEXT NOT NULL CHECK(type IN ('bank','cash','wallet','other')),
  bank_name TEXT,
  account_number TEXT,
  card_number TEXT,
  iban TEXT,
  initial_balance INTEGER NOT NULL DEFAULT 0,
  currency TEXT NOT NULL DEFAULT 'IRR' CHECK(currency IN ('IRR','IRT')),
  active INTEGER NOT NULL DEFAULT 1,
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS import_batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL REFERENCES accounts(id),
  file_name TEXT NOT NULL,
  adapter TEXT NOT NULL,
  imported_count INTEGER NOT NULL DEFAULT 0,
  duplicate_count INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'completed' CHECK(status IN ('completed','rolled_back')),
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS import_batches_account_idx ON import_batches(account_id);

CREATE TABLE IF NOT EXISTS categories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  parent_id INTEGER REFERENCES categories(id),
  icon TEXT,
  color TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS people (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  phone TEXT,
  description TEXT,
  account_number TEXT,
  national_id TEXT,
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS transactions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL REFERENCES accounts(id),
  transaction_date TEXT NOT NULL,
  transaction_time TEXT,
  amount INTEGER NOT NULL,
  type TEXT NOT NULL CHECK(type IN ('income','expense','transfer','adjustment')),
  balance_after INTEGER,
  description TEXT,
  document_number TEXT,
  counterparty TEXT,
  category_id INTEGER REFERENCES categories(id),
  person_id INTEGER REFERENCES people(id),
  notes TEXT,
  source TEXT NOT NULL DEFAULT 'manual' CHECK(source IN ('import','manual')),
  import_batch_id INTEGER REFERENCES import_batches(id),
  transfer_id TEXT,
  source_row_number INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS transactions_date_idx ON transactions(transaction_date);
CREATE INDEX IF NOT EXISTS transactions_doc_num_idx ON transactions(document_number);
CREATE INDEX IF NOT EXISTS transactions_account_idx ON transactions(account_id);
CREATE INDEX IF NOT EXISTS transactions_person_idx ON transactions(person_id);
CREATE INDEX IF NOT EXISTS transactions_category_idx ON transactions(category_id);
CREATE INDEX IF NOT EXISTS transactions_batch_idx ON transactions(import_batch_id);
CREATE INDEX IF NOT EXISTS transactions_transfer_idx ON transactions(transfer_id);

CREATE TABLE IF NOT EXISTS tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  color TEXT
);

CREATE TABLE IF NOT EXISTS transaction_tags (
  transaction_id INTEGER NOT NULL REFERENCES transactions(id),
  tag_id INTEGER NOT NULL REFERENCES tags(id),
  PRIMARY KEY (transaction_id, tag_id)
);
CREATE INDEX IF NOT EXISTS transaction_tags_tx_idx ON transaction_tags(transaction_id);
CREATE INDEX IF NOT EXISTS transaction_tags_tag_idx ON transaction_tags(tag_id);

CREATE TABLE IF NOT EXISTS debts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL CHECK(kind IN ('receivable','payable')),
  person_id INTEGER NOT NULL REFERENCES people(id),
  original_amount INTEGER NOT NULL,
  paid_amount INTEGER NOT NULL DEFAULT 0,
  created_date TEXT NOT NULL,
  due_date TEXT,
  description TEXT,
  status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','settled','overdue'))
);
CREATE INDEX IF NOT EXISTS debts_person_idx ON debts(person_id);

CREATE TABLE IF NOT EXISTS debt_payments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  debt_id INTEGER NOT NULL REFERENCES debts(id),
  transaction_id INTEGER REFERENCES transactions(id),
  amount INTEGER NOT NULL,
  date TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS debt_payments_debt_idx ON debt_payments(debt_id);

CREATE TABLE IF NOT EXISTS loans (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  lender TEXT NOT NULL,
  principal INTEGER NOT NULL,
  interest_rate INTEGER,
  term_months INTEGER NOT NULL,
  installment_amount INTEGER NOT NULL,
  start_date TEXT NOT NULL,
  due_date TEXT,
  account_id INTEGER REFERENCES accounts(id),
  notes TEXT
);

CREATE TABLE IF NOT EXISTS installments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  loan_id INTEGER NOT NULL REFERENCES loans(id),
  installment_number INTEGER NOT NULL,
  due_date TEXT NOT NULL,
  amount INTEGER NOT NULL,
  paid_amount INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'upcoming' CHECK(status IN ('upcoming','due','paid','overdue','partially_paid')),
  transaction_id INTEGER REFERENCES transactions(id)
);
CREATE INDEX IF NOT EXISTS installments_loan_idx ON installments(loan_id);

CREATE TABLE IF NOT EXISTS customers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  phone TEXT,
  description TEXT
);

CREATE TABLE IF NOT EXISTS installment_sales (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  date TEXT NOT NULL,
  item_amount INTEGER NOT NULL,
  discount INTEGER NOT NULL DEFAULT 0,
  final_amount INTEGER NOT NULL,
  down_payment INTEGER NOT NULL DEFAULT 0,
  installment_count INTEGER NOT NULL,
  payment_terms TEXT
);

CREATE TABLE IF NOT EXISTS sale_payments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sale_id INTEGER NOT NULL REFERENCES installment_sales(id),
  date TEXT NOT NULL,
  amount INTEGER NOT NULL,
  account_id INTEGER REFERENCES accounts(id),
  transaction_id INTEGER REFERENCES transactions(id),
  notes TEXT
);
CREATE INDEX IF NOT EXISTS sale_payments_sale_idx ON sale_payments(sale_id);

CREATE TABLE IF NOT EXISTS rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  condition TEXT NOT NULL,
  actions TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  auto_apply INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS budgets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  category_id INTEGER NOT NULL REFERENCES categories(id),
  month TEXT NOT NULL, -- 'YYYY-MM' Gregorian
  amount INTEGER NOT NULL,
  UNIQUE(category_id, month)
);

CREATE TABLE IF NOT EXISTS recurring_transactions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL REFERENCES accounts(id),
  name TEXT NOT NULL,
  amount INTEGER NOT NULL,
  type TEXT NOT NULL CHECK(type IN ('income','expense')),
  category_id INTEGER REFERENCES categories(id),
  day_of_month INTEGER NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
