package nl.leon.uren

import android.Manifest
import android.app.DatePickerDialog
import android.app.TimePickerDialog
import android.content.Intent
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.MutableState
import androidx.compose.runtime.key
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import kotlinx.coroutines.launch
import java.io.File
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.YearMonth
import java.time.format.DateTimeFormatter
import java.time.format.TextStyle
import java.time.temporal.IsoFields
import java.util.Locale

private val NL = Locale("nl", "NL")
private val DAY_FMT = DateTimeFormatter.ofPattern("EEEE d MMMM", NL)

class MainActivity : ComponentActivity() {
    private val askNotify = registerForActivityResult(ActivityResultContracts.RequestPermission()) { }
    private val pairedEvent = mutableStateOf<String?>(null)

    private fun handlePairLink(intent: Intent?) {
        val pair = parsePairLink(intent?.dataString) ?: return
        val prefs = Prefs(this)
        prefs.serverUrl = pair.first
        prefs.token = pair.second
        prefs.lastSyncError = ""
        Sync.enqueue(this)
        pairedEvent.value = pair.first
        intent?.data = null
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handlePairLink(intent)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        handlePairLink(intent)
        Reminder.createChannel(this)
        Reminder.schedule(this)
        Sync.schedulePeriodic(this)
        Sync.enqueue(this)
        if (Build.VERSION.SDK_INT >= 33) askNotify.launch(Manifest.permission.POST_NOTIFICATIONS)
        setContent {
            MaterialTheme(colorScheme = if (isSystemInDarkTheme()) darkColorScheme() else lightColorScheme()) {
                App(pairedEvent)
            }
        }
    }
}

@Composable
fun App(paired: MutableState<String?>) {
    val ctx = LocalContext.current
    val prefs = remember { Prefs(ctx) }
    var tab by remember { mutableIntStateOf(if (prefs.configured) 0 else 3) }
    var selected by remember { mutableStateOf(LocalDate.now()) }
    val snack = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()
    var update by remember { mutableStateOf<Pair<Int, String>?>(null) }
    var settingsKey by remember { mutableIntStateOf(0) }

    LaunchedEffect(paired.value) {
        paired.value?.let {
            tab = 0
            settingsKey++
            snack.showSnackbar("Gekoppeld met $it")
            paired.value = null
        }
    }
    LaunchedEffect(prefs.configured, settingsKey) {
        update = runCatching { Update.check(ctx) }.getOrNull()
    }
    Scaffold(
        snackbarHost = { SnackbarHost(snack) },
        bottomBar = {
            NavigationBar {
                NavigationBarItem(tab == 0, { tab = 0 }, { Icon(Icons.Filled.Edit, null) }, label = { Text("Dag") })
                NavigationBarItem(tab == 1, { tab = 1 }, { Icon(Icons.Filled.List, null) }, label = { Text("Week") })
                NavigationBarItem(tab == 2, { tab = 2 }, { Icon(Icons.Filled.DateRange, null) }, label = { Text("Maand") })
                NavigationBarItem(tab == 3, { tab = 3 }, { Icon(Icons.Filled.Settings, null) }, label = { Text("Instellingen") })
            }
        },
    ) { pad ->
        Column(
            Modifier.padding(pad).fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            update?.let { (_, name) ->
                Card(Modifier.fillMaxWidth()) {
                    Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text("Nieuwe versie $name beschikbaar", Modifier.weight(1f))
                        Button({
                            scope.launch {
                                try { Update.downloadAndInstall(ctx) } catch (e: Exception) {
                                    snack.showSnackbar("Update mislukt: ${e.message ?: "geen verbinding"}")
                                }
                            }
                        }) { Text("Installeren") }
                    }
                }
            }
            when (tab) {
                0 -> DayScreen(selected, { selected = it }, snack)
                1 -> WeekScreen(selected) { selected = it; tab = 0 }
                2 -> MonthScreen(snack)
                else -> key(settingsKey) { SettingsScreen(snack) }
            }
        }
    }
}

