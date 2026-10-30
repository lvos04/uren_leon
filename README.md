# Uren & salaris

Vervangt `salaris_bijhouden_Leon.xlsx`. Drie onderdelen:

| Onderdeel | Wat | Map |
|---|---|---|
| **Server** | Web-app op TrueNAS: uren, overuren, maandoverzicht, vakantiedagen, bruto-netto, printen, Excel-export | `server/` |
| **Android-app** | Elke dag uren invoeren, herinnering om 20:00 (ma t/m za), maandoverzicht printen | `android/` |
| **Backup** | Elke nacht database + Excel-bestand naar OneDrive (via rclone in de container) | `server/app/backup.py` |

## Rekenregels (zoals in het Excel)

- Een week loopt van **maandag t/m zondag**. Overuren = weektotaal − contracturen (40).
- **Zon-/feestdag 1,5× of 2×**: de uren van die dag tellen 1,5 of 2 keer mee in het weektotaal
  (8 uur op 2× = 16 uur). Zo tellen ze ook voor de overuren. Op zondag staat de app standaard op 2×.
- Een week hoort bij de maand waarin de **donderdag** valt. Per week kun je dit handmatig aanpassen
  (week-scherm → "Meer"). Bij de import zijn de maanden overgenomen zoals ze in het Excel stonden.
- **Overuren zijn netto**: overuren × tarief (schaal 1 of 2, per maand te kiezen). Er gaat geen belasting af.
- Storingsdienst: aantal dagen × bedrag per dag (standaard € 10).
- Totaal netto per maand = nettoloon + overuren in euro + storingsdienst.
- Vakantiedagen: totaal per jaar (21) − gebruikt = over; uit te betalen = over × tarief × 8.
- **Bruto-netto calculator**: schatting voor het vaste salaris met de tarieven van 2024, 2025 en 2026
  (schijven, algemene heffingskorting, arbeidskorting; bron: Belastingdienst). Nieuwe jaren toevoegen in
  `server/app/tax_rates.json`.

## 1. Server op TrueNAS installeren

1. Maak een dataset, bijvoorbeeld `tank/apps/uren` (pad `/mnt/tank/apps/uren`).
2. De Docker-image wordt door GitHub Actions gebouwd: `ghcr.io/lvos04/uren_leon:latest`.
   Zet het package eenmalig op *public* (GitHub → je profiel → Packages → uren_leon → Package settings →
   Change visibility), of voeg in TrueNAS je GitHub-inlog toe als registry. Het image bevat geen gegevens.
3. TrueNAS SCALE: **Apps → Discover Apps → ⋮ → Install via YAML**. Plak `server/docker-compose.yml`
   en pas aan:
   - `APP_PASSWORD`: het wachtwoord voor de web-app.
   - het pad bij `volumes` naar je dataset.
4. Open `http://<truenas-ip>:8085` en log in.
5. **Oude gegevens importeren**: Instellingen → *Importeer oud Excel-bestand* → kies het xlsx-bestand.
   Alle jaren (2023–2026) worden overgenomen: uren, maandsalarissen, schalen, storings- en vakantiedagen,
   uitbetaalde overuren.

### Bereikbaar via internet (reverse proxy)

Zet een reverse proxy met https voor poort 8085, bijvoorbeeld Nginx Proxy Manager (TrueNAS-app),
Caddy of een Cloudflare Tunnel, met een eigen (sub)domein zoals `https://uren.jouwdomein.nl`.

- Laat `SESSION_HTTPS_ONLY: "1"` staan zodat het inlogcookie alleen over https gaat.
- Gebruik een sterk `APP_PASSWORD`. De Android-app gebruikt een apart token dat je kunt intrekken.

## 2. Backup naar OneDrive

De container maakt elke nacht om 03:00 (`BACKUP_TIME`) in `/data/backups` een kopie van de database en een
Excel-export. Bestanden ouder dan 30 dagen worden lokaal opgeruimd. Daarna kopieert rclone de map naar OneDrive.

