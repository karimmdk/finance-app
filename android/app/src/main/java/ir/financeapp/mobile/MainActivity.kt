package ir.financeapp.mobile

import android.annotation.SuppressLint
import android.content.ActivityNotFoundException
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import android.provider.MediaStore
import android.provider.Settings
import android.util.Base64
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowInsets
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.MimeTypeMap
import android.webkit.RenderProcessGoneDetail
import android.webkit.URLUtil
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONObject
import java.io.DataInputStream
import java.io.File
import java.io.IOException
import java.io.OutputStream
import java.net.HttpURLConnection
import java.net.URL

class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var statusView: TextView

    private var fileCallback: ValueCallback<Array<Uri>>? = null

    // پوشه دیتابیس که واقعاً استفاده شد + امضای فایل در لحظه خروج از برنامه (برای تشخیص تغییر توسط سینک)
    private var usedDbDir: String? = null
    private var dbSignature: String? = null
    private var permissionDialog: AlertDialog? = null

    private val fileChooser =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            val uris = WebChromeClient.FileChooserParams.parseResult(result.resultCode, result.data)
            fileCallback?.onReceiveValue(uris)
            fileCallback = null
        }

    private val pickBackup =
        registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
            if (uri != null) confirmRestore(uri)
        }

    companion object {
        // مقدار بین بازسازی‌های Activity در همان process حفظ می‌شود (سرور فقط یک‌بار بالا می‌آید)
        @Volatile private var port = 0
        @Volatile private var token = ""
        @Volatile private var starting = false
        private const val PREFS = "finance_prefs"
        private const val PREF_DB_DIR = "db_dir"
        private const val HOOK_JS = """
            (function(){
              if (window.__faHooked) return; window.__faHooked = true;
              var o = HTMLAnchorElement.prototype.click;
              HTMLAnchorElement.prototype.click = function(){
                try { if (this.download) window.__faName = this.download; } catch(e) {}
                return o.apply(this, arguments);
              };
            })();
        """
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val root = FrameLayout(this)
        root.setBackgroundColor(Color.parseColor("#F9FAFB"))
        // اندروید ۱۵ به بعد محتوا را زیر نوار وضعیت می‌کشد؛ پس خودمان حاشیه (نوار وضعیت/برش/صفحه‌کلید) را می‌دهیم
        root.setOnApplyWindowInsetsListener { v, insets ->
            try {
                val bars = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
                val ime = insets.getInsets(WindowInsets.Type.ime())
                v.setPadding(bars.left, bars.top, bars.right, maxOf(bars.bottom, ime.bottom))
            } catch (_: Throwable) {
            }
            WindowInsets.CONSUMED
        }
        webView = WebView(this).apply {
            visibility = View.INVISIBLE
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT
            )
        }
        statusView = TextView(this).apply {
            text = getString(R.string.loading)
            textSize = 18f
            setTextColor(Color.GRAY)
            gravity = Gravity.CENTER
        }
        root.addView(webView)
        root.addView(
            statusView,
            FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT
            )
        )
        setContentView(root)

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = false
            allowContentAccess = false
            textZoom = 100
        }
        CookieManager.getInstance().setAcceptCookie(true)
        webView.addJavascriptInterface(Bridge(), "AndroidBridge")

        webView.webViewClient = object : WebViewClient() {
            override fun onPageStarted(view: WebView, url: String?, favicon: android.graphics.Bitmap?) {
                view.evaluateJavascript(HOOK_JS, null)
            }

            override fun onPageFinished(view: WebView, url: String?) {
                view.evaluateJavascript(HOOK_JS, null)
            }

            override fun onRenderProcessGone(view: WebView, detail: RenderProcessGoneDetail): Boolean {
                // بدون این، مرگ پردازش رندر WebView کل برنامه را می‌بندد؛ به‌جایش صفحه از نو ساخته می‌شود
                runOnUiThread {
                    (view.parent as? ViewGroup)?.removeView(view)
                    view.destroy()
                    recreate()
                }
                return true
            }

            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val uri = request.url
                if (uri.host == "127.0.0.1" || uri.scheme == "blob") return false
                try {
                    startActivity(Intent(Intent.ACTION_VIEW, uri))
                } catch (_: ActivityNotFoundException) {
                }
                return true
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(
                view: WebView,
                callback: ValueCallback<Array<Uri>>,
                params: FileChooserParams
            ): Boolean {
                fileCallback?.onReceiveValue(null)
                fileCallback = callback
                return try {
                    fileChooser.launch(params.createIntent())
                    true
                } catch (_: ActivityNotFoundException) {
                    fileCallback = null
                    callback.onReceiveValue(null)
                    false
                }
            }
        }

        webView.setDownloadListener { url, _, contentDisposition, mimeType, _ ->
            if (url.startsWith("blob:")) downloadBlob(url) else downloadHttp(url, contentDisposition, mimeType)
        }

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                // اول کشوی منو را ببند / از هر صفحه به داشبورد برگرد؛ فقط از داشبورد خارج شو
                webView.evaluateJavascript("window.faBack ? window.faBack() : false") { result ->
                    if (result == "true") return@evaluateJavascript
                    if (webView.canGoBack()) {
                        webView.goBack()
                    } else {
                        isEnabled = false
                        onBackPressedDispatcher.onBackPressed()
                    }
                }
            }
        })

        showPreviousCrash()
        bootstrap()
    }

    private fun showPreviousCrash() {
        try {
            val f = File(filesDir, "last_crash.txt")
            if (!f.exists()) return
            val text = f.readText()
            f.delete()
            AlertDialog.Builder(this)
                .setTitle(R.string.crash_title)
                .setMessage(text.take(3500))
                .setPositiveButton(R.string.close, null)
                .show()
        } catch (_: Throwable) {
        }
    }

    // ------------------------------------------------------ storage / bootstrap

    /** پوشه‌ای که finance.db در آن است (برای سینک با MEGA و غیره). قابل تغییر از منو. */
    private fun configuredDbDir(): String {
        val saved = getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(PREF_DB_DIR, null)
        if (!saved.isNullOrBlank()) return saved
        return File(
            Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOCUMENTS), "FinanceApp"
        ).absolutePath
    }

    private fun bootstrap() {
        when {
            port != 0 -> openApp()
            !Environment.isExternalStorageManager() -> askStorageAccess()
            else -> startServerAndOpen()
        }
    }

    private fun askStorageAccess() {
        statusView.text = getString(R.string.need_storage_title)
        permissionDialog = AlertDialog.Builder(this)
            .setTitle(R.string.need_storage_title)
            .setMessage(getString(R.string.need_storage_msg, configuredDbDir()))
            .setCancelable(false)
            .setPositiveButton(R.string.open_settings) { _, _ ->
                try {
                    startActivity(
                        Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION, Uri.parse("package:$packageName"))
                    )
                } catch (_: Exception) {
                    startActivity(Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION))
                }
            }
            .setNegativeButton(R.string.exit) { _, _ -> finish() }
            .show()
    }

    override fun onResume() {
        super.onResume()
        // بعد از برگشت از صفحه تنظیمات دسترسی
        if (port == 0 && !starting) {
            if (Environment.isExternalStorageManager()) startServerAndOpen()
            else if (permissionDialog?.isShowing != true) askStorageAccess()
        }
    }

    // ---------------------------------------------------- sync-friendly lifecycle

    private fun dbFile() = usedDbDir?.let { File(it, "finance.db") }

    private fun signature(): String? = dbFile()?.takeIf { it.exists() }?.let { "${it.length()}:${it.lastModified()}" }

    /** همه تغییرات را داخل finance.db ثبت کن؛ بعد از این فایل کامل و آماده سینک است. */
    private fun flushDb() {
        if (port == 0) return
        try {
            Python.getInstance().getModule("android_main").callAttr("flush")
        } catch (_: Throwable) {
        }
        dbSignature = signature()
    }

    override fun onStop() {
        flushDb()
        super.onStop()
    }

    override fun onStart() {
        super.onStart()
        // اگر در پس‌زمینه ابزار سینک فایل را عوض کرده، با فایل جدید دوباره شروع کن
        val before = dbSignature
        if (port != 0 && before != null && signature() != before) restartApp()
    }

    // ---------------------------------------------------------------- server

    private fun startServerAndOpen() {
        if (starting) return
        starting = true
        Thread {
            try {
                val payload = File(filesDir, "payload")
                payload.deleteRecursively()
                copyAsset("payload", payload)

                if (!Python.isStarted()) Python.start(AndroidPlatform(this))
                val result = Python.getInstance().getModule("android_main")
                    .callAttr("start", filesDir.absolutePath, payload.absolutePath, configuredDbDir())
                    .asList()
                port = result[0].toInt()
                token = result[1].toString()
                usedDbDir = result[2].toString()
                val warning = result[3].toString()
                if (warning.isNotEmpty()) toast(getString(R.string.fallback_private, warning))

                waitForServer()
                runOnUiThread { openApp() }
            } catch (e: Throwable) {
                starting = false
                runOnUiThread {
                    statusView.text = getString(R.string.start_failed, e.message ?: e.toString())
                }
            }
        }.start()
    }

    private fun copyAsset(assetPath: String, target: File) {
        val children = assets.list(assetPath) ?: emptyArray()
        if (children.isEmpty()) {
            target.parentFile?.mkdirs()
            assets.open(assetPath).use { input -> target.outputStream().use { input.copyTo(it) } }
        } else {
            target.mkdirs()
            for (name in children) copyAsset("$assetPath/$name", File(target, name))
        }
    }

    private fun waitForServer() {
        val deadline = System.currentTimeMillis() + 40_000
        while (System.currentTimeMillis() < deadline) {
            try {
                val c = URL("http://127.0.0.1:$port/api/health").openConnection() as HttpURLConnection
                c.setRequestProperty("Cookie", "fa_token=$token")
                c.connectTimeout = 1000
                c.readTimeout = 1000
                if (c.responseCode == 200) return
            } catch (_: IOException) {
            }
            Thread.sleep(200)
        }
        throw IOException("Server did not start in time")
    }

    private fun openApp() {
        if (usedDbDir == null) {
            // Activity بعد از بازسازی: مسیر را از Python بخوان
            usedDbDir = try {
                Python.getInstance().getModule("android_main").callAttr("start", "", "").asList()[2].toString()
            } catch (_: Throwable) { null }
        }
        dbSignature = signature()
        val base = "http://127.0.0.1:$port"
        CookieManager.getInstance().apply {
            setCookie(base, "fa_token=$token; Path=/")
            flush()
        }
        webView.loadUrl("$base/")
        webView.visibility = View.VISIBLE
        statusView.visibility = View.GONE
    }

    // ------------------------------------------------------------- downloads

    private fun toast(msg: String) = runOnUiThread { Toast.makeText(this, msg, Toast.LENGTH_LONG).show() }

    private fun saveToDownloads(name: String, mime: String, write: (OutputStream) -> Unit) {
        try {
            val values = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, name)
                put(MediaStore.Downloads.MIME_TYPE, mime)
                put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
            }
            val uri = contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                ?: throw IOException("insert failed")
            contentResolver.openOutputStream(uri)?.use(write) ?: throw IOException("open failed")
            toast(getString(R.string.saved_to_downloads, name))
        } catch (e: Exception) {
            toast(getString(R.string.save_failed) + ": " + (e.message ?: ""))
        }
    }

    private fun downloadHttp(url: String, contentDisposition: String?, mimeType: String?) {
        Thread {
            try {
                val c = URL(url).openConnection() as HttpURLConnection
                c.setRequestProperty("Cookie", "fa_token=$token")
                val mime = mimeType ?: c.contentType ?: "application/octet-stream"
                val name = URLUtil.guessFileName(url, contentDisposition, mime)
                saveToDownloads(name, mime) { out -> c.inputStream.use { it.copyTo(out) } }
            } catch (e: Exception) {
                toast(getString(R.string.save_failed) + ": " + (e.message ?: ""))
            }
        }.start()
    }

    private fun downloadBlob(blobUrl: String) {
        val js = """
            (function(u){
              fetch(u).then(function(r){return r.blob();}).then(function(b){
                var fr = new FileReader();
                fr.onloadend = function(){
                  AndroidBridge.saveBlob(window.__faName || '', b.type || 'application/octet-stream', fr.result);
                  window.__faName = '';
                };
                fr.readAsDataURL(b);
              });
            })(${JSONObject.quote(blobUrl)});
        """
        webView.post { webView.evaluateJavascript(js, null) }
    }

    private inner class Bridge {
        @JavascriptInterface
        fun showMenu() {
            runOnUiThread { showAppMenu() }
        }

        @JavascriptInterface
        fun saveBlob(fileName: String, mime: String, dataUrl: String) {
            val bytes = Base64.decode(dataUrl.substringAfter("base64,"), Base64.DEFAULT)
            val ext = MimeTypeMap.getSingleton().getExtensionFromMimeType(mime) ?: "bin"
            val name = fileName.ifBlank { "download-${System.currentTimeMillis()}.$ext" }
            saveToDownloads(name, mime) { it.write(bytes) }
        }
    }

    // --------------------------------------------------------------- restore

    private fun showAppMenu() {
        val items = arrayOf(
            getString(R.string.menu_reload),
            getString(R.string.menu_restore),
            getString(R.string.menu_db_dir),
            getString(R.string.menu_quit)
        )
        AlertDialog.Builder(this)
            .setItems(items) { _, which ->
                when (which) {
                    0 -> webView.reload()
                    1 -> pickBackup.launch(arrayOf("*/*"))
                    2 -> changeDbDir()
                    3 -> quitCompletely()
                }
            }
            .show()
    }

    private fun confirmRestore(uri: Uri) {
        AlertDialog.Builder(this)
            .setTitle(R.string.restore_title)
            .setMessage(R.string.restore_msg)
            .setPositiveButton(R.string.yes) { _, _ -> stageRestore(uri) }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    private fun stageRestore(uri: Uri) {
        Thread {
            try {
                val header = ByteArray(16)
                contentResolver.openInputStream(uri)?.use { DataInputStream(it).readFully(header) }
                    ?: throw IOException("open failed")
                if (String(header, Charsets.ISO_8859_1) != "SQLite format 3\u0000") {
                    toast(getString(R.string.not_sqlite))
                    return@Thread
                }
                val dir = File(filesDir, "data").apply { mkdirs() }
                val tmp = File(dir, "restore_pending.db.tmp")
                contentResolver.openInputStream(uri)!!.use { i -> tmp.outputStream().use { i.copyTo(it) } }
                tmp.renameTo(File(dir, "restore_pending.db"))
                runOnUiThread { restartApp() }
            } catch (e: Exception) {
                toast(getString(R.string.not_sqlite) + " (" + (e.message ?: "") + ")")
            }
        }.start()
    }

    private fun restartApp() {
        val intent = packageManager.getLaunchIntentForPackage(packageName)!!
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
        startActivity(intent)
        finishAffinity()
        Runtime.getRuntime().exit(0) // process جدید با فایل بازیابی‌شده شروع می‌شود
    }

    private fun changeDbDir() {
        val input = EditText(this).apply {
            setText(configuredDbDir())
            setSingleLine(true)
            textDirection = View.TEXT_DIRECTION_LTR
        }
        AlertDialog.Builder(this)
            .setTitle(R.string.menu_db_dir)
            .setMessage(getString(R.string.db_dir_msg, usedDbDir ?: configuredDbDir()))
            .setView(input)
            .setPositiveButton(R.string.save_and_restart) { _, _ ->
                val dir = input.text.toString().trim()
                if (dir.startsWith("/")) {
                    flushDb()
                    getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString(PREF_DB_DIR, dir).apply()
                    restartApp()
                }
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    /** ذخیره کامل و بستن process تا هیچ اتصالی به دیتابیس باز نماند؛ بعد از آن سینک کنید. */
    private fun quitCompletely() {
        flushDb()
        finishAffinity()
        Runtime.getRuntime().exit(0)
    }

    override fun onDestroy() {
        fileCallback?.onReceiveValue(null)
        fileCallback = null
        if (isFinishing && port != 0) {
            // خروج با دکمه Back: تغییرات ثبت شود و process بسته شود تا فایل برای سینک آزاد باشد
            flushDb()
            super.onDestroy()
            Runtime.getRuntime().exit(0)
            return
        }
        super.onDestroy()
    }
}