// ------------------------------------------------------------------ Dag
@Composable
fun DayScreen(date: LocalDate, onDate: (LocalDate) -> Unit, snack: SnackbarHostState) {
    val ctx = LocalContext.current
    val store = remember { DayStore(ctx) }
    val scope = rememberCoroutineScope()
    var day by remember(date) { mutableStateOf(store.get(date)) }
    var hoursText by remember(date) { mutableStateOf(fmtHours(day.hours)) }
    var note by remember(date) { mutableStateOf(day.note ?: "") }
    // Zondag standaard 2x als er nog niets is ingevuld
    LaunchedEffect(date) {
        if (day.isEmpty && date.dayOfWeek == DayOfWeek.SUNDAY) day = day.copy(factor = 2.0)
    }

    Row(verticalAlignment = Alignment.CenterVertically) {
        TextButton({ onDate(date.minusDays(1)) }) { Text("‹", fontSize = 26.sp) }
        Text(
            date.format(DAY_FMT).replaceFirstChar { it.uppercase() },
            style = MaterialTheme.typography.titleLarge,
            modifier = Modifier.weight(1f).clickable {
                DatePickerDialog(ctx, { _, y, m, d -> onDate(LocalDate.of(y, m + 1, d)) },
                    date.year, date.monthValue - 1, date.dayOfMonth).show()
            },
            textAlign = TextAlign.Center,
        )
        TextButton({ onDate(date.plusDays(1)) }) { Text("›", fontSize = 26.sp) }
    }
    if (date != LocalDate.now()) {
        TextButton({ onDate(LocalDate.now()) }, Modifier.fillMaxWidth()) { Text("Naar vandaag") }
    }

    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Uren", style = MaterialTheme.typography.labelLarge)
            Row(verticalAlignment = Alignment.CenterVertically) {
                FilledTonalButton({ hoursText = fmtHours(((parseHours(hoursText) ?: 0.0) - 0.25).coerceAtLeast(0.0)) }) { Text("−", fontSize = 22.sp) }
                OutlinedTextField(
                    hoursText, { hoursText = it },
                    Modifier.weight(1f).padding(horizontal = 8.dp),
                    singleLine = true,
                    textStyle = MaterialTheme.typography.headlineMedium.copy(textAlign = TextAlign.Center),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                )
                FilledTonalButton({ hoursText = fmtHours(((parseHours(hoursText) ?: 0.0) + 0.25).coerceAtMost(24.0)) }) { Text("+", fontSize = 22.sp) }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                listOf(8.0, 9.0, 10.0, 10.5, 11.0).forEach { h ->
                    FilterChip(parseHours(hoursText) == h, { hoursText = fmtHours(h) }, { Text(fmtHours(h)) })
                }
            }
            HorizontalDivider()
            Text("Telt mee als (zon-/feestdag)", style = MaterialTheme.typography.labelLarge)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(1.0 to "1×", 1.5 to "1,5×", 2.0 to "2×").forEach { (f, l) ->
                    FilterChip(day.factor == f, { day = day.copy(factor = f) }, { Text(l) })
                }
            }
            HorizontalDivider()
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Storingsdienst", Modifier.weight(1f))
                Switch(day.storing, { day = day.copy(storing = it) })
            }
            Text("Vakantie", style = MaterialTheme.typography.labelLarge)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(0.0 to "Geen", 0.5 to "Halve dag", 1.0 to "Hele dag").forEach { (v, l) ->
                    FilterChip(day.vakantie == v, { day = day.copy(vakantie = v) }, { Text(l) })
                }
            }
            OutlinedTextField(note, { note = it }, Modifier.fillMaxWidth(), label = { Text("Notitie") })
        }
    }
    Button(
        onClick = {
            val h = parseHours(hoursText)
            if (hoursText.isNotBlank() && (h == null || h < 0 || h > 24)) {
                scope.launch { snack.showSnackbar("Ongeldig aantal uren") }
                return@Button
            }
            val d = day.copy(hours = h, note = note.ifBlank { null })
            store.edit(d)
            day = store.get(date)
            Sync.enqueue(ctx)
            scope.launch { snack.showSnackbar("Opgeslagen") }
        },
        modifier = Modifier.fillMaxWidth().height(52.dp),
    ) { Text("Opslaan", fontSize = 17.sp) }
    if (day.dirty) Text("Nog niet gesynchroniseerd met de server", color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
}

