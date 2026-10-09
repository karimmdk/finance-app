"""
Chaquopy بسته‌ی pydantic-core (هسته Rust در pydantic نسخه ۲) را برای اندروید ندارد؛ پس روی اندروید
pydantic نسخه ۱ (کاملاً پایتونی) نصب می‌شود. کد اپ فقط یک API نسخه ۲ را استفاده می‌کند
(model_dump(exclude_unset=True)) که اینجا برای نسخه ۱ معادل‌سازی می‌شود. روی pydantic ۲ (دسکتاپ) کاری نمی‌کند.
"""
import pydantic

if pydantic.VERSION.startswith("1."):
    def _model_dump(self, **kwargs):
        return self.dict(**kwargs)

    if not hasattr(pydantic.BaseModel, "model_dump"):
        pydantic.BaseModel.model_dump = _model_dump
