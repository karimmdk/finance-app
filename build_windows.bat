@echo off
REM ساخت بسته پرتابل تک‌پوشه‌ای برای ویندوز (بدون نیاز به نصب پایتون روی سیستم مقصد).
REM این اسکریپت باید روی خودِ ویندوز اجرا شود (PyInstaller نمی‌تواند از لینوکس/مک برای
REM ویندوز cross-compile کند) — پایتون باید از قبل روی این سیستم (فقط برای ساخت) نصب باشد.

cd /d "%~dp0"

pip install -r requirements.txt pyinstaller

REM اگر پروژه فرانت‌اند React کنار همین پوشه است، آن را بیلد و کپی کنید
if exist "..\finance-app" (
  echo Building frontend...
  cd ..\finance-app
  call npm run build
  cd ..\finance-app-py
  rmdir /s /q static
  mkdir static
  xcopy /e /i ..\finance-app\dist-ui\* static\
)

rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del *.spec 2>nul

pyinstaller --name finance-app --onedir --noconfirm ^
  --add-data "migrations;migrations" ^
  --add-data "static;static" ^
  --hidden-import uvicorn.logging ^
  --hidden-import uvicorn.loops ^
  --hidden-import uvicorn.loops.auto ^
  --hidden-import uvicorn.protocols ^
  --hidden-import uvicorn.protocols.http ^
  --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.websockets ^
  --hidden-import uvicorn.protocols.websockets.auto ^
  --hidden-import uvicorn.lifespan ^
  --hidden-import uvicorn.lifespan.on ^
  run.py

echo.
echo ساخته شد: dist\finance-app\
echo برای اجرا: پوشه dist\finance-app را هرجا خواستید کپی کنید و finance-app.exe را دوبار کلیک کنید.