// ------------------------------------------------------------------ Week
@Composable
fun WeekScreen(anchor: LocalDate, onOpenDay: (LocalDate) -> Unit) {
    val ctx = LocalContext.current
    val store = remember { DayStore(ctx) }
    val prefs = remember { Prefs(ctx) }
    var monday by remember { mutableStateOf(anchor.with(DayOfWeek.MONDAY)) }
    var refresh by remember { mutableIntStateOf(0) }
    val scope = rememberCoroutineScope()
    val days = remember(monday, refresh) { store.range(monday, monday.plusDays(6)) }
    val total = days.sumOf { it.weighted }
    val worked = days.sumOf { it.hours ?: 0.0 }
    val over = (total - prefs.contractHours).coerceAtLeast(0.0)

    Row(verticalAlignment = Alignment.CenterVertically) {
        TextButton({ monday = monday.minusWeeks(1) }) { Text("‹", fontSize = 26.sp) }
        Text("Week ${monday.get(IsoFields.WEEK_OF_WEEK_BASED_YEAR)}, ${monday.get(IsoFields.WEEK_BASED_YEAR)}",
            style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f), textAlign = TextAlign.Center)
        TextButton({ monday = monday.plusWeeks(1) }) { Text("›", fontSize = 26.sp) }
    }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(vertical = 8.dp)) {
            days.forEach { d ->
                Row(
                    Modifier.fillMaxWidth().clickable { onOpenDay(d.date) }.padding(horizontal = 16.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(d.date.dayOfWeek.getDisplayName(TextStyle.SHORT, NL) + " " + d.date.dayOfMonth + "-" + d.date.monthValue,
                        Modifier.width(90.dp), fontWeight = if (d.date == LocalDate.now()) FontWeight.Bold else FontWeight.Normal)
                    Text(buildString {
                        if (d.storing) append("S ")
                        if (d.vakantie > 0) append(if (d.vakantie == 1.0) "V " else "V½ ")
                        if (d.factor != 1.0) append(if (d.factor == 2.0) "2× " else "1,5× ")
                        if (d.dirty) append("•")
                    }, Modifier.weight(1f), color = MaterialTheme.colorScheme.tertiary)
                    Text(fmtHours(d.hours), style = MaterialTheme.typography.titleMedium)
                }
            }
            HorizontalDivider()
            Row(Modifier.padding(horizontal = 16.dp, vertical = 10.dp)) {
                Text("Totaal", Modifier.weight(1f), fontWeight = FontWeight.Bold)
                Text(fmtHours(total), fontWeight = FontWeight.Bold)
            }
            if (worked != total) Text("Gewerkt ${fmtHours(worked)} u (zon-/feestdagen tellen dubbel)",
                Modifier.padding(horizontal = 16.dp), style = MaterialTheme.typography.bodySmall)
            Row(Modifier.padding(horizontal = 16.dp, vertical = 6.dp)) {
                Text("Overuren (boven ${fmtHours(prefs.contractHours)})", Modifier.weight(1f))
                Text(fmtHours(over))
            }
        }
    }
    OutlinedButton({
        scope.launch { runCatching { Sync.run(ctx) }; refresh++ }
    }, Modifier.fillMaxWidth()) { Text("Vernieuwen van server") }
    Text("S = storing, V = vakantie, • = nog niet verstuurd. Tik op een dag om te wijzigen.",
        style = MaterialTheme.typography.bodySmall)
}

// ------------------------------------------------------------------ Maand
@Composable
fun MonthScreen(snack: SnackbarHostState) {
    val ctx = LocalContext.current
    val prefs = remember { Prefs(ctx) }
    val api = remember { Api(prefs) }
    val scope = rememberCoroutineScope()
    var ym by remember { mutableStateOf(YearMonth.now()) }
    var info by remember(ym) { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }

    LaunchedEffect(ym) {
        info = try {
            val m = api.month(ym.year, ym.monthValue)
            buildString {
                appendLine("Uren: ${fmtHours(m.optDouble("uren"))}")
                appendLine("Overuren: ${fmtHours(m.optDouble("overuren"))}")
                appendLine("€ overuren (netto): € %.2f".format(m.optDouble("overuren_euro")))
                if (m.optInt("storing_dagen") > 0) appendLine("Storingsdienst: ${m.optInt("storing_dagen")} dagen, € %.2f".format(m.optDouble("storing_euro")))
                append("Totaal netto: € %.2f".format(m.optDouble("totaal_netto")))
            }.replace('.', ',')
        } catch (e: Exception) {
            "Niet beschikbaar: ${e.message ?: "geen verbinding"}"
        }
    }

    Row(verticalAlignment = Alignment.CenterVertically) {
        TextButton({ ym = ym.minusMonths(1) }) { Text("‹", fontSize = 26.sp) }
        Text(ym.month.getDisplayName(TextStyle.FULL, NL).replaceFirstChar { it.uppercase() } + " " + ym.year,
            style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f), textAlign = TextAlign.Center)
        TextButton({ ym = ym.plusMonths(1) }) { Text("›", fontSize = 26.sp) }
    }
    Card(Modifier.fillMaxWidth()) {
        Text(info ?: "Laden…", Modifier.padding(16.dp), style = MaterialTheme.typography.bodyLarge)
    }

    suspend fun pdf(): File? = try {
        Sync.run(ctx)
        api.downloadPdf(ym.year, ym.monthValue, File(ctx.cacheDir, "pdf/uren-${ym}.pdf"))
    } catch (e: Exception) {
        snack.showSnackbar("PDF ophalen mislukt: ${e.message ?: "geen verbinding"}"); null
    }

    Button({
        busy = true
        scope.launch { pdf()?.let { printPdf(ctx, it, "Uren $ym") }; busy = false }
    }, Modifier.fillMaxWidth().height(52.dp), enabled = !busy) { Text("🖨  Maandoverzicht printen") }
    OutlinedButton({
        busy = true
        scope.launch {
            pdf()?.let {
                val uri = FileProvider.getUriForFile(ctx, ctx.packageName + ".files", it)
                val send = Intent(Intent.ACTION_SEND).setType("application/pdf")
                    .putExtra(Intent.EXTRA_STREAM, uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                ctx.startActivity(Intent.createChooser(send, "PDF delen"))
            }
            busy = false
        }
    }, Modifier.fillMaxWidth(), enabled = !busy) { Text("PDF delen / opslaan") }
    Text("Het overzicht toont hele weken (ma–zo) die bij deze maand horen.", style = MaterialTheme.typography.bodySmall)
}

