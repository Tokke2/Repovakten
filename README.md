# Repovakten

**Installationshanterare för GitHub-appar** – en fristående skrivbordsapp
med svenskt gränssnitt för Windows, macOS och Linux. Den installerar appar
på den här datorn, inte på något webbhotell.

> **Status: v0.0.1 – första releasen.** Katalog, synk, spärrar, releaseurval,
> SHA-256-filjämförelse, installation med backup och svenskt Qt-gränssnitt
> (PySide6) är implementerade och testade (201 tester). Releasen uppdateras
> automatiskt vid ny kod på branchen – versionsnumret höjs först när
> användaren säger till. Se [IDEER.md](IDEER.md) för 25 förslag som gör
> Repovakten bättre än konkurrenterna.

Namnet **Repovakten** valdes före Applotsen, Releasekollen, Paketvakten och
Reponavet eftersom bevakningen av konton och adminspärrarna är appens kärna.

## Krav

- Python **3.11+** (målet är senaste Python, 3.14-serien; koden undviker
  versionsspecifika finesser så den kör överallt från 3.11 och uppåt)
- För GUI: `pip install repovakten[gui]` (PySide6 + segno)

## Starta appen

```bash
python -m repovakten                      # GUI – samma på Windows, macOS och Linux
python -m repovakten --autostart          # minimerat (läget som autostart använder)
python -m repovakten --enable-autostart   # starta med datorn
python -m repovakten --disable-autostart  # stäng av autostart
python -m repovakten --version
```

Autostart fungerar på **Windows** (registret `HKCU\...\Run`), **macOS**
(LaunchAgent i `~/Library/LaunchAgents`) och **Linux** (XDG-autostart) –
samma sak via kryssrutan **Arkiv → Starta med datorn** i appen. Från den
portabla ZIP:en startar `Repovakten.bat` / `./repovakten.sh` som förut
(och `--autostart` skickas vidare).

