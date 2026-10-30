package nl.leon.uren

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.time.LocalDate

class ApiException(val code: Int, msg: String) : Exception(msg)

/** Verbinding met de server op TrueNAS (REST /api/v1, Bearer-token). */
class Api(private val prefs: Prefs) {

    private fun open(path: String, method: String = "GET"): HttpURLConnection {
        val c = URL(prefs.serverUrl + "/api/v1" + path).openConnection() as HttpURLConnection
        c.requestMethod = method
        c.connectTimeout = 10_000
        c.readTimeout = 30_000
        c.setRequestProperty("Authorization", "Bearer " + prefs.token)
        c.setRequestProperty("Accept", "application/json")
        return c
    }

    private fun HttpURLConnection.body(): String {
        val ok = responseCode in 200..299 || responseCode == 409
        // HttpURLConnection geeft bij code >= 400 de inhoud alleen via errorStream
        val s = (if (responseCode < 400) inputStream else errorStream)?.bufferedReader()?.use { it.readText() } ?: ""
        if (!ok) {
            throw ApiException(responseCode, when (responseCode) {
                401 -> "Token ongeldig"
                404 -> "Server-URL klopt niet"
                else -> "Serverfout $responseCode"
            })
        }
        return s
    }

    suspend fun ping(): Boolean = withContext(Dispatchers.IO) {
        JSONObject(open("/ping").body()).optBoolean("ok")
    }

    /** Stuurt een dag; geeft de serverversie terug als die nieuwer is (409). */
    suspend fun putDay(d: Day): Day? = withContext(Dispatchers.IO) {
        val c = open("/days/${d.date}", "PUT")
        c.doOutput = true
        c.setRequestProperty("Content-Type", "application/json")
        val body = JSONObject().apply {
            put("hours", d.hours ?: JSONObject.NULL)
            put("storing", d.storing)
            put("vakantie", d.vakantie)
            put("factor", d.factor)
            put("note", d.note ?: JSONObject.NULL)
            put("updated_at", d.updatedAt)
        }
        c.outputStream.use { it.write(body.toString().toByteArray()) }
        val text = c.body()
        if (c.responseCode == 409) Day.fromJson(JSONObject(text)) else null
    }

    suspend fun days(start: LocalDate, end: LocalDate): List<Day> = withContext(Dispatchers.IO) {
        val arr = JSONArray(open("/days?start=$start&end=$end").body())
        (0 until arr.length()).map { Day.fromJson(arr.getJSONObject(it)) }
    }

    suspend fun week(date: LocalDate): JSONObject = withContext(Dispatchers.IO) {
        JSONObject(open("/week/$date").body())
    }

    suspend fun month(year: Int, month: Int): JSONObject = withContext(Dispatchers.IO) {
        JSONObject(open("/month/$year/$month").body())
    }

    suspend fun downloadPdf(year: Int, month: Int, target: File): File = withContext(Dispatchers.IO) {
        val c = open("/print/$year/$month.pdf")
        c.setRequestProperty("Accept", "application/pdf")
        if (c.responseCode !in 200..299) c.body()
        target.parentFile?.mkdirs()
        c.inputStream.use { inp -> target.outputStream().use { inp.copyTo(it) } }
        target
    }
}
