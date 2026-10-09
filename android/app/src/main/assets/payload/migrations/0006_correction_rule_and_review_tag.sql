-- تگ پیش‌فرض «نیاز به بررسی» + قانون برای ردیف‌های «اصلاح سند» که تا الان هیچ دسته‌بندی یا
-- تگ خودکاری نداشتند (چون correction هستند و به یک سند دیگر اشاره می‌کنند، نه یک تراکنش عادی).

INSERT INTO tags (name)
SELECT 'نیاز به بررسی' WHERE NOT EXISTS (SELECT 1 FROM tags WHERE name = 'نیاز به بررسی');

-- توجه: چون actions فعلاً فقط یک tagId می‌پذیرد نه آرایه در seed (برای سادگی SQL)، فقط categoryId
-- را ست می‌کنیم و tagId را جدا با UPDATE بعد از insert اضافه می‌کنیم.
INSERT INTO rules (name, condition, actions, active, auto_apply)
SELECT 'اصلاح سند → متفرقه',
       '{"field":"rawTransactionType","op":"equals","value":"اصلاح سند"}',
       json_object('categoryId', (SELECT id FROM categories WHERE name = 'متفرقه')),
       1, 1
WHERE NOT EXISTS (SELECT 1 FROM rules WHERE name = 'اصلاح سند → متفرقه')
  AND EXISTS (SELECT 1 FROM categories WHERE name = 'متفرقه');

UPDATE rules
SET actions = json_set(actions, '$.tagIds', json_array((SELECT id FROM tags WHERE name = 'نیاز به بررسی')))
WHERE name = 'اصلاح سند → متفرقه'
  AND json_extract(actions, '$.tagIds') IS NULL
  AND EXISTS (SELECT 1 FROM tags WHERE name = 'نیاز به بررسی');
