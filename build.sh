#!/bin/bash
# ساخت بسته پرتابل تک‌پوشه‌ای (بدون نیاز به نصب پایتون روی سیستم مقصد).
# روی لینوکس یا مک اجرا کنید. خروجی در dist/finance-app/ قرار می‌گیرد —
# همان پوشه را کپی/جابه‌جا کنید و finance-app (یا finance-app.exe در ویندوز) را اجرا کنید.
set -e
cd "$(dirname "$0")"

pip install --break-system-packages -r requirements.txt pyinstaller

# فرانت‌اند React را از پروژه Node بیلد کنید و نتیجه را در static/ کپی کنید
# (اگر پروژه finance-app کنار همین پوشه است؛ در غیر این صورت مسیر را اصلاح کنید)
if [ -d "../finance-app" ]; then
  echo "Building frontend..."
  (cd ../finance-app && npm run build)
  rm -rf static/*
  cp -r ../finance-app/dist-ui/* static/
fi

rm -rf build dist *.spec

pyinstaller --name finance-app --onedir --noconfirm \
  --add-data "migrations:migrations" \
  --add-data "static:static" \
  --hidden-import uvicorn.logging \
  --hidden-import uvicorn.loops \
  --hidden-import uvicorn.loops.auto \
  --hidden-import uvicorn.protocols \
  --hidden-import uvicorn.protocols.http \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import uvicorn.protocols.websockets \
  --hidden-import uvicorn.protocols.websockets.auto \
  --hidden-import uvicorn.lifespan \
  --hidden-import uvicorn.lifespan.on \
  run.py

echo ""
echo "ساخته شد: dist/finance-app/"
echo "برای اجرا: cd dist/finance-app && ./finance-app"
