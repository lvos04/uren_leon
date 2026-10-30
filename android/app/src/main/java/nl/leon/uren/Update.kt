package nl.leon.uren

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.core.content.FileProvider
import java.io.File

/** Nieuwe app-versie van de server halen en de Android-installer openen. */
object Update {
    /** Geeft (versionCode, versionName) terug als de server een nieuwere app heeft. */
    suspend fun check(context: Context): Pair<Int, String>? {
        val prefs = Prefs(context)
        if (!prefs.configured) return null
        val info = Api(prefs).appVersion()
        val code = info.optInt("versionCode", 0)
        return if (code > BuildConfig.VERSION_CODE) code to info.optString("versionName") else null
    }

    suspend fun downloadAndInstall(context: Context) {
        val pm = context.packageManager
        if (!pm.canRequestPackageInstalls()) {
            // Eenmalig toestaan dat deze app updates mag installeren
            context.startActivity(
                Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + context.packageName))
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            )
            return
        }
        val file = Api(Prefs(context)).downloadApk(File(context.cacheDir, "apk/uren.apk"))
        val uri = FileProvider.getUriForFile(context, context.packageName + ".files", file)
        context.startActivity(
            Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/vnd.android.package-archive")
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        )
    }
}

/** Koppel-link uit de web-app: uren://koppel?url=...&token=... */
fun parsePairLink(link: String?): Pair<String, String>? {
    if (link == null) return null
    val uri = try { java.net.URI(link) } catch (e: Exception) { return null }
    if (uri.scheme != "uren" || uri.host != "koppel") return null
    val params = (uri.rawQuery ?: "").split("&").mapNotNull {
        val i = it.indexOf('=')
        if (i <= 0) null else it.substring(0, i) to java.net.URLDecoder.decode(it.substring(i + 1), "UTF-8")
    }.toMap()
    val url = params["url"]?.trim()?.trimEnd('/') ?: return null
    val token = params["token"]?.trim() ?: return null
    if (!(url.startsWith("http://") || url.startsWith("https://")) || token.isEmpty()) return null
    return url to token
}
