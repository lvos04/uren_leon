package nl.leon.uren

import android.Manifest
import android.app.AlarmManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.app.RemoteInput
import androidx.core.content.ContextCompat
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.ZoneId

/**
 * Dagelijkse herinnering (standaard 20:00, tweede om 21:30), maandag t/m zaterdag.
 * Zondag en ingeschakelde feestdagen worden overgeslagen. Vanuit de melding kun je direct uren invullen.
 */
object Reminder {
    const val CHANNEL = "herinnering"
    const val NOTIF_ID = 1
    const val KEY_HOURS = "uren"
    const val EXTRA_HOURS = "uren"
    private const val REQ = 1001

    /** Volgende herinnering na 'now' op een van de tijden, niet op een dag waarvoor skip() true geeft. */
    fun nextTrigger(now: LocalDateTime, times: List<LocalTime>, skip: (LocalDate) -> Boolean = { false }): LocalDateTime? {
        if (times.isEmpty()) return null
        var day = now.toLocalDate()
        repeat(14) {
            if (day.dayOfWeek != DayOfWeek.SUNDAY && !skip(day)) {
                times.sorted().map { day.atTime(it) }.firstOrNull { it.isAfter(now) }?.let { return it }
            }
            day = day.plusDays(1)
        }
        return null
    }

    fun nextTrigger(now: LocalDateTime, hour: Int, minute: Int): LocalDateTime =
        nextTrigger(now, listOf(LocalTime.of(hour, minute)))!!

    fun times(prefs: Prefs): List<LocalTime> = buildList {
        if (prefs.reminderOn) {
            add(LocalTime.of(prefs.reminderHour, prefs.reminderMinute))
            if (prefs.reminder2On) add(LocalTime.of(prefs.reminder2Hour, prefs.reminder2Minute))
        }
    }

    fun schedule(context: Context) {
        val prefs = Prefs(context)
        val am = context.getSystemService(AlarmManager::class.java)
        val pi = pending(context)
        am.cancel(pi)
        val hol = Holidays(context)
        val at = nextTrigger(LocalDateTime.now(), times(prefs)) { prefs.skipHolidays && hol.get(it) != null } ?: return
        val millis = at.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
        // Niet-exact alarm (geen extra toestemming nodig); Android levert het binnen enkele minuten.
        am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, millis, pi)
    }

    private fun pending(context: Context): PendingIntent = PendingIntent.getBroadcast(
        context, REQ, Intent(context, ReminderReceiver::class.java),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )

    fun createChannel(context: Context) {
        val ch = NotificationChannel(CHANNEL, "Dagelijkse herinnering", NotificationManager.IMPORTANCE_DEFAULT)
        ch.description = "Herinnering om je uren in te vullen"
        context.getSystemService(NotificationManager::class.java).createNotificationChannel(ch)
    }

    private fun allowed(context: Context) = Build.VERSION.SDK_INT < 33 ||
        ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    /** Twee meest ingevulde aantallen uren van de laatste 4 weken (standaard 8 en 10). */
    fun quickHours(context: Context): List<Double> {
        val today = LocalDate.now()
        val freq = DayStore(context).range(today.minusDays(28), today).mapNotNull { it.hours }
            .filter { it > 0 }.groupingBy { it }.eachCount().entries
            .sortedWith(compareByDescending<Map.Entry<Double, Int>> { it.value }.thenBy { it.key }).map { it.key }
        return (freq + listOf(8.0, 10.0, 9.0)).distinct().take(2).sorted()
    }

    fun notify(context: Context, text: String = "Hoeveel uur heb je vandaag gewerkt?") {
        if (!allowed(context)) return
        createChannel(context)
        val open = PendingIntent.getActivity(
            context, 0,
            Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val b = NotificationCompat.Builder(context, CHANNEL)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle("Uren invullen")
            .setContentText(text)
            .setContentIntent(open)
            .setAutoCancel(true)
            .setOnlyAlertOnce(true)
        quickHours(context).forEachIndexed { i, h ->
            val pi = PendingIntent.getBroadcast(
                context, 2000 + i,
                Intent(context, QuickEntryReceiver::class.java).putExtra(EXTRA_HOURS, h),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
            b.addAction(0, "${fmtHours(h)} uur", pi)
        }
        // "Typ uren": invoerveld in de melding zelf
        val input = RemoteInput.Builder(KEY_HOURS).setLabel("Aantal uren, bv. 9,5").build()
        val typePi = PendingIntent.getBroadcast(
            context, 2100, Intent(context, QuickEntryReceiver::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE,
        )
        b.addAction(NotificationCompat.Action.Builder(0, "Typ uren", typePi).addRemoteInput(input).build())
        NotificationManagerCompat.from(context).notify(NOTIF_ID, b.build())
    }

    fun confirm(context: Context, text: String) {
        if (!allowed(context)) return
        val n = NotificationCompat.Builder(context, CHANNEL)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(text)
            .setTimeoutAfter(5000)
            .setAutoCancel(true)
            .build()
        NotificationManagerCompat.from(context).notify(NOTIF_ID, n)
    }
}

/** Uren opslaan vanuit de knoppen of het invoerveld in de melding. */
class QuickEntryReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val typed = RemoteInput.getResultsFromIntent(intent)?.getCharSequence(Reminder.KEY_HOURS)?.toString()
        val hours = if (typed != null) parseHours(typed) else intent.getDoubleExtra(Reminder.EXTRA_HOURS, -1.0)
        if (hours == null || hours < 0 || hours > 24) {
            Reminder.notify(context, "Ongeldig aantal uren. Probeer het opnieuw, bv. 9,5")
            return
        }
        val today = LocalDate.now()
        val store = DayStore(context)
        val cur = store.get(today)
        val factor = if (cur.isEmpty) Holidays(context).defaultFactor(today) else cur.factor
        store.edit(cur.copy(hours = hours, factor = factor))
        Sync.enqueue(context)
        Reminder.confirm(context, "✓ ${fmtHours(hours)} uur opgeslagen voor vandaag")
    }
}

class ReminderReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val today = LocalDate.now()
        val day = DayStore(context).get(today)
        val filled = day.hours != null || day.vakantie > 0
        val prefs = Prefs(context)
        val holiday = prefs.skipHolidays && Holidays(context).get(today) != null
        if (today.dayOfWeek != DayOfWeek.SUNDAY && !holiday && !filled) Reminder.notify(context)
        Reminder.schedule(context)
    }
}

/** Na herstart of tijdwijziging de herinnering opnieuw plannen. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        Reminder.schedule(context)
        Sync.schedulePeriodic(context)
    }
}
