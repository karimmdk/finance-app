plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

android {
    namespace = "ir.financeapp.mobile"
    compileSdk = 35

    defaultConfig {
        applicationId = "ir.financeapp.mobile"
        minSdk = 30          // اندروید ۱۱ به بالا (برای دسترسی به پوشه‌های مشترک)
        targetSdk = 35
        versionCode = 5
        versionName = "1.4"
        ndk {
            // arm64-v8a = همه گوشی‌های امروزی؛ x86_64 فقط برای شبیه‌ساز
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }

    // کلید ثابت: همه APKها (حتی از اجراهای مختلف GitHub Actions) با یک امضا ساخته می‌شوند
    // تا بتوان نسخه جدید را روی قبلی نصب کرد بدون حذف برنامه (و از دست رفتن داده).
    signingConfigs {
        getByName("debug") {
            storeFile = file("debug.keystore")
            storePassword = "android"
            keyAlias = "androiddebugkey"
            keyPassword = "android"
        }
    }

    buildTypes {
        release { isMinifyEnabled = false }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    androidResources {
        // فایل‌های static/migrations فشرده نشوند تا کپی‌شان سریع باشد
        noCompress += listOf("woff2", "js", "css", "sql", "html")
    }
}

chaquopy {
    defaultConfig {
        version = "3.12"
        pip {
            // Chaquopy بسته‌ی pydantic-core (لازم برای pydantic 2) را ندارد؛ پس pydantic 1 (کاملاً پایتونی).
            // FastAPI 0.115.x هر دو نسخه را پشتیبانی می‌کند. (pydantic_compat.py تفاوت کوچک API را پر می‌کند)
            install("fastapi==0.115.6")
            install("uvicorn==0.34.0")
            install("pydantic>=1.10.17,<2")
            install("python-multipart==0.0.20")
            install("jdatetime>=5.0,<6")
            install("openpyxl>=3.1")
        }
    }
}

dependencies {
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.core:core-ktx:1.13.1")
}
