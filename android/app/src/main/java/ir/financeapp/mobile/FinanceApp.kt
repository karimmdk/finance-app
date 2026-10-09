package ir.financeapp.mobile

import android.app.Application
import android.content.ContentValues
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import java.io.File
import java.io.PrintWriter
import java.io.StringWriter
import java.util.Date

/**
 * اگر برنامه به‌خاطر خطا بسته شود، گزارش خطا ذخیره می‌شود:
 *  - داخل پوشه Downloads (فایل finance-crash.txt) — حتی اگر برنامه دیگر باز نشود قابل دیدن/ارسال است
 *  - و دفعه بعد که برنامه باز شد، متن خطا در یک پنجره نشان داده می‌شود.
 */
class FinanceApp : Application() {
    override fun onCreate() {
        super.onCreate()
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, error ->
            try {
                val sw = StringWriter()
                error.printStackTrace(PrintWriter(sw))
                val text = "Finance app crash\n${Date()}\n" +
                    "thread=${thread.name}\nandroid=${Build.VERSION.SDK_INT} device=${Build.MANUFACTURER} ${Build.MODEL}\n\n$sw"
                File(filesDir, "last_crash.txt").writeText(text)
                saveToDownloads(text)
            } catch (_: Throwable) {
            }
            previous?.uncaughtException(thread, error)
        }
    }

    private fun saveToDownloads(text: String) {
        val values = ContentValues().apply {
            put(MediaStore.Downloads.DISPLAY_NAME, "finance-crash.txt")
            put(MediaStore.Downloads.MIME_TYPE, "text/plain")
            put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
        }
        val uri = contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values) ?: return
        contentResolver.openOutputStream(uri)?.use { it.write(text.toByteArray()) }
    }
}