OneDrive koppelen (eenmalig, op je pc):

1. Installeer rclone (<https://rclone.org/downloads/>).
2. Voer `rclone config` uit → `n` (nieuwe remote) → naam **`onedrive`** → type **`onedrive`** →
   client_id en secret leeg laten → region *global* → inloggen in de browser → kies je OneDrive
   (*OneDrive Personal or Business*) → bevestigen.
3. Zoek het configbestand met `rclone config file` en kopieer het naar de dataset als
   `/mnt/tank/apps/uren/rclone/rclone.conf`.
4. In de web-app: Instellingen → *Nu backup maken*. Je ziet daar of het gelukt is. De bestanden staan
   in OneDrive in de map **UrenBackup** (aan te passen met `RCLONE_REMOTE`).

rclone ververst het OneDrive-token zelf en schrijft het terug in `rclone.conf`.

## 3. Android-app

1. Installeer `Uren-x.apk` op je telefoon (toestaan: *installeren uit onbekende bronnen*).
   Nieuwe versies: GitHub → Actions → *Android* → artifact `uren-apk`, of een release met tag `app-vX`.
2. Maak in de web-app een token: Instellingen → Android-app → *Nieuw token*.
3. In de app: Instellingen → server-URL (bijv. `https://uren.jouwdomein.nl`) en het token →
   *Opslaan en testen*.

Wat de app doet:

- **Dag**: uren invullen (± 0,25), 1× / 1,5× / 2×, storingsdienst, vakantie (halve/hele dag), notitie.
  Werkt ook offline; de app synchroniseert zodra er verbinding is.
- **Week**: overzicht met totaal (zon-/feestdagen meegeteld) en overuren.
- **Maand**: samenvatting en **maandoverzicht printen** (PDF met hele weken), of de PDF delen.
- **Herinnering** om 20:00 van maandag t/m zaterdag, niet op zondag. Geen melding als je die dag al
  hebt ingevuld. Tijd aan te passen in Instellingen.

Wijzig je dezelfde dag op de telefoon en in de web-app, dan wint de laatste wijziging.

### APK ondertekenen in GitHub Actions

Zodat updates over de bestaande app heen geïnstalleerd kunnen worden, moet elke versie met dezelfde sleutel
ondertekend zijn. Zet in GitHub → Settings → Secrets and variables → Actions deze secrets:

| Secret | Waarde |
|---|---|
| `UREN_KEYSTORE_B64` | base64 van `uren.jks` |
| `UREN_KEYSTORE_PASSWORD` | wachtwoord keystore |
| `UREN_KEY_ALIAS` | `uren` |
| `UREN_KEY_PASSWORD` | wachtwoord sleutel |

Zonder deze secrets bouwt de workflow wel een APK, maar die kan niet over een eerder geïnstalleerde versie heen.

## Printen

Web-app → Maand → *Print (PDF)*, of in het jaaroverzicht 🖨 per maand of *Print hele jaar*.
Elke maand staat op één A4 met per week een blok (ma t/m zo, ook als de week over de maandgrens loopt;
dagen buiten de maand zijn grijs), en onderaan de maandtotalen.

## Ontwikkelen

```bash
cd server
pip install -r requirements-dev.txt
APP_PASSWORD=test DATA_DIR=./data uvicorn app.main:app --reload --port 8080
pytest -q                                   # tests
UREN_XLSX=/pad/naar/salaris.xlsx pytest -q   # ook vergelijken met het oude Excel
```

```bash
cd android
./gradlew testDebugUnitTest assembleDebug
```

API (Bearer-token): `GET /api/v1/ping`, `GET /api/v1/days?start=&end=`, `PUT /api/v1/days/{datum}`,
`GET /api/v1/week/{datum}`, `GET /api/v1/month/{jaar}/{maand}`, `GET /api/v1/print/{jaar}/{maand}.pdf`.
