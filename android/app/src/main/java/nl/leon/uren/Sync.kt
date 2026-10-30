package nl.leon.uren

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import java.time.LocalDate
import java.util.concurrent.TimeUnit

/** Stuurt lokale wijzigingen naar de server en haalt de laatste weken op. */
class SyncWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result {
        val prefs = Prefs(applicationContext)
        if (!prefs.configured) return Result.success()
        return try {
            Sync.run(applicationContext)
            Result.success()
        } catch (e: ApiException) {
            prefs.lastSyncError = e.message ?: "fout"
            if (e.code == 401 || e.code == 404) Result.failure() else Result.retry()
        } catch (e: Exception) {
            prefs.lastSyncError = "Geen verbinding met server"
            Result.retry()
        }
    }
}

object Sync {
    private val network = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()

    /** Direct (zodra er netwerk is) synchroniseren. */
    fun enqueue(context: Context) {
        val req = OneTimeWorkRequestBuilder<SyncWorker>()
            .setConstraints(network)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork("sync", ExistingWorkPolicy.REPLACE, req)
    }

    /** Achtergrond-synchronisatie elke 6 uur (vangnet). */
    fun schedulePeriodic(context: Context) {
        val req = PeriodicWorkRequestBuilder<SyncWorker>(6, TimeUnit.HOURS).setConstraints(network).build()
        WorkManager.getInstance(context).enqueueUniquePeriodicWork("sync-periodiek", ExistingPeriodicWorkPolicy.KEEP, req)
    }

    suspend fun run(context: Context) {
        val prefs = Prefs(context)
        val store = DayStore(context)
        val api = Api(prefs)
        for (d in store.dirty()) {
            val newer = api.putDay(d)
            if (newer != null) store.replace(newer) else store.markSynced(d)
        }
        val end = LocalDate.now().plusDays(7)
        val start = LocalDate.now().minusWeeks(8)
        store.mergeFromServer(start, end, api.days(start, end))
        runCatching { prefs.contractHours = api.week(LocalDate.now()).optDouble("contract", 40.0) }
        prefs.lastSync = nowIso()
        prefs.lastSyncError = ""
    }
}
