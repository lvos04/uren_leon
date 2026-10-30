package nl.leon.uren

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.time.DayOfWeek
import java.time.LocalDate

/** Een feestdag zoals ingesteld in de web-app (naam + hoe zwaar hij meetelt). */
data class Holiday(val date: LocalDate, val name: String, val factor: Double)

/** Nederlandse feestdagen. Zelfde berekening als op de server (server/app/holidays.py). */
object HolidayCalc {
    fun easter(year: Int): LocalDate {
        val a = year % 19
        val b = year / 100
        val c = year % 100
        val d = b / 4
        val e = b % 4
        val f = (b + 8) / 25
        val g = (b - f + 1) / 3
        val h = (19 * a + b - d - g + 15) % 30
        val i = c / 4
        val k = c % 4
        val l = (32 + 2 * e + 2 * i - h - k) % 7
        val m = (a + 11 * h + 22 * l) / 451
        val month = (h + l - 7 * m + 114) / 31
        val day = (h + l - 7 * m + 114) % 31 + 1
        return LocalDate.of(year, month, day)
    }

    /** Standaard ingeschakelde feestdagen (Goede Vrijdag en Bevrijdingsdag staan standaard uit), allemaal 2×. */
    fun defaults(year: Int): List<Holiday> {
        val e = easter(year)
        var koning = LocalDate.of(year, 4, 27)
        if (koning.dayOfWeek == DayOfWeek.SUNDAY) koning = LocalDate.of(year, 4, 26)
        return listOf(
            Holiday(LocalDate.of(year, 1, 1), "Nieuwjaarsdag", 2.0),
            Holiday(e, "1e Paasdag", 2.0),
            Holiday(e.plusDays(1), "2e Paasdag", 2.0),
            Holiday(koning, "Koningsdag", 2.0),
            Holiday(e.plusDays(39), "Hemelvaartsdag", 2.0),
            Holiday(e.plusDays(49), "1e Pinksterdag", 2.0),
            Holiday(e.plusDays(50), "2e Pinksterdag", 2.0),
            Holiday(LocalDate.of(year, 12, 25), "1e Kerstdag", 2.0),
            Holiday(LocalDate.of(year, 12, 26), "2e Kerstdag", 2.0),
        )
    }
}

/** Feestdagen uit de server (bewaard voor offline gebruik), met eigen berekening als terugval. */
class Holidays(context: Context) {
    private val p = context.getSharedPreferences("feestdagen", Context.MODE_PRIVATE)

    fun save(json: JSONObject) {
        p.edit().putString("data", json.toString()).apply()
    }

    private val cached: Pair<Double, Map<LocalDate, Holiday>>? by lazy {
        val raw = p.getString("data", null) ?: return@lazy null
        try {
            val o = JSONObject(raw)
            val arr: JSONArray = o.getJSONArray("holidays")
            val map = (0 until arr.length()).map { arr.getJSONObject(it) }.associate {
                val d = LocalDate.parse(it.getString("date"))
                d to Holiday(d, it.getString("name"), it.optDouble("factor", 2.0))
            }
            o.optDouble("sunday_factor", 2.0) to map
        } catch (e: Exception) {
            null
        }
    }

    private fun covered(d: LocalDate): Boolean {
        val range = p.getString("range", null)?.split("..") ?: return false
        return d.toString() >= range[0] && d.toString() <= range[1]
    }

    fun saveRange(start: LocalDate, end: LocalDate) {
        p.edit().putString("range", "$start..$end").apply()
    }

    fun get(d: LocalDate): Holiday? {
        val c = cached
        return if (c != null && covered(d)) c.second[d] else HolidayCalc.defaults(d.year).find { it.date == d }
    }

    val sundayFactor: Double get() = cached?.first ?: 2.0

    /** Voorinstelling voor een nog lege dag. */
    fun defaultFactor(d: LocalDate): Double = get(d)?.factor
        ?: if (d.dayOfWeek == DayOfWeek.SUNDAY) sundayFactor else 1.0
}

/** Werkdag (ma–vr) tot en met gisteren zonder uren, zonder vakantie en geen feestdag. */
fun isMissing(d: Day, first: LocalDate?, holiday: Holiday?, today: LocalDate = LocalDate.now()): Boolean =
    first != null && !d.date.isBefore(first) && d.date.isBefore(today) &&
        d.date.dayOfWeek.value <= 5 && d.hours == null && d.vakantie == 0.0 && holiday == null
