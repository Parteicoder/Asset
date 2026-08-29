# Wahldaten-Sammler

Sammler für deutsche Wahldaten. Lädt Bundestagswahl, Europawahl, die jeweils jüngste Landtags- und
Gemeinde-/Stadtratswahl aller sechzehn Länder sowie die Kreistagswahlen der 294 Landkreise und legt
sie als kompakte JSON-Dateien ab.

**Nicht Teil dieses Repos: Regionalatlas und Zensus 2022.** Dieses Repo liefert ausschließlich
Wahldaten. Regionalatlas und Zensus 2022 sind eine eigene, live abgefragte externe
Datenquelle - kein Sync-Job, kein JSON-Snapshot, nichts davon steckt in `sammeln.py` oder
`quellen.json`:

| Quelle | Endpunkt |
|---|---|
| Regionalatlas | `https://www.gis-idmz.nrw.de/arcgis/rest/services/stba/regionalatlas/MapServer/dynamicLayer/query` |
| Zensus 2022 (100-m-Raster) | `https://services2.arcgis.com/jUpNdisbWqRpMo35/arcgis/rest/services/Zensus2022_grid_final/FeatureServer/0/query` |

Beides öffentliche ArcGIS-REST-Dienste, live per Umkreisabfrage genutzt (kein Bulk-Download, keine
Anmeldung).

