package nl.leon.uren

import android.content.Context
import org.json.JSONObject
import java.io.File
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

/** Eén dag. hours == null betekent: niet ingevuld. factor = 1, 1.5 of 2 (zon-/feestdag telt dubbel). */
data class Day(
    val date: LocalDate,
    val hours: Double? = null,
    val storing: Boolean = false,
    val vakantie: Double = 0.0,
    val factor: Double = 1.0,
    val note: String? = null,
    val updatedAt: String = nowIso(),
    val dirty: Boolean = false,
) {
    val isEmpty get() = hours == null && !storing && vakantie == 0.0 && factor == 1.0 && note.isNullOrBlank()
    val weighted get() = (hours ?: 0.0) * factor

    fun toJson(): JSONObject = JSONObject().apply {
        put("date", date.toString())
        put("hours", hours ?: JSONObject.NULL)
        put("storing", storing)
        put("vakantie", vakantie)
        put("factor", factor)
        put("note", note ?: JSONObject.NULL)
        put("updated_at", updatedAt)
        put("dirty", dirty)
    }

    companion object {
        fun fromJson(o: JSONObject) = Day(
            date = LocalDate.parse(o.getString("date")),
            hours = if (o.isNull("hours")) null else o.getDouble("hours"),
            storing = o.optBoolean("storing"),
            vakantie = o.optDouble("vakantie", 0.0),
            factor = o.optDouble("factor", 1.0),
            note = if (o.isNull("note")) null else o.optString("note"),
            updatedAt = o.optString("updated_at", nowIso()),
            dirty = o.optBoolean("dirty"),
        )
    }
}

fun nowIso(): String = LocalDateTime.now().withNano(0).format(DateTimeFormatter.ISO_LOCAL_DATE_TIME)

fun fmtHours(v: Double?): String {
    if (v == null) return ""
    return if (v % 1.0 == 0.0) v.toLong().toString() else "%.2f".format(v).trimEnd('0').replace('.', ',')
}

fun parseHours(s: String): Double? = s.trim().replace(',', '.').takeIf { it.isNotEmpty() }?.toDoubleOrNull()

/** Lokale opslag van de dagen (werkt offline). Gewijzigde dagen staan op dirty tot ze naar de server zijn gestuurd. */
class DayStore(context: Context) {
    private val file = File(context.filesDir, "days.json")

    @Synchronized
    private fun load(): MutableMap<String, Day> {
        if (!file.exists()) return mutableMapOf()
        return try {
            val o = JSONObject(file.readText())
            o.keys().asSequence().associateWith { Day.fromJson(o.getJSONObject(it)) }.toMutableMap()
        } catch (e: Exception) {
            mutableMapOf()
        }
    }

    @Synchronized
    private fun save(map: Map<String, Day>) {
        val o = JSONObject()
        map.forEach { (k, v) -> o.put(k, v.toJson()) }
        val tmp = File(file.parentFile, "days.json.tmp")
        tmp.writeText(o.toString())
        tmp.renameTo(file)
    }

    @Synchronized
    fun get(date: LocalDate): Day = load()[date.toString()] ?: Day(date)

    @Synchronized
    fun range(start: LocalDate, end: LocalDate): List<Day> {
        val m = load()
        return generateSequence(start) { it.plusDays(1) }.takeWhile { !it.isAfter(end) }
            .map { m[it.toString()] ?: Day(it) }.toList()
    }

    /** Lokale wijziging: markeren voor synchronisatie. */
    @Synchronized
    fun edit(day: Day) {
        val m = load()
        m[day.date.toString()] = day.copy(updatedAt = nowIso(), dirty = true)
        save(m)
    }

    @Synchronized
    fun dirty(): List<Day> = load().values.filter { it.dirty }

    @Synchronized
    fun markSynced(day: Day) {
        val m = load()
        val cur = m[day.date.toString()]
        if (cur != null && cur.updatedAt == day.updatedAt) {
            if (cur.isEmpty) m.remove(day.date.toString()) else m[day.date.toString()] = cur.copy(dirty = false)
            save(m)
        }
    }

    /** Serverversie wint (server had een nieuwere wijziging). */
    @Synchronized
    fun replace(day: Day) {
        val m = load()
        m[day.date.toString()] = day.copy(dirty = false)
        save(m)
    }

    /** Gegevens van de server overnemen, behalve dagen met een nog niet verstuurde lokale wijziging. */
    @Synchronized
    fun mergeFromServer(start: LocalDate, end: LocalDate, server: List<Day>) {
        val m = load()
        val byDate = server.associateBy { it.date.toString() }
        var d = start
        while (!d.isAfter(end)) {
            val key = d.toString()
            val local = m[key]
            if (local == null || !local.dirty) {
                val s = byDate[key]
                if (s == null) m.remove(key) else m[key] = s.copy(dirty = false)
            }
            d = d.plusDays(1)
        }
        save(m)
    }
}

class Prefs(context: Context) {
    private val p = context.getSharedPreferences("uren", Context.MODE_PRIVATE)
    var serverUrl: String
        get() = p.getString("server", "") ?: ""
        set(v) = p.edit().putString("server", v.trim().trimEnd('/')).apply()
    var token: String
        get() = p.getString("token", "") ?: ""
        set(v) = p.edit().putString("token", v.trim()).apply()
    var reminderOn: Boolean
        get() = p.getBoolean("rem_on", true)
        set(v) = p.edit().putBoolean("rem_on", v).apply()
    var reminderHour: Int
        get() = p.getInt("rem_h", 20)
        set(v) = p.edit().putInt("rem_h", v).apply()
    var reminderMinute: Int
        get() = p.getInt("rem_m", 0)
        set(v) = p.edit().putInt("rem_m", v).apply()
    var contractHours: Double
        get() = p.getFloat("contract", 40f).toDouble()
        set(v) = p.edit().putFloat("contract", v.toFloat()).apply()
    var lastSync: String
        get() = p.getString("last_sync", "") ?: ""
        set(v) = p.edit().putString("last_sync", v).apply()
    var lastSyncError: String
        get() = p.getString("last_sync_err", "") ?: ""
        set(v) = p.edit().putString("last_sync_err", v).apply()
    val configured get() = serverUrl.isNotBlank() && token.isNotBlank()
}