## Utveckling

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"   # eller: uv pip install -e ".[dev]"
.venv/bin/python -m pytest          # 201 tester
```

## Så fungerar det

1. **Bevaka dina GitHub-konton** (`repovakten.sync`). Ett eller flera konton
   (t.ex. `Tokke2`) läggs till en gång. Vid start, var **15:e minut** medan
   appen är öppen (`SYNC_INTERVAL_SECONDS = 900`) och vid "Synka nu" hämtas
   nya och ändrade *publika* repon. Ett nytt repo i katalogen betyder
   **aldrig** att något installeras. Försvunna repon markeras som
   försvunna men raderas aldrig – varken installationsregister eller spärrar.
2. **Katalogen visar vad det är för app** (`repovakten.catalog`): projektnamn,
   huvudspråk enligt GitHub (PHP, Python, C++, C# …), installerad version,
   senaste stabila release och om installation är tillåten. Repon utan
   releaser visas också.
3. **Adminspärr per repo** (`repovakten.blocking`). "Spärra installation" /
   "Tillåt igen". En spärrad app får visas men får varken installeras eller
   uppdateras. Spärren nycklas på **GitHubs repo-ID** och överlever namnbyte
   och synk. Den raderar aldrig en redan installerad kopia. Installations-
   och uppdateringsflödet anropar `assert_install_allowed()` precis före
   varje skrivning, inte bara när dialogen öppnas.
4. **Rätt release** (`repovakten.releases`): senaste *stabila* releasen
   enligt GitHubs egna draft-/prerelease-flaggor. v1 stödjer **uppladdade,
   portabla ZIP-paket**; GitHubs autogenererade "Source code (zip)"
   presenteras aldrig som en färdig app. Finns flera paket rangordnas de för
   din dator (OS + arkitektur + "portable"), men du väljer alltid själv.
5. **Filjämförelse med SHA-256** (`repovakten.hashing`, `repovakten.compare`):
   varje programfil i releasen jämförs med den lokala kopian – också när båda
   heter t.ex. `v1.2.0`. Rapporten visar *vilken fil* som skiljer sig, plus
   **nya**, **saknade** (saknas på disk enligt installationsmanifestet) och
   **utgående** filer. `storage/` (användardata) bevaras alltid och jämförs
   aldrig.
6. **Fråga innan något ändras**: filrapporten
   kan stängas utan att installera. Vid godkännande kontrolleras spärren
   igen och den tidigare kopian sparas som backup. Nedladdade program körs
   **aldrig** automatiskt.
7. **Donationsdialog** (`repovakten.donation`, menyn Hjälp → Stöd projektet):
   valfritt belopp med Swish-QR enligt Swish officiella C-format, plus
   knappar för PayPal och Ko-fi. Swish-numret visas aldrig i klartext –
   bara QR-koden innehåller det. Gåvan är helt frivillig och ändrar
   ingenting i appen.
8. **Självuppdatering + appkontroll** (`repovakten.selfupdate`, menyn Hjälp →
   Sök uppdateringar): Repovakten kollar sin egen rullande release och jämför
   paketets filer mot den körande koden med SHA-256 – också när
   versionsnumret är samma. Filrapporten visas före ändringen och ingenting
   görs utan godkännande; backup och rullning tillbaka ingår. Endast
   `repovakten/`-paketet uppdateras. Kontrollen kollar **även de
   installerade apparna** efter nyare stabila releaser och erbjuder att
   uppdatera dem en och en – samma säkra flöde med filrapport och backup.
   Söks automatiskt efter synken vid appstart.

## Säkerhet och garantier

- Spärrar och installationer nycklas på repo-ID och följer med vid namnbyte.
- `storage/` (och andra bevarade sökvägar) skrivs aldrig över och tas aldrig
  bort – varken vid jämförelse eller vid installation.
- ZIP-paket valideras: absoluta sökvägar, enhetsbokstäver och `..` avvisas
  (zip-slip), dubbletter efter normalisering avvisas, tak på antal filer och
  uppackad storlek.
- Tokens läses endast från miljövariablerna `REPOVAKTEN_GITHUB_TOKEN` eller
  `GITHUB_TOKEN` – aldrig från appen sparade filer. Utan token fungerar allt,
  men med lägre API-kvot.
- Tillståndsfilen `state.json` skrivs atomiskt (tempfil + `os.replace`) och
  den tidigare versionen sparas som `state.json.bak` om filen skulle skadas.
- Synken läser bara metadata och rör aldrig installationsmappar.
- Release-ZIP:en innehåller **endast aktiva filer** – paketets `.py`-moduler
  och startskripten. Ingen dokumentation, metadata, cachar eller loggar.

## Loggar och felkoder

Appen loggar i en egen mapp i appmappen: `<appmapp>/logs/repovakten.log`
(roteras, 4 × 1 MB). Varje fel får en **felkod** som både skrivs till
loggen och visas i dialogen – koden kan citeras vid en felrapport:

| Kod | Vad |
|---|---|
| `SYNK-001` | Synk mot GitHub misslyckades |
| `INSTALL-001` | Paketet kunde inte hämtas eller jämföras |
| `INSTALL-002` | Installationen misslyckades (återställd) |
| `INSTALL-003` | Appen är spärrad av admin |
| `UPPDATERA-001` | Kunde inte söka uppdatering |
| `UPPDATERA-002` | Självuppdateringen misslyckades |
| `AUTOSTART-001` | Autostart kunde inte ställas in |
| `LAGRING-001` | `state.json` kunde inte läsas eller skrivas |
| `DONATION-001` | Donationsdialogen kunde inte visas |
| `QT-001` / `QT-002` | Varning / kritiskt fel från Qt-ramverket |
| `ALLMANT-001` | Övriga fel |

Varje session börjar med versions- och miljöinfo. Qt:s egna varningar och
fel fångas automatiskt och hamnar i samma logg med sina koder. Om
appmappen är skrivskyddad används `~/.repovakten/logs` i stället.

## Arkitektur

```
src/repovakten/
  models.py        Datamodeller (repo, release, asset, spärr, installationsregister)
  versions.py      Tolkning/jämförelse av versionstaggar (v1.2.0, pre-releaser)
  github.py        Minimal REST-klient (urllib), bytbar transport, paginering
  sync.py          Bevakning: start / var 15:e minut / "Synka nu"
  store.py         Beständigt tillstånd: state.json, atomisk skrivning + .bak
  blocking.py      Adminspärrar (blockera / tillåt igen / assert_install_allowed)
  releases.py      Senaste stabila release, ZIP-filtrering, paketrangordning
  hashing.py       SHA-256, trädläsning, säker ZIP-validering
  compare.py       Filrapport: ny / ändrad / saknad / utgående + svensk text
  catalog.py       Vymodell: status per repo (klar/spärrad/ingen release/…)
  platforminfo.py  OS- och arkitekturidentifiering
  installer.py     Installation: nedladdning (HTTPS), validering, backup,
                   uppackning, borttag av utgående filer, rollback vid fel
  errors.py        Felhierarki
  donation.py      Donationer: Swish-QR (C-format), PayPal, Ko-fi (Qt-fri)
  selfupdate.py    Självuppdatering: jämför och uppdaterar den körande koden
  applog.py        Loggning med felkoder i <appmapp>/logs/ (Qt-fri)
  autostart.py     Autostart vid inloggning: Windows-registret, macOS
                   LaunchAgent, Linux XDG (Qt-fri)
  __main__.py      Gemensam startpunkt: `python -m repovakten` (alla OS)
  gui.py           Startpunkt: `repovakten-gui` / `python -m repovakten.gui`
  ui/              Qt-gränssnitt (PySide6): huvudfönster, dialoger
                   (filrapport, paketval, donation), bakgrundsarbetare
                   (synk/nedladdning/installation), svenska statustexter
tests/             201 tester (fejkad GitHub-transport, inga nätverksanrop)
```

## Kända begränsningar och nästa steg

- **Paketering**: fristående fil per OS (t.ex. PyInstaller) för Windows,
  macOS och Linux. GUI:t kräver PySide6 (`pip install repovakten[gui]`)
  och körs med `repovakten-gui` eller från releasens portabla ZIP.
- **Paketformat**: endast uppladdade portabla ZIP-paket stöds i v1
  (inte `.tar.gz`, `.7z` eller installerare – se [IDEER.md](IDEER.md) #11).
- Prototyp fanns i arbetskopian av `Tokke2/lager` (`apphanterare/`,
  Tk/Python) men var inte tillgänglig här, så Repovakten byggdes på nytt
  från specifikationen – med Qt och senaste Python istället för Tk.

## Notis om GitHub-åtkomst

Utan token har API:et låg kvot. Sätt `REPOVAKTEN_GITHUB_TOKEN` till ett
fine-grained PAT med endast läsbehörighet för publika releaser om du synkar
många repos ofta.