// ------------------------------------------------------------------ Instellingen
@Composable
fun SettingsScreen(snack: SnackbarHostState) {
    val ctx = LocalContext.current
    val prefs = remember { Prefs(ctx) }
    val scope = rememberCoroutineScope()
    var url by remember { mutableStateOf(prefs.serverUrl) }
    var token by remember { mutableStateOf(prefs.token) }
    var remOn by remember { mutableStateOf(prefs.reminderOn) }
    var remH by remember { mutableIntStateOf(prefs.reminderHour) }
    var remM by remember { mutableIntStateOf(prefs.reminderMinute) }

    Text("Server", style = MaterialTheme.typography.titleLarge)
    if (!prefs.configured) Card(Modifier.fillMaxWidth()) {
        Text("Makkelijkst: open de web-app → Instellingen → Telefoon koppelen, en tik op \"Open in de Uren-app\" " +
            "(of scan de QR-code). Dan wordt alles hieronder vanzelf ingevuld.", Modifier.padding(16.dp))
    }
    OutlinedTextField(url, { url = it }, Modifier.fillMaxWidth(), label = { Text("Server-URL, bv. https://uren.mijndomein.nl") }, singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri))
    OutlinedTextField(token, { token = it }, Modifier.fillMaxWidth(), label = { Text("Token (web-app → Instellingen)") }, singleLine = true)
    if (url.startsWith("http://")) Text("Let op: zonder https wordt je token onversleuteld verstuurd. Gebruik http alleen thuis.",
        color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
    Button({
        prefs.serverUrl = url; prefs.token = token
        scope.launch {
            val msg = try {
                if (Api(prefs).ping()) { Sync.run(ctx); "Verbonden en gesynchroniseerd" } else "Onverwacht antwoord"
            } catch (e: Exception) { "Mislukt: ${e.message ?: "geen verbinding"}" }
            snack.showSnackbar(msg)
        }
    }, Modifier.fillMaxWidth()) { Text("Opslaan en testen") }
    Text(
        if (prefs.lastSync.isNotBlank()) "Laatst gesynchroniseerd: ${prefs.lastSync.replace('T', ' ')}" else "Nog niet gesynchroniseerd",
        style = MaterialTheme.typography.bodySmall,
    )
    if (prefs.lastSyncError.isNotBlank()) Text(prefs.lastSyncError, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)

    Spacer(Modifier.height(8.dp))
    Text("Herinnering", style = MaterialTheme.typography.titleLarge)
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text("Dagelijks ma t/m za (niet op zondag)", Modifier.weight(1f))
        Switch(remOn, { remOn = it; prefs.reminderOn = it; Reminder.schedule(ctx) })
    }
    OutlinedButton({
        TimePickerDialog(ctx, { _, h, m ->
            remH = h; remM = m; prefs.reminderHour = h; prefs.reminderMinute = m; Reminder.schedule(ctx)
        }, remH, remM, true).show()
    }, enabled = remOn) { Text("Tijd: %02d:%02d".format(remH, remM)) }
    Text("Je krijgt geen melding als je die dag al uren of vakantie hebt ingevuld.", style = MaterialTheme.typography.bodySmall)
    OutlinedButton({ Reminder.notify(ctx) }) { Text("Test melding") }
    Text("App-versie ${BuildConfig.VERSION_NAME}", style = MaterialTheme.typography.bodySmall)
}
