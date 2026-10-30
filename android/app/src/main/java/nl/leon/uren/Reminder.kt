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
import androidx.core.content.ContextCompat
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.ZoneId

/** Dagelijkse herinnering (standaard 20:00), maandag t/m zaterdag. Zondag wordt overgeslagen. */
object Reminder {
    const val CHANNEL = "herinnering"
    private const val REQ = 1001

    /** Volgende moment op uur:minuut, niet op zondag, na 'now'. */
    fun nextTrigger(now: LocalDateTime, hour: Int, minute: Int): LocalDateTime {
        var t = now.toLocalDate().atTime(hour, minute)
        if (!t.isAfter(now)) t = t.plusDays(1)
        while (t.dayOfWeek == DayOfWeek.SUNDAY) t = t.plusDays(1)
        return t
    }

    fun schedule(context: Context) {
        val prefs = Prefs(context)
        val am = context.getSystemService(AlarmManager::class.java)
        val pi = pending(context)
        am.cancel(pi)
        if (!prefs.reminderOn) return
        val at = nextTrigger(LocalDateTime.now(), prefs.reminderHour, prefs.reminderMinute)
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

    fun notify(context: Context) {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) return
        createChannel(context)
        val open = PendingIntent.getActivity(
            context, 0,
            Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val n = NotificationCompat.Builder(context, CHANNEL)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle("Uren invullen")
            .setContentText("Hoeveel uur heb je vandaag gewerkt?")
            .setContentIntent(open)
            .setAutoCancel(true)
            .build()
        NotificationManagerCompat.from(context).notify(1, n)
    }
}

class ReminderReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val today = LocalDate.now()
        val day = DayStore(context).get(today)
        val filled = day.hours != null || day.vakantie > 0
        if (today.dayOfWeek != DayOfWeek.SUNDAY && !filled) Reminder.notify(context)
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
