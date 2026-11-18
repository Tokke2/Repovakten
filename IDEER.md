# Repovakten – 25 förslag som gör den bättre än konkurrenterna

Konkurrenterna (Winget, Scoop, Chocolatey, GitHub Desktop m.fl.) installerar
*pålitligt* men visar aldrig *vad som faktiskt händer med filerna*. Repovaktens
kärna – filjämförelse med SHA-256, adminspärr per repo-ID och backup före varje
ändring – är redan annorlunda. Förslagen nedan bygger vidare på just det.
Varje förslag anger **vad**, **varför det slår konkurrenterna** och en grov
**insats** (S = liten, M = medel, L = stor).

---

## Säkerhet & förtroende

### 1. Verifiera nedladdningen mot GitHubs digest
GitHubs API returnerar SHA-256 för varje release-tillgång. Jämför den
nedladdade filens hash mot API:ts värde *innan* uppackning – en korrupt eller
manipulerad nedladdning avvisas direkt.
**Varför:** Winget/Scoop kontrollerar hash mot sitt eget index, inte mot
källan. Repovakten verifierar mot GitHub själv – noll förtroende behövs för
tredjepartsindex. **Insats: S** (API-fältet finns redan i `ReleaseAsset`).

### 2. Proveniensmärkning (SLSA/attestations)
Visa om releasen byggdes av GitHub Actions med build-attestation, och varna
om den laddades upp manuellt. En liten ikon i katalogen räcker.
**Varför:** Ingen konsumenthanterare visar detta i dag. Det gör "var kom
den här binären ifrån?" till en en-sekundersfråga. **Insats: M**.

### 3. Permanent installationslogg (audit trail)
Varje installation, uppdatering, spärr och avspärrning loggas med tidpunkt,
version, filantal och backup-sökväg – sökbart i en egen vy.
**Varför:** När något går fel kan användaren svara på "vad hände i tisdags?"
utan att gräva i mappar. **Insats: S** (loggfil + enkel tabell).

### 4. Skadad-installation-detektor
Bakgrundskontroll som hash:ar installerade filer och flaggar saknade/ändrade
filer med förslaget "Reparera" (installera om samma version).
**Varför:** Konkurrenterna upptäcker aldrig att en app tyst korrumperats.
Repovakten kan, eftersom manifestet redan finns. **Insats: M**.

### 5. Spärrhistorik med orsak
Visa vem som spärrade vad, när och varför (orsaken finns redan i `BlockRule`).
**Varför:** Adminspärren blir granskningsbar – viktigt i familje- och
företagsmiljöer där flera personer delar datorn. **Insats: S**.

---

## Uppdateringar

### 6. Systemtray + notiser
Tray-ikon med antal väntande uppdateringar och valfria inbyggda notiser när
en ny stabil release dyker upp.
**Varför:** Användaren behöver aldrig öppna appen för att veta att något
hänt. **Insats: M**.

### 7. "Uppdatera allt"
En knapp som uppdaterar alla installerade appar med nya stabila releaser –
med samma filrapport och backup per app.
**Varför:** Det är den enskilt mest efterfrågade funktionen i alla
pakethanterare, men här med full transparens per app. **Insats: M**.

### 8. Pinnade versioner
Lås en app till en specifik version ("installera aldrig nyare än v1.2.0").
**Varför:** Skyddar mot en dålig release utan att behöva spärra hela appen.
**Insats: S**.

### 9. Beta-kanal per app
Valfri per-repo inställning att också räkna pre-releaser som uppdateringar.
**Varför:** Utvecklare och testare slipper hämta pre-releaser manuellt.
**Insats: S** (`select_latest_any` finns redan).

### 10. Återställ-knapp per version
Från uppdateringshistoriken: "Återställ till v1.2.0" – installerar om den
tidigare releasen från GitHub (inte bara från lokal backup).
**Varför:** "Uppdateringen pajade något" blir en 30-sekundersåtgärd i stället
för en supportärende. **Insats: M**.

---

## Installation & format

### 11. Fler paketformat
Utöver ZIP: `.tar.gz`, `.7z`, enskilda körbara filer samt – med tydlig
användarbekräftelse – MSI/EXE-installerare (Windows) och dmg/pkg (macOS).
**Varför:** Många projekt distribuerar bara så. Repovakten blir den enda
hanteraren som hanterar *alla* GitHub-utgåvor, inte bara de som råkar vara ZIP.
**Insats: L** (format för format).

