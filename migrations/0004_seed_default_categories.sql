-- دسته‌بندی‌های پیش‌فرض بر اساس انواع تراکنش‌های واقعی مشاهده‌شده در فایل نمونه بانکی
-- (docs/import-format.md). idempotent با الگوی WHERE NOT EXISTS چون categories.name
-- محدودیت UNIQUE ندارد (کاربر می‌تواند دستی نام تکراری هم بسازد، این فقط جلوی seed دوباره را می‌گیرد).

INSERT INTO categories (name)
SELECT 'خرید آنلاین' WHERE NOT EXISTS (SELECT 1 FROM categories WHERE name = 'خرید آنلاین');

INSERT INTO categories (name)
SELECT 'خرید حضوری' WHERE NOT EXISTS (SELECT 1 FROM categories WHERE name = 'خرید حضوری');

INSERT INTO categories (name)
SELECT 'کارمزد بانکی' WHERE NOT EXISTS (SELECT 1 FROM categories WHERE name = 'کارمزد بانکی');

INSERT INTO categories (name)
SELECT 'قبوض' WHERE NOT EXISTS (SELECT 1 FROM categories WHERE name = 'قبوض');

INSERT INTO categories (name)
SELECT 'انتقال وجه' WHERE NOT EXISTS (SELECT 1 FROM categories WHERE name = 'انتقال وجه');

INSERT INTO categories (name)
SELECT 'درآمد و دریافتی' WHERE NOT EXISTS (SELECT 1 FROM categories WHERE name = 'درآمد و دریافتی');

INSERT INTO categories (name)
SELECT 'سود بانکی' WHERE NOT EXISTS (SELECT 1 FROM categories WHERE name = 'سود بانکی');

INSERT INTO categories (name)
SELECT 'متفرقه' WHERE NOT EXISTS (SELECT 1 FROM categories WHERE name = 'متفرقه');
