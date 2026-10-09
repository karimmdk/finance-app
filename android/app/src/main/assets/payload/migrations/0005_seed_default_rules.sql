-- قوانین پیش‌فرض دسته‌بندی خودکار بر اساس نوع تراکنش خام بانک (ستون raw_transaction_type) —
-- auto_apply=1 یعنی این‌ها بدون تأیید کاربر روی تراکنش‌های ایمپورت‌شده اعمال می‌شوند.
-- idempotent با الگوی WHERE NOT EXISTS روی name.

INSERT INTO rules (name, condition, actions, active, auto_apply)
SELECT 'خرید اینترنتی → خرید آنلاین',
       '{"field":"rawTransactionType","op":"equals","value":"خرید اینترنتی"}',
       json_object('categoryId', (SELECT id FROM categories WHERE name = 'خرید آنلاین')),
       1, 1
WHERE NOT EXISTS (SELECT 1 FROM rules WHERE name = 'خرید اینترنتی → خرید آنلاین')
  AND EXISTS (SELECT 1 FROM categories WHERE name = 'خرید آنلاین');

INSERT INTO rules (name, condition, actions, active, auto_apply)
SELECT 'خرید از فروشگاه → خرید حضوری',
       '{"field":"rawTransactionType","op":"equals","value":"خرید از فروشگاه"}',
       json_object('categoryId', (SELECT id FROM categories WHERE name = 'خرید حضوری')),
       1, 1
WHERE NOT EXISTS (SELECT 1 FROM rules WHERE name = 'خرید از فروشگاه → خرید حضوری')
  AND EXISTS (SELECT 1 FROM categories WHERE name = 'خرید حضوری');

INSERT INTO rules (name, condition, actions, active, auto_apply)
SELECT 'کارمزد → کارمزد بانکی',
       '{"field":"rawTransactionType","op":"equals","value":"کارمزد"}',
       json_object('categoryId', (SELECT id FROM categories WHERE name = 'کارمزد بانکی')),
       1, 1
WHERE NOT EXISTS (SELECT 1 FROM rules WHERE name = 'کارمزد → کارمزد بانکی')
  AND EXISTS (SELECT 1 FROM categories WHERE name = 'کارمزد بانکی');

INSERT INTO rules (name, condition, actions, active, auto_apply)
SELECT 'قبض → قبوض',
       '{"field":"rawTransactionType","op":"equals","value":"قبض"}',
       json_object('categoryId', (SELECT id FROM categories WHERE name = 'قبوض')),
       1, 1
WHERE NOT EXISTS (SELECT 1 FROM rules WHERE name = 'قبض → قبوض')
  AND EXISTS (SELECT 1 FROM categories WHERE name = 'قبوض');

INSERT INTO rules (name, condition, actions, active, auto_apply)
SELECT 'انتقال به کارت → انتقال وجه',
       '{"field":"rawTransactionType","op":"equals","value":"انتقال به کارت"}',
       json_object('categoryId', (SELECT id FROM categories WHERE name = 'انتقال وجه')),
       1, 1
WHERE NOT EXISTS (SELECT 1 FROM rules WHERE name = 'انتقال به کارت → انتقال وجه')
  AND EXISTS (SELECT 1 FROM categories WHERE name = 'انتقال وجه');

INSERT INTO rules (name, condition, actions, active, auto_apply)
SELECT 'انتقال به سپرده → انتقال وجه',
       '{"field":"rawTransactionType","op":"equals","value":"انتقال به سپرده"}',
       json_object('categoryId', (SELECT id FROM categories WHERE name = 'انتقال وجه')),
       1, 1
WHERE NOT EXISTS (SELECT 1 FROM rules WHERE name = 'انتقال به سپرده → انتقال وجه')
  AND EXISTS (SELECT 1 FROM categories WHERE name = 'انتقال وجه');

INSERT INTO rules (name, condition, actions, active, auto_apply)
SELECT 'دریافت از کارت → درآمد و دریافتی',
       '{"field":"rawTransactionType","op":"equals","value":"دریافت از کارت"}',
       json_object('categoryId', (SELECT id FROM categories WHERE name = 'درآمد و دریافتی')),
       1, 1
WHERE NOT EXISTS (SELECT 1 FROM rules WHERE name = 'دریافت از کارت → درآمد و دریافتی')
  AND EXISTS (SELECT 1 FROM categories WHERE name = 'درآمد و دریافتی');

INSERT INTO rules (name, condition, actions, active, auto_apply)
SELECT 'دریافت از سپرده → درآمد و دریافتی',
       '{"field":"rawTransactionType","op":"equals","value":"دریافت از سپرده"}',
       json_object('categoryId', (SELECT id FROM categories WHERE name = 'درآمد و دریافتی')),
       1, 1
WHERE NOT EXISTS (SELECT 1 FROM rules WHERE name = 'دریافت از سپرده → درآمد و دریافتی')
  AND EXISTS (SELECT 1 FROM categories WHERE name = 'درآمد و دریافتی');

INSERT INTO rules (name, condition, actions, active, auto_apply)
SELECT 'واریز سود بانکی → سود بانکی',
       '{"field":"rawTransactionType","op":"equals","value":"واریز سود بانکی"}',
       json_object('categoryId', (SELECT id FROM categories WHERE name = 'سود بانکی')),
       1, 1
WHERE NOT EXISTS (SELECT 1 FROM rules WHERE name = 'واریز سود بانکی → سود بانکی')
  AND EXISTS (SELECT 1 FROM categories WHERE name = 'سود بانکی');