### 12. Återställ från lokal backup
Backup-katalogen får en vy: välj en backup och återställ den direkt, även om
repot försvunnit från GitHub.
**Varför:** Backupen är värdelös om den inte går att använda. **Insats: M**.

### 13. Portabelt läge
Kör helt från en mapp (USB-minne): tillstånd, appar och backuppar på samma
ställe. Miljövariablerna `REPOVAKTEN_HOME`/`REPOVAKTEN_APPS` finns redan.
**Varför:** Fungerar på lånedatorer och i klassrum utan installation.
**Insats: S**.

### 14. Exportera/importera konfiguration
JSON-export av konton, spärrar och bevarade sökvägar – import på en annan
dator återställer allt.
**Varför:** Nya datorn = tio minuters klickande i dag. Med export: en fil.
**Insats: S**.

### 15. Kommandoradsläge (CLI)
`repovakten sync`, `repovakten install Tokke2/Appen`, `repovakten block …` –
samma kärna, inget GUI. Möjliggör skript och SSH-fjärradministration.
**Varför:** Konkurrenterna har CLI men inget av dem visar filrapporter.
**Insats: M** (kärnan är redan GUI-fri).

---

## Katalog & upptäckt

### 16. Sök och filter
Söktext plus filter: språk, status (klar/spärrad/saknar release), installerad
eller ej.
**Varför:** Med 20+ repon per konto blir listan ohanterlig utan filter.
**Insats: S**.

### 17. Favoriter och grupper
Stjärnmärk appar och gruppera dem ("Jobb", "Spel", "Verktyg").
**Varför:** Personlig katalog i stället för en platt lista. **Insats: S**.

### 18. Repo-detaljvy med README
Klicka en app för att se beskrivning, licens, senaste commit och README
renderad (markdown) innan du bestämmer dig.
**Varför:** Man installerar inte blint – man läser först. **Insats: M**.

### 19. Release notes i filrapporten
Visa GitHub-releasens anteckningar i godkännandedialogen, ovanför filistan.
**Varför:** "Vad ändrades i v1.3.0?" besvaras där beslutet fattas.
**Insats: S** (fältet finns i API-svaret).

### 20. Organisationer och privata repon
Bevaka hela GitHub-organisationer, inte bara användare. Privata repon via
token (se #21).
**Varför:** Företag och skolor har sina appar i organisationer.
**Insats: M**.

---

## Autentisering & API

### 21. Personlig access-token (PAT)
Valfri token med enbart läsrättigheter: högre API-kvot (5 000 anrop/timme)
och privata repon. Lagras i OS:ets nyckelring, aldrig i `state.json`.
**Varför:** Utan token tar synken slut på kvoten vid många konton.
**Insats: M**.

### 22. API-kvot i gränssnittet
Visa återstående GitHub-kvot och pausa synk elegant vid slut (med
återupptagningsbar tid).
**Varför:** Användaren ser *varför* synken väntar i stället för ett fel.
**Insats: S**.

---

## Användbarhet

### 23. Mörkt läge
Följ systemets tema automatiskt (Qt stöder detta inbyggt).
**Varför:** Förväntat av varje modern desktopapp. **Insats: S**.

### 24. Svenska + engelska
Språkval i inställningar, svenska som standard. All text är redan centraliserad
i `ui/status.py` och dialogerna.
**Varför:** Öppnar upp för internationella användare utan att tappa svenskan.
**Insats: M** (översättningsarbete, inte kod).

### 25. Genvägar till installerade appar
Skapa genvägar i Windows Startmeny, macOS Program-mapp och Linux
`.desktop`-filer – med val per app.
**Varför:** En installerad app som inte syns i menyn känns inte installerad.
Det är steget från "hanterare" till "ersätter appbutiken". **Insats: M**.

---

## Rekommenderad ordning

Först de billiga förtroendeförbättringarna (**1, 3, 5, 8, 19, 22**), sedan
det som märks varje dag (**6, 7, 16, 23, 25**), och sist de stora
format- och integrationslyften (**11, 18, 20, 21**). Varje steg är
oberoende och kan levereras för sig.
