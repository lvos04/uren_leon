# Uren & salaris

Vervangt `salaris_bijhouden_Leon.xlsx`:

- **Web-app op TrueNAS**: uren, overuren, maandoverzicht, vakantiedagen, bruto-netto, printen, Excel-export.
- **Android-app**: elke dag uren invoeren, herinnering om 20:00 (ma t/m za), maandoverzicht printen.
- **Backup**: elke nacht naar OneDrive.

Alles stel je in via de web-app. Geen wachtwoorden in bestanden, geen terminal, geen GitHub-secrets.

## Installeren (eenmalig)

### Stap 1 — Image openbaar maken (1 klik op GitHub)

De repo is privé, daarom staat de app-image ook op privé. TrueNAS moet hem kunnen downloaden:

GitHub → je profielfoto → **Your profile** → tab **Packages** → **uren_leon** → **Package settings** (rechts) →
onderaan **Change visibility** → **Public** → typ `uren_leon` ter bevestiging.

De image bevat alleen de programmacode, geen gegevens.

### Stap 2 — App toevoegen in TrueNAS

TrueNAS → **Apps** → **Discover Apps** → **Custom App**. Vul in:

| Veld | Waarde |
|---|---|
| Application Name | `uren` |
| Image → Repository | `ghcr.io/lvos04/uren_leon` |
| Image → Tag | `latest` |
| Timezone (bovenaan het formulier) | `Europe/Amsterdam` — **niet** ook als Environment Variable toevoegen |
| Network → Port Forwarding | Container Port `8080`, Host Port `8085` |
| Storage → Host Path | Mount Path `/data`, Host Path: een map op je pool, bv. `/mnt/tank/apps/uren` (maak hem aan met het mapje-icoon) |

Klik **Install**. (Liever YAML? Dan kan `server/docker-compose.yml` via ⋮ → *Install via YAML*.)

### Stap 3 — Web-app openen en instellen

1. Open **thuis** `http://<ip-van-truenas>:8085`.
2. **Kies je wachtwoord** (dit scherm werkt alleen vanaf je thuisnetwerk, zodat niemand anders het eerst kan doen).
3. **Instellingen → Import**: kies je oude Excel-bestand. Alle jaren 2023–2026 worden overgenomen.
4. **Instellingen → Backup & OneDrive → OneDrive koppelen**: volg de 3 stappen op het scherm
   (inloggen bij Microsoft, adres uit de adresbalk kopiëren, plakken).
5. **Instellingen → Account → Adres van de server**: het adres van je reverse proxy, bv. `https://uren.jouwdomein.nl`.
6. **Instellingen → Telefoon → Telefoon koppelen**: download de app, installeer hem, en tik op
   **Open in de Uren-app** (of scan de QR-code). De app is dan gekoppeld.

### Stap 4 — Reverse proxy

Laat je reverse proxy (bv. `uren.jouwdomein.nl`) doorsturen naar `http://<ip-van-truenas>:8085`, met https aan.

## Updates

- **Server**: TrueNAS → Apps → uren → **Update** (of *Pull image* + herstarten) wanneer er een nieuwe versie is.
- **Telefoon**: de app laat zelf "Nieuwe versie beschikbaar → Installeren" zien zodra de server een nieuwere app heeft.
  De eerste keer vraagt Android of de Uren-app updates mag installeren: toestaan.

## Backup en terugzetten

Elke nacht (tijd in te stellen) maakt de server een kopie van de database en een Excel-bestand. Die gaan naar
OneDrive in de map **UrenBackup**. Op de server blijven ze 30 dagen staan (aan te passen).
Onder *Backups op de server* kun je een backup downloaden of **terugzetten**. Bij terugzetten wordt eerst een extra
kopie van de huidige gegevens gemaakt, en je wachtwoord en gekoppelde telefoons blijven gewoon werken.

## Rekenregels (zoals in het Excel)

- Een week loopt van **maandag t/m zondag**. Overuren = weektotaal − contracturen (40).
- **Zon-/feestdag 1,5× of 2×**: de uren van die dag tellen 1,5 of 2 keer mee in het weektotaal
  (8 uur op 2× = 16 uur), dus ook voor de overuren. Op zondag staat de app standaard op 2×.
- Een week hoort bij de maand waarin de **donderdag** valt; per week aan te passen. Bij de import zijn de
  maanden overgenomen zoals ze in het Excel stonden.
- **Overuren zijn netto**: overuren × tarief (schaal 1 of 2, per maand te kiezen). Er gaat geen belasting af.
- Storingsdienst: aantal dagen × bedrag per dag (standaard € 10).
- Totaal netto per maand = nettoloon + overuren in euro + storingsdienst.
- Vakantiedagen: totaal per jaar (21) − gebruikt = over; uit te betalen = over × tarief × 8.
- **Bruto-netto**: schatting voor het vaste salaris met de tarieven van 2024–2026 (Belastingdienst).
  Nieuwe jaren: `server/app/tax_rates.json`.

## Printen

Web-app → Maand → *Print (PDF)*, in het jaaroverzicht 🖨 per maand of *Print hele jaar*, of in de app → Maand →
*Maandoverzicht printen*. Elke maand staat op één A4 met per week een blok (ma t/m zo; dagen buiten de maand grijs)
en onderaan de maandtotalen.

## Wachtwoord kwijt?

Voeg in TrueNAS bij de app de omgevingsvariabele `APP_PASSWORD` toe met een tijdelijk wachtwoord, log daarmee in,
kies onder Instellingen → Account een nieuw wachtwoord en haal de variabele weer weg.

## Voor ontwikkelaars

```bash
cd server && pip install -r requirements-dev.txt
DATA_DIR=./data uvicorn app.main:app --reload --port 8080
pytest -q                                   # tests
UREN_XLSX=/pad/naar/salaris.xlsx pytest -q   # ook vergelijken met het oude Excel

cd android && ./gradlew testDebugUnitTest assembleRelease
```

GitHub Actions (`.github/workflows/build.yml`) bouwt bij elke push de app (ondertekend met `android/signing/`)
en de server-image met de app erin, en zet die op `ghcr.io/lvos04/uren_leon:latest`.

API (Bearer-token): `GET /api/v1/ping`, `GET /api/v1/days?start=&end=`, `PUT /api/v1/days/{datum}`,
`GET /api/v1/week/{datum}`, `GET /api/v1/month/{jaar}/{maand}`, `GET /api/v1/print/{jaar}/{maand}.pdf`,
`GET /api/v1/app-version`, `GET /api/v1/app.apk`.