Eine ausführliche technische Einführung für Entwickler und KI-Assistenten steht in
[`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md).

## Installieren & aktualisieren

Installieren (klont nach `./Asset`, prüft git/python3, läuft Selbsttest):

```
irm https://raw.githubusercontent.com/Parteicoder/Asset/main/install.ps1 | iex
```
```
curl -fsSL https://raw.githubusercontent.com/Parteicoder/Asset/main/install.sh | bash
```

Aktualisieren (im geklonten Verzeichnis, `git pull --ff-only` + Selbsttest):

```
.\update.ps1
```
```
./update.sh
```

Daten sammeln (nach Installation/Update):

```
python3 scripts/sammeln.py --land NN
```

## Landkennzahlen

Die zweistellige Landkennzahl (erste zwei Ziffern des AGS, `--land NN`) steht in `quellen.json`,
den Dateinamen unter `daten/` und den CLI-Aufrufen - hier zum Nachschlagen:

| NN | Land |
|---|---|
| 01 | Schleswig-Holstein |
| 02 | Hamburg |
| 03 | Niedersachsen |
| 04 | Bremen |
| 05 | Nordrhein-Westfalen |
| 06 | Hessen |
| 07 | Rheinland-Pfalz |
| 08 | Baden-Württemberg |
| 09 | Bayern |
| 10 | Saarland |
| 11 | Berlin |
| 12 | Brandenburg |
| 13 | Mecklenburg-Vorpommern |
| 14 | Sachsen |
| 15 | Sachsen-Anhalt |
| 16 | Thüringen |

## Quellen

Alle Quellen inklusive URL, Lizenz und Auswertungsdatei stehen maschinenlesbar in
[`quellen.json`](quellen.json) - diese Tabellen sind daraus abgeleitet, für eine schnelle
Übersicht ohne die JSON öffnen zu müssen. Es gibt keine GENESIS-Anmeldung mehr, keine Secrets und
keine automatische Tabellensuche.

**Basis (alle 16 Länder, wo unten keine Ergänzung greift):**

| Wahl | Quelle | URL |
|---|---|---|
| Bundestagswahl 2025 | Bundeswahlleiterin, kerg2 | <https://www.bundeswahlleiterin.de/bundestagswahlen/2025/ergebnisse/opendata/btw25/csv/kerg2.csv> |
| Europawahl 2024 | Bundeswahlleiterin, kerg2 | <https://www.bundeswahlleiterin.de/europawahlen/2024/ergebnisse/opendata/ew24/csv/kerg2.csv> |
| Landtagswahlen | [GERDA](https://www.german-elections.com/election-data/), `state_harm_25.csv` | <https://github.com/awiedem/german_election_data/raw/refs/heads/main/data/state_elections/final/state_harm_25.csv> |
| Gemeinde-/Stadtratswahlen | GERDA, `municipal_harm_25.csv` | <https://github.com/awiedem/german_election_data/raw/refs/heads/main/data/municipal_elections/final/municipal_harm_25.csv> |
| Kreistagswahlen | GERDA, `county_elec_harm_21_cty.csv` | <https://github.com/awiedem/german_election_data/raw/refs/heads/main/data/county_elections/final/county_elec_harm_21_cty.csv> |

**Landtagswahl-Ergänzungen** (ersetzen GERDA für dieses Land, weil aktueller oder amtlich statt harmonisiert):

| Land | Jahr | Quelle | URL |
|---|---|---|---|
| Rheinland-Pfalz | 2026 | Landeswahlleiter Rheinland-Pfalz | <https://www.wahlen.rlp.de/fileadmin/wahlen.rlp.de/dokumente-wahlen/ltw/Ergebnisdateien/2026/LW_2026_Endergebnis_Stimmbezirksebene.xlsx> |
| Sachsen | 2024 | Landeswahlleiter des Freistaates Sachsen | <https://wahlen.sachsen.de/download/Landtag/statistik-sachsen_LW24_endgErgebniss.xlsx> |
| Sachsen-Anhalt | 2021 | Landeswahlleiterin Sachsen-Anhalt | <https://wahlergebnisse.sachsen-anhalt.de/wahlen/lt21/erg/csv/lt21dat2.csv> |
| Berlin | 2023 | Landeswahlleiterin Berlin | <https://www.wahlen-berlin.de/wahlen/BE2023/AFSPRAES/agh/DL/DL_BE_AGHBVV2023.xlsx> |
| Mecklenburg-Vorpommern | 2021 | Landeswahlleiterin Mecklenburg-Vorpommern (LAIV-MV) | <https://www.laiv-mv.de/static/LAIV/Wahlen/2-Landtagswahlen/2021/Ergebnisse/l_gemeinden.csv> |
| Saarland | 2022 | Landeswahlleiterin Saarland | <https://wahlergebnis.saarland.de/LTW/KERG_SAARLAND.csv> |
| Schleswig-Holstein | 2022 | Statistikamt Nord | <https://www.statistik-nord.de/fileadmin/Dokumente/Wahlen/Schleswig-Holstein/Landtagswahlen/2022/endg%C3%BCltig/down/e_Tab_79_LTW2022_SH.xlsx> |
| Hessen | 2023 | Hessisches Statistisches Landesamt (manuell geprüfter Snapshot, `quellen/hessen-landtagswahl-2023.json`) | <https://wahlen.hessen-ltw23.23degrees.eu/> |
| Thüringen | 2024 | Thüringer Landeswahlleiter (manuell geprüfter Snapshot, `quellen/thueringen-landtagswahl-2024.json`) | <https://wahlen.thueringen.de/NeuLesen.asp?seite=LWINFOG2024> |

**Gemeinde-/Stadtratswahl-Ergänzungen:**

| Land | Jahr | Quelle | URL |
|---|---|---|---|
| Rheinland-Pfalz | 2024 | Landeswahlleiter Rheinland-Pfalz (manuell geprüfter Snapshot, `quellen/rlp-kommunalwahlen-2024-gemeindeebene.json`) | <https://rlp-kw24.wahlen.23degrees.eu/> |
| Thüringen | 2024 | Thüringer Landeswahlleiter (manuell geprüfter Snapshot, `quellen/thueringen-gemeinderatswahl-2024.json`) | <https://wahlen.thueringen.de/NeuLesen.asp?seite=GWInfoG2024> |
| Mecklenburg-Vorpommern | 2024 | Landeswahlleiter Mecklenburg-Vorpommern (LAIV-MV) | <https://www.laiv-mv.de/static/LAIV/Wahlen/3-Kommunalwahlen/2024/Ergebnisse/k_gemeinden.csv> |
| Brandenburg | 2024 | Amt für Statistik Berlin-Brandenburg | <https://wahlergebnisse.brandenburg.de/12/300/20240609/gemeindevertretungswahl_land/DL/DL_BB_GVW2024.xlsx> |

**Kreistagswahl-Ergänzungen:**

| Land | Jahr | Quelle | URL |
|---|---|---|---|
| Rheinland-Pfalz | 2024 | Landeswahlleiter Rheinland-Pfalz (manuell geprüfter PDF-Snapshot, `quellen/rlp-kommunalwahlen-2024-kreisebene.json`) | <https://www.wahlen.rlp.de/fileadmin/wahlen.rlp.de/KW/KW_2024_Ergebisse_Kreisebene.pdf> |
| Mecklenburg-Vorpommern | 2024 | Landeswahlleiter Mecklenburg-Vorpommern (LAIV-MV) | <https://www.laiv-mv.de/static/LAIV/Wahlen/3-Kommunalwahlen/2024/Ergebnisse/k_wahlkreise.csv> |
| Bayern | 2026 | Bayerisches Landesamt für Statistik | <https://kommunalwahl2026.bayern.de/downloads/gremienwahl/Kommunalwahl_Gremien_Landkreise.xml> |

Die Rheinland-Pfalz-Kommunalwahl-Ergänzung für 2024 deckt inzwischen fast alle rund 2.300
Gemeinden ab (nicht mehr nur die 12 kreisfreien Städte wie beim früheren PDF-Snapshot, siehe
`LIZENZ-DATEN.md`) - nur die Kreistagswahl (24 Landkreise) kommt weiterhin aus einer PDF ohne
zuverlässig per Standardbibliothek auswertbare Tabellenstruktur.

Die Thüringen-Ergänzung für die Gemeinde-/Stadtratswahl 2024 ersetzt GERDAs Datensatz für das ganze
Land vollständig, statt ihn nur zu ergänzen: GERDAs `municipal_harm_25.csv` führte für Thüringen
zwar 600 Gemeinden, aber keine der fünf kreisfreien Städte (Erfurt, Gera, Jena, Suhl, Weimar) – die
amtliche Quelle deckt alle 605 Gebiete einheitlich ab (siehe `LIZENZ-DATEN.md`, Abschnitt
„Thüringen: Gemeinde- und Stadtratswahl 2024").

Die Thüringen-Ergänzung für die Landtagswahl 2024 ersetzt GERDAs Datensatz ebenfalls vollständig,
diesmal für einheitliche Quellenlage statt einer echten Lücke bei GERDA. **Mit bekannter
Einschränkung:** Die Briefwahl lässt sich aus der amtlichen Datei für viele Gemeinden nicht
zuverlässig zurückrechnen, wodurch Wahlbeteiligung und Parteianteile bei kleineren Gemeinden
spürbar von GERDAs korrekt harmonisiertem Stand abweichen können (Details und Zahlen in
`LIZENZ-DATEN.md`, Abschnitt „Thüringen 2024 (Landtag)").

## Warum GERDA

Die frühere Lösung las Landtagswahlen aus der Regionaldatenbank GENESIS. Das hatte zwei
grundsätzliche Probleme:

- Der Abruf verlangte persönliche Zugangsdaten.
- Bei gemeinsam ausgezählter Briefwahl fehlen in GENESIS auf Gemeindeebene Stimmen oder werden
  dem falschen Gebiet zugerechnet. Das betrifft vor allem ostdeutsche Länder und kann Ergebnisse
  deutlich verschieben.

GERDA liest die Rohdateien der Landeswahlleitungen und statistischen Landesämter, vereinheitlicht
die Parteinamen und teilt gemeinsam ausgewiesene Briefwahl nachvollziehbar zu. Der Sammler lädt
die jeweilige GERDA-Datei **einmal pro Lauf**, sucht darin für jedes Land automatisch das jüngste
Wahljahr und schreibt daraus kleine App-Dateien.

Verwendet wird `state_harm_25.csv`. Diese Fassung bildet Ergebnisse auf die Gemeindegrenzen von
2025 ab und enthält Gemeindename und achtstelligen AGS. Das passt zur App, die ebenfalls mit
aktuellen AGS arbeitet. Wer wissenschaftlich die Grenzen am jeweiligen Wahltag untersuchen will,
sollte stattdessen direkt GERDAs `state_unharm.csv` verwenden; für die aktuelle App-Karte wäre
diese Fassung nicht der richtige Join-Schlüssel.

Für Gemeinde- und Stadträte wird entsprechend `municipal_harm_25.csv` verwendet. GERDA führt dort
zehn größere Parteien einzeln; lokale Listen, gemeinsame Wahlvorschläge und Einzelbewerber stehen
zusammengefasst als `Sonstige`. Wo ausschließlich diese Sammelgruppe vorliegt, kennzeichnet die
JSON-Datei das ausdrücklich mit einem Hinweis.

Kreistagswahlen kommen aus `county_elec_harm_21_cty.csv`. Der Sammler trennt wiederkehrende Parteien,
Wählervereinigungen und Einzelbewerber und fasst alle verbleibenden lokalen Listen verlustfrei als
`Sonstige` zusammen. Namen und Gebietstypen stammen aus `county_council_seats.csv`; dadurch werden
die Räte kreisfreier Städte nicht fälschlich als Kreistage ausgegeben. Berlin, Bremen und Hamburg
haben keine Landkreise und deshalb keine `kreistag.json` in ihren Landesordnern.

## Ausführen

Lokal genügt:

```bash
python3 scripts/sammeln.py
```

Es gibt kein `pip install` und keine `requirements.txt`. CSV, JSON, Netzabruf und selbst die
amtliche XLSX-Datei werden nur mit der Python-Standardbibliothek verarbeitet.

Weitere Befehle:

```bash
python3 scripts/sammeln.py --nur-laender  # GERDA und Länder-Ergänzungen
python3 scripts/sammeln.py --nur-kommunal # Gemeinde-/Stadtrats- und Kreistagswahlen
python3 scripts/sammeln.py --nur-bund     # Bundestags- und Europawahl
python3 scripts/sammeln.py --land 14      # alle landesabhängigen Dateien für Sachsen
python3 scripts/sammeln.py --land 14 --nur-kommunal
python3 scripts/sammeln.py --land 7       # einstellige Schreibweise ist ebenfalls erlaubt
python3 scripts/selbsttest.py             # Parser ohne Netz prüfen
```

Auf GitHub: *Actions → Daten sammeln → Run workflow*. Der Workflow läuft zusätzlich am Ersten
jedes Monats. Er committet nur, wenn sich Daten wirklich geändert haben.

## Rheinland-Pfalz 2026

GERDA enthält für Rheinland-Pfalz derzeit noch die Wahl 2021. Deshalb ersetzt der Sammler dieses
eine Land mit dem amtlichen Endergebnis vom 22. März 2026.

Die offizielle CSV kann dafür nicht sicher verwendet werden: Lange Identifikationsschlüssel sind
dort teilweise in wissenschaftlicher Schreibweise auf zu wenige Stellen gerundet. Aus einem
solchen Wert lässt sich kein eindeutiger Gemeinde-AGS zurückgewinnen. Die parallel veröffentlichte
amtliche XLSX-Datei enthält dieselben Ergebnisse mit vollständigen Schlüsseln und wird daher direkt
gelesen.

58 kleine Gemeinden weisen laut Quelldatei kein getrenntes Ergebnis aus. Ihre Stimmen sind mit
einer anderen Gemeinde zusammengefasst. Für diese Flächen übernimmt der Sammler das amtlich
gemeinsam ausgewiesene Ergebnis und ergänzt zwei Felder:

```json
{
  "hinweis": "Gemeinsam ausgewiesenes Ergebnis mit Peterslahr",
  "zusammengelegt_mit": "07132089"
}
```

Damit bleiben alle 2.300 Gemeinden in der Datei, ohne ein getrenntes Ergebnis vorzutäuschen.

## Ausgabe

`daten/index.json` listet alle vorhandenen Dateien, Wahljahre, Gebietsanzahlen, Quellen und
Lizenzen auf. Jedes Land besitzt einen Ordner nach seiner zweistelligen amtlichen Kennzahl:

- `daten/bundestagswahl-2025.json`
- `daten/europawahl-2024.json`
- `daten/01/landtag.json` bis `daten/16/landtag.json`
- `daten/01/kommunal.json` bis `daten/16/kommunal.json`
- `daten/XX/kreistag.json` für die 13 Flächenländer mit Landkreisen

Die bisherigen Adressen `daten/land-XX.json`, `daten/kommunal-XX.json` und
`daten/kreistag-XX.json` bleiben als bytegleiche Kompatibilitätsdateien bestehen. Neue Verbraucher
sollen die Landesordner verwenden, beispielsweise `daten/14/kommunal.json` für Sachsen.

`gemeinderat/<land>/<AGS>.json` (Repository-Wurzel, **nicht** unter `daten/`) ist eine
Direktabruf-Datei je Gemeinde, für wer nicht die ganze Landesdatei laden will. Für Eilenburg
(`14730110`) lautet sie `gemeinderat/14/14730110.json`. Bewusst getrennt von `daten/` gehalten:
ein statischer Datei-Host mit Dateilimit würde bei einer Datei je der bundesweit ~11.000 Gemeinden
allein durch `gemeinderat/` gerissen (siehe
`GEMEINDERAT_ZIEL` in `scripts/sammeln.py`). `gemeinderat/index.json` beschreibt alle Länder;
zusätzlich enthält jeder Landesordner ein kleines `index.json` mit Wahljahr, Gemeindezahl und dem
Dateimuster `{ags}.json`. Die gebündelten `daten/XX/kommunal.json` bleiben für Auswertungen eines
ganzen Landes erhalten.

Beispiel:

```json
{
  "land": "14",
  "name": "Sachsen",
  "titel": "Landtagswahl Sachsen 2024",
  "jahr": 2024,
  "wahl_datum": "2024-09-01",
  "schluesselart": "ags",
  "quelle": "GERDA – German Election Database",
  "gebiete": {
    "14730110": {
      "name": "Eilenburg",
      "beteiligung": 70.8,
      "parteien": {
        "AfD": 35.1,
        "CDU": 33.2,
        "BSW": 12.3
      }
    }
  }
}
```

`schluesselart` verhindert, dass eine Zahl falsch gedeutet wird:

| Wert | Bedeutung |
|---|---|
| `ags` | achtstelliger Gemeindeschlüssel, bei der Europawahl auch fünfstelliger Kreisschlüssel |
| `kreis-ags` | fünfstelliger Kreisschlüssel; nur echte Landkreise, keine kreisfreien Städte |
| `btw-wahlkreis` | Nummer des Bundestagswahlkreises |

GERDA liefert Parteianteile als Brüche zwischen 0 und 1. Durch Harmonisierung und proportionale
Briefwahl-Zuteilung kann ihre Summe geringfügig von 1 abweichen. Der Sammler akzeptiert nur
plausible Summen von 0,95 bis 1,05 und normiert diese für die Anzeige auf 100 Prozent. Abgeleitete
GERDA-Spalten wie `far_right` werden ausdrücklich nicht als Parteien gelesen.

## Schutz gegen stille Fehler

`scripts/selbsttest.py` prüft unter anderem:

- Auswahl des jüngsten Wahljahrs pro Land,
- führende Nullen in AGS,
- Abgrenzung echter Parteien von GERDA-Kennzahlen,
- Gemeinde-/Stadtratswahlen auf 2025er AGS und ihre jüngsten Wahljahre,
- vollständige 294 Landkreise ohne kreisfreie Städte,
- direkt abrufbare und idempotent erzeugte Gemeinderatsdateien je AGS,
- Erhalt unbekannter lokaler Listen als `Sonstige`,
- vollständige RLP-Schlüssel und Zusammenlegungsziele,
- XLSX-Lesen ohne Fremdpaket,
- Gebietsebene und Zweitstimme im kerg2-Format,
- unveränderte Dateien ohne künstlich neues Laufdatum.

Beim echten RLP-Abruf kommen weitere harte Prüfungen hinzu: ungefähr 2.300 Gemeindezeilen,
eindeutige AGS und Parteistimmensummen, die exakt den gültigen Landesstimmen entsprechen. Ein
Formatbruch stoppt den Lauf, statt unbemerkt falsche Daten zu veröffentlichen.

## Lizenz

Code, Workflows, Konfiguration und Dokumentation stehen unter AGPL-3.0-or-later (`LICENSE`). Für
die erzeugten Daten gelten die Bedingungen der jeweiligen Quelle:

| Dateien | Lizenz / Hinweis |
|---|---|
| Bundestags- und Europawahl | Datenlizenz Deutschland – Namensnennung 2.0 |
| GERDA-Länderdateien | CC BY 4.0, mit GERDA-Zitation |
| GERDA-Gemeinde-/Stadtrats- und Kreistagsdateien | CC BY 4.0, mit GERDA-Zitation |
| Rheinland-Pfalz 2026 | amtliche Wahlergebnisse; Quellenhinweis und Nutzungsbedingungen der Quelle beachten |
| Rheinland-Pfalz 2024 (Kommunal-/Kreistagswahl) | amtliche Wahlergebnisse; Quellenhinweis und Nutzungsbedingungen der Quelle beachten |
| Thüringen 2024 (Gemeinde-/Stadtratswahl) | amtliche Wahlergebnisse; Quellenhinweis und Nutzungsbedingungen der Quelle beachten |
| Thüringen 2024 (Landtag) | amtliche Wahlergebnisse; Quellenhinweis und Nutzungsbedingungen der Quelle beachten; bekannte Briefwahl-Einschränkung, siehe `LIZENZ-DATEN.md` |
| Hessen 2023 (Landtag) | amtliche Wahlergebnisse; Quellenhinweis und Nutzungsbedingungen der Quelle beachten |

Jede JSON-Datei trägt `quelle`, `quellenvermerk`, `lizenz`, `lizenz_url` und `quellendatei` selbst.
Einzelheiten stehen in [`LIZENZ-DATEN.md`](LIZENZ-DATEN.md).
