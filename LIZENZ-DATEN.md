# Lizenz und Herkunft der Dateien unter `daten/`

Die AGPL im Wurzelverzeichnis gilt für Code, Workflows, Konfiguration und Dokumentation. Sie gilt
nicht automatisch für die Wahldaten. Für jede erzeugte Datei gelten die Bedingungen ihrer Quelle.

## Bundestags- und Europawahl

Quelle: Die Bundeswahlleiterin, Wiesbaden.

Lizenz: Datenlizenz Deutschland – Namensnennung – Version 2.0 (`dl-de/by-2-0`):
<https://www.govdata.de/dl-de/by-2-0>

Verlangter Quellenvermerk:

> Datenquelle: Die Bundeswahlleiterin, Wiesbaden

## Wahlen aus GERDA

Quelle: GERDA – German Election Database. Verwendete Dateien:
<https://www.german-elections.com/election-data/>

- Landtagswahlen: `state_harm_25.csv`
- Gemeinde-/Stadtratswahlen: `municipal_harm_25.csv`
- Kreistagswahlen: `county_elec_harm_21_cty.csv`
- Namen und Typen der Kreise: `county_council_seats.csv`

Lizenz: Creative Commons Namensnennung 4.0 International (`CC BY 4.0`):
<https://creativecommons.org/licenses/by/4.0/>

Quellenvermerk:

> Datenquelle: GERDA – German Election Database (Heddesheimer, Hilbig, Sichart & Wiedemann,
> 2025); eigene Aufbereitung (jüngste Wahl je Land, Anteile auf 100 Prozent normiert)

Zitation:

> Heddesheimer, V.; Hilbig, H.; Sichart, F.; Wiedemann, A. (2025): GERDA: The German Election
> Database. Scientific Data 12, 618. <https://doi.org/10.1038/s41597-025-04811-5>

GERDA vereint amtliche Landesquellen, harmonisiert Gemeindegrenzen und teilt gemeinsam
ausgewiesene Briefwahl proportional zu. Der Sammler wählt daraus das jüngste Wahljahr je Land,
entfernt abgeleitete Analysefelder und normiert kleine Rundungsabweichungen auf 100 Prozent. Diese
Aufbereitung wird im Quellenvermerk genannt.

Bei Gemeinde-/Stadtratswahlen sind örtliche Listen, gemeinsame Wahlvorschläge und Einzelbewerber in
GERDA bereits als `other` zusammengefasst. Die Ausgabe nennt diese Gruppe `Sonstige`. Bei
Kreistagswahlen bleiben wiederkehrende Parteien, Wählervereinigungen und Einzelbewerber getrennt;
alle weiteren lokalen Listen werden ebenfalls als `Sonstige` zusammengefasst. Kreisfreie Städte
werden anhand von `county_council_seats.csv` ausgeschlossen, weil sie keinen Kreistag wählen.

## Rheinland-Pfalz 2026

Quelle: Landeswahlleiter Rheinland-Pfalz, Endergebnis der Landtagswahl vom 22. März 2026:
<https://www.wahlen.rlp.de/landtagswahl/ergebnisse>

Direkte Quelldatei: `LW_2026_Endergebnis_Stimmbezirksebene.xlsx` auf `wahlen.rlp.de`.

Die Ergebnisseite weist für diese Datei keine standardisierte offene Lizenz wie CC BY oder
`dl-de/by-2-0` aus. Deshalb behaupten die erzeugte Datei und dieses Repo keine solche Lizenz. Bei
einer Weiterverwendung sind die Nutzungsbedingungen der amtlichen Quelle zu beachten und der
folgende Vermerk beizubehalten:

> Datenquelle: Landeswahlleiter Rheinland-Pfalz, Endergebnis der Landtagswahl vom 22. März 2026;
> eigene Aufbereitung (Landesstimmenanteile; gemeinsam ausgewiesene Ergebnisse gekennzeichnet)

Die Aufbereitung berechnet Anteile aus den Landesstimmen. Bei 58 Gemeinden, für die die Quelle nur
ein gemeinsames Ergebnis mit einer anderen Gemeinde ausweist, wird genau dieses gemeinsame
Ergebnis verwendet und im Datensatz ausdrücklich gekennzeichnet.

## Sachsen 2024

Quelle: Landeswahlleiter des Freistaates Sachsen, endgültiges Ergebnis der Landtagswahl vom
1. September 2024 auf Gemeindeebene:
<https://wahlen.sachsen.de/landtagswahlen-2024-informationen-und-downloads.html>

Direkte Quelldatei: `statistik-sachsen_LW24_endgErgebniss.xlsx`, Tabellenblatt
`LW24_endgErgebnisse_GE&TG`, auf `wahlen.sachsen.de`.

Die Downloadseite weist für diese Datei keine standardisierte offene Lizenz wie CC BY oder
`dl-de/by-2-0` aus. Deshalb behaupten die erzeugte Datei und dieses Repo keine solche Lizenz. Bei
einer Weiterverwendung sind die Nutzungsbedingungen der amtlichen Quelle zu beachten und der
folgende Vermerk beizubehalten:

> Datenquelle: Landeswahlleiter des Freistaates Sachsen, endgültiges Ergebnis der Landtagswahl vom
> 1. September 2024 auf Gemeindeebene; eigene Aufbereitung (Listenstimmenanteile; Chemnitz,
> Dresden, Leipzig und Zwickau aus Teilgemeinden zusammengefasst)

Diese Ergänzung ersetzt GERDAs Sachsen-Ergebnis für die Landtagswahl, weil die amtliche Datei die
Gemeinden ohne GERDAs Harmonisierungsschritt direkt und mit exakten Stimmenzahlen ausweist. Vier
kreisfreie Städte (Chemnitz, Dresden, Leipzig, Zwickau) führt die Datei ausschließlich als mehrere
Teilgemeinde-Zeilen ohne eine zusammenfassende Gemeindezeile; der Sammler summiert deren
Listenstimmen zu einem Ergebnis je achtstelligem Gemeinde-AGS.

**Ungeprüft:** Ob die verlinkte Downloadseite eine andere Lizenz nennt als zum Zeitpunkt dieser
Ergänzung eingesehen, sollte vor einer Weiterverwendung erneut geprüft werden.

## Thüringen 2024 (Landtag)

Quelle: Thüringer Landeswahlleiter, endgültiges Ergebnis der Landtagswahl vom 1. September 2024:
<https://wahlen.thueringen.de/landtagswahlen/lw_wahlergebnisse.asp>

Direkte Quelldatei: `LWINFOG2024.xlsx` auf `wahlen.thueringen.de`
(`NeuLesen.asp?seite=LWINFOG2024`), Gemeindezeilen (Satzart „G").

**Bekannte Einschränkung, bewusst in Kauf genommen: Briefwahl nicht zuverlässig auf Gemeinden
zurückrechenbar.** Anders als bei der Kommunal-/Kreistagswahl (siehe unten) wird die Briefwahl bei
der Landtagswahl in Thüringen für viele Gemeinden wahlkreisweit statt gemeindeweise ausgezählt.
Dutzende Briefwahlbezirk-Zeilen in der Quelldatei sind nur einer Verwaltungsgemeinschaft, nicht
einer einzelnen Gemeinde zugeordnet, ohne dass die Datei eine eindeutige Aufteilung angibt. Beim
Abgleich gegen den bisherigen GERDA-Datensatz weicht die Wahlbeteiligung deshalb bei 90 % der 591
gemeinsamen Gemeinden um mehr als 2 Prozentpunkte ab (Median rund 8 Punkte, Extremfälle über 20
Punkte); auch die Parteianteile schwanken entsprechend. Das ist genau das Briefwahl-Zurechnungsproblem,
wegen dem dieses Projekt sonst GENESIS/rohe Landesquellen zugunsten von GERDA meidet (siehe
README.md, „Warum GERDA"). Die Umstellung erfolgt trotzdem, auf ausdrücklichen Wunsch: einheitlich
amtliche Zahlen für Thüringen statt GERDA, auch mit dieser bekannten Ungenauigkeit bei kleineren
Gemeinden. Für die kreisfreien Städte Erfurt, Gera, Jena und Weimar (auf mehrere Wahlkreise
aufgeteilt, deren Teilergebnisse aufsummiert werden) ist die Auswirkung gering, da sie jeweils
eigene Briefwahlbezirke haben.

Vier sehr kleine Gemeinden (u. a. Gerstengrund) weisen in der Quelldatei eine eigene Zeile ohne jede
Stimme aus – ihre Wahlbezirke sind laut Datei vollständig an eine Nachbargemeinde abgegeben. Diese
vier Zeilen bleiben deshalb ausgelassen, wie bei GERDA auch, statt eine leere Gemeinde zu erzeugen.

Parteinamen wurden an GERDAs Schreibweise angeglichen (`WU` → `WerteUnion`, `FAMILIE` → `Familie`,
`ÖDP / Familie ..` → `ÖDP`).

> Datenquelle: Thüringer Landeswahlleiter, endgültiges Ergebnis der Landtagswahl vom 1. September
> 2024; eigene Aufbereitung (Landesstimmenanteile)

Die Ergebnisseite weist für diese Datei keine standardisierte offene Lizenz wie CC BY oder
`dl-de/by-2-0` aus. Deshalb behaupten die erzeugte Datei und dieses Repo keine solche Lizenz. Bei
einer Weiterverwendung sind die Nutzungsbedingungen der amtlichen Quelle zu beachten.

**Ungeprüft:** Ob die verlinkte Ergebnisseite eine andere Lizenz nennt als zum Zeitpunkt dieser
Ergänzung eingesehen, sollte vor einer Weiterverwendung erneut geprüft werden.

## Rheinland-Pfalz: Kommunal- und Kreistagswahl 2024

Quelle: Landeswahlleiter Rheinland-Pfalz, endgültige Ergebnisse der Kommunalwahlen vom 9. Juni
2024 (Stadtratswahlen der kreisfreien Städte und Kreistagswahlen):
<https://www.wahlen.rlp.de/kommunalwahlen/ergebnisse-1>

Direkte Quelldatei: `KW_2024_Ergebisse_Kreisebene.pdf` auf `wahlen.rlp.de`.

**Anders als die übrigen Ergänzungen kein automatischer Abruf.** Die Quelldatei ist eine PDF mit
mehrspaltigen Tabellen; eine zuverlässige Extraktion brauchte eine Tabellen-Bibliothek, die dieser
rein auf die Python-Standardbibliothek gestützte Sammler nicht mitbringt (siehe
`scripts/sammeln.py`, Modul-Docstring). Die Zahlen wurden deshalb einmalig von Hand extrahiert
und liegen als geprüfter Snapshot unter `quellen/rlp-kommunalwahlen-2024-kreisebene.json`.

**Geprüft gegen die in derselben PDF mitgelieferte 2019er-Vergleichsspalte:** Alle 36 Gebiete
(12 kreisfreie Städte, 24 Landkreise) stimmen mit den bis dahin verwendeten GERDA-2019-Werten
exakt überein (Toleranz 0,15 Prozentpunkte je Partei, 0,3 für die zusammengefassten
Kleinparteien/Wählergruppen) – ein starkes Indiz, dass sowohl die vorherigen GERDA-Daten als auch
diese Extraktion korrekt sind.

**Deckt nur einen Teil der Kommunalwahl ab.** Die PDF weist ausschließlich die 12 kreisfreien
Städte und die 24 Landkreise aus, nicht die übrigen rund 2.280 rheinland-pfälzischen Gemeinden
(Ortsgemeinden, Verbandsgemeinden). Für diese fehlt bislang eine amtliche, maschinell auswertbare
2024er-Quelle. Sie werden deshalb bewusst **nicht** mit GERDAs älterem 2019er-Stand aufgefüllt,
sondern fehlen ganz aus `07/kommunal.json` – lieber kein Datensatz als eine veraltete Zahl unter
dem Anschein von Aktualität. `GENESIS`/`regionalstatistik.de` wurde als Ersatzquelle bewusst nicht
herangezogen: Bei gemeinsam ausgezählter Briefwahl fehlen dort auf Gemeindeebene Stimmen oder sie
werden dem falschen Gebiet zugerechnet (siehe README.md, „Warum GERDA").

> Datenquelle: Landeswahlleiter Rheinland-Pfalz, endgültige Ergebnisse der Stadtratswahlen der
> kreisfreien Städte bzw. der Kreistagswahlen vom 9. Juni 2024; eigene Aufbereitung (gewichtete
> Stimmenanteile)

Die Ergebnisseite weist für diese Datei keine standardisierte offene Lizenz wie CC BY oder
`dl-de/by-2-0` aus. Deshalb behaupten die erzeugte Datei und dieses Repo keine solche Lizenz. Bei
einer Weiterverwendung sind die Nutzungsbedingungen der amtlichen Quelle zu beachten.

**Ungeprüft:** Ob die verlinkte Ergebnisseite eine andere Lizenz nennt als zum Zeitpunkt dieser
Ergänzung eingesehen, sollte vor einer Weiterverwendung erneut geprüft werden.

31 Gemeinden führten die Briefwahl auch für ihre Nachbargemeinden durch. Deren Briefwähler zählen
in der amtlichen Datei bei der durchführenden Gemeinde mit, obwohl sie dort nicht wahlberechtigt
sind. Das verfälscht dort sowohl die Wahlbeteiligung als auch die Parteianteile; alle betroffenen
Gemeinden tragen deshalb einen `hinweis` mit der amtlichen Erläuterung. In drei Fällen ergäbe die
Rechnung eine Wahlbeteiligung über 100 Prozent (bis zu 131,5 Prozent); dort bleibt `beteiligung`
leer, weil eine solche Zahl keine Wahlbeteiligung mehr ist.

## Thüringen: Gemeinde- und Stadtratswahl 2024

Quelle: Thüringer Landeswahlleiter, endgültiges Ergebnis der Gemeinderats- und Stadtratswahlen vom
26. Mai 2024: <https://wahlen.thueringen.de/kommunalwahlen/kw_wahlergebnisse_GW.asp>

Direkte Quelldateien: `GWInfoG2024.xlsx` (600 Gemeinden, `NeuLesen.asp?seite=GWInfoG2024`) sowie
`KWInfo2024.xlsx` (5 kreisfreie Städte, `NeuLesen.asp?seite=KWInfo2024`) auf `wahlen.thueringen.de`.

**Ersetzt GERDA vollständig, statt es nur zu ergänzen.** GERDAs `municipal_harm_25.csv` führt für
Thüringen 600 Gemeinden, aber keine der fünf kreisfreien Städte (Erfurt, Gera, Jena, Suhl, Weimar) –
die Landeshauptstadt eingeschlossen. Die amtliche Quelle deckt dagegen alle 605 Gebiete ab, deshalb
ersetzt diese Ergänzung GERDAs Ergebnis für Thüringen vollständig, statt nur die fünf fehlenden
Städte hinzuzufügen – die Datei stammt damit einheitlich aus einer Quelle statt aus GERDA plus einer
punktuellen Ergänzung.

**Geprüft gegen den bisherigen GERDA-Datensatz:** 599 von 600 Gemeinden stimmen mit den bis dahin
verwendeten GERDA-2024-Werten exakt überein (Toleranz 0,3 Prozentpunkte je Partei) – ein starkes
Indiz, dass sowohl GERDAs Daten als auch diese Extraktion korrekt sind. Die einzige Abweichung
(Uhlstädt-Kirchhasel) ist eine Lücke in GERDAs eigener Harmonisierung: Die Liste „FREIE WÄHLER" ist
dort identisch beschriftet wie in den 21 anderen Gemeinden, in denen GERDA sie korrekt erkennt,
wird aber nur dort fälschlich in „Sonstige" zusammengefasst. Dieselben Quelldateien führen zusätzlich
die Kreistagswahl-Ergebnisse der 17 Landkreise; sie stimmen ebenfalls exakt mit GERDAs
Kreistagswahl-Datensatz überein, der deshalb unverändert bleibt (kein Wechsel nötig).

**Parteizuordnung wie bei GERDA:** CDU, SPD, DIE LINKE, GRÜNE, AfD, PIRATEN, FDP, Die PARTEI, FREIE
WÄHLER und BSW bleiben als eigene Partei erhalten – dieselbe Zuordnung, die GERDA für
Gemeinde-/Stadtratswahlen verwendet. Alle örtlichen Listen, Wählervereinigungen und Einzelbewerber
werden als `Sonstige` zusammengefasst, auch in den rund 210 kleinen Gemeinden mit reiner
Mehrheitswahl (dort stehen auf dem Stimmzettel keine Parteien, sondern einzelne Personen).

**Zwei Wiederholungswahlen.** Für Rauschwitz (16074073) und Umpferstedt (16071089) galt statt der
Maiwahl 2024 eine spätere Wiederholungswahl (5. bzw. 12. Januar 2025); die Datei verwendet die
neueren Einzelergebnisse (`ErgebnisGW_*.pdf`).

> Datenquelle: Thüringer Landeswahlleiter, endgültiges Ergebnis der Gemeinderats- und
> Stadtratswahlen vom 26. Mai 2024 (Rauschwitz und Umpferstedt: Wiederholungswahl Januar 2025);
> eigene Aufbereitung

Die Ergebnisseite weist für diese Dateien keine standardisierte offene Lizenz wie CC BY oder
`dl-de/by-2-0` aus. Deshalb behaupten die erzeugte Datei und dieses Repo keine solche Lizenz. Bei
einer Weiterverwendung sind die Nutzungsbedingungen der amtlichen Quelle zu beachten.

**Ungeprüft:** Ob die verlinkte Ergebnisseite eine andere Lizenz nennt als zum Zeitpunkt dieser
Ergänzung eingesehen, sollte vor einer Weiterverwendung erneut geprüft werden.

## Bayern: Kreistagswahl 2026

Quelle: Bayerisches Landesamt für Statistik, endgültiges Ergebnis der Kreistagswahlen vom 8. März
2026: <https://www.statistik.bayern.de/wahlen/kommunalwahlen/index.html>

Direkte Quelldatei: `Kommunalwahl_Gremien_Landkreise.xml` (mit Schema `KWADEXEG.xsd`) unter
`kommunalwahl2026.bayern.de/downloads/gremienwahl/`.

**Strukturiertes XML statt fester Parteispalten.** Anders als GERDAs Kreistag-Datensatz, der
wiederkehrende Parteien über `KREISTAG_GRUPPEN` zuordnet und alles Übrige zu „Sonstige”
zusammenfasst, liefert die amtliche Quelle eine `<Wahlvorschlag>`-Zeile je tatsächlich angetretener
Liste mit ihrem echten Namen. Das erhält alle 189 in den 71 Landkreisen tatsächlich angetretenen
Wahlvorschläge, darunter zahlreiche örtliche Wählergruppen und Kreisverbände (z. B.
„Bürgerliste Reichenhall”, „FREIE WÄHLER/Freie Wähler Kreisverband Dachau e.V.”).

**Gewichtete Stimmen statt Rohstimmen.** Bayerns Kommunalwahlrecht erlaubt Kumulieren und
Panaschieren (mehrere Stimmen je Wählendem, verteilbar auf mehrere Listen). Die Quelle liefert
dafür bereits `Gewichtete_Stimmen_absolut` je Wahlvorschlag – dieselbe Gewichtung, die für die
Sitzverteilung maßgeblich ist. Der Parser übernimmt sie direkt, statt eigene Rohstimmen zu zählen,
und normiert sie auf die von der Quelle gemeldete gewichtete Gesamtstimmenzahl.

**Geprüft:** Für alle 71 Landkreise wurde die Summe der gewichteten Wahlvorschlagsstimmen exakt
gegen die von der Quelle gemeldete Gesamtsumme verglichen – keine Abweichung. Eine Liste, die 2026
nicht mehr antrat, erscheint in der Quelldatei nur als Verlaufszeile ohne aktuelle Stimmenangabe;
sie zählt als 0 aktuelle Stimmen, nicht als Fehler.

**Deckt nur die Kreistagswahl ab.** Die Gemeinderats-/Stadtratswahl der rund 2.000 kreisangehörigen
bayerischen Gemeinden liegt bei dieser Quelle nicht als eine gemeinsam abrufbare Datei vor, sondern
nur als einzelne Ergebnisseiten je Gemeinde auf `kommunalwahl2026.bayern.de` – das bleibt vorerst
bei GERDA. Die Landtagswahl ist ebenfalls nicht Teil dieser Ergänzung.

> Datenquelle: Bayerisches Landesamt für Statistik, endgültiges Ergebnis der Kreistagswahlen vom
> 8. März 2026; eigene Aufbereitung (gewichtete Stimmenanteile gemäß Kumulieren/Panaschieren)

**Lizenz:** § 9 der AGB des Bayerischen Landesamts für Statistik
(<https://www.statistik.bayern.de/meta/agb/index.html>) erlaubt Vervielfältigung und
Weiterverbreitung, auch auszugsweise, mit Quellenangabe: „Datenquelle: Bayerisches Landesamt für
Statistik – www.statistik.bayern.de”. Keine standardisierte offene Lizenz wie CC BY, aber eine
ausdrückliche, unbeschränkte Weiterverwendungserlaubnis mit Namensnennung.

## Brandenburg: Gemeindevertretungswahl 2024

Quelle: Amt für Statistik Berlin-Brandenburg, amtliches Ergebnis der Wahlen zu den
Gemeindevertretungen vom 9. Juni 2024 (2., aktualisierte Auflage vom 8. Oktober 2024):
<https://wahlen.brandenburg.de/wahlen/de/kommunalwahlen/ergebnisse/kommunalwahlen/>

Direkte Quelldatei: `DL_BB_GVW2024.xlsx` unter
`wahlergebnisse.brandenburg.de/12/300/20240609/gemeindevertretungswahl_land/DL/`.

**Ersetzt GERDAs Kommunaldatensatz für Brandenburg vollständig.** Anders als die meisten anderen
Länderquellen dieses Sammlers liegt die Datei bereits im Langformat vor: eine Zeile je Gemeinde
UND Wahlvorschlag (Partei, Parteivereinigung, Listenvereinigung, Wählergruppe oder Einzelbewerber)
statt fester Parteispalten. Dadurch bleiben alle echten Namen erhalten, auch lokale
Wählergruppen und Einzelbewerber (z. B. „Bürger für Frieden, Vernunft und Gerechtigkeit”,
„EB Wenzel”), die GERDAs `municipal_harm_25.csv` sonst ungenannt in `other`/„Sonstige”
zusammenfasst (siehe Issue #10).

**Geprüft:** Für alle 413 Gemeinden wurde die Summe der gemeldeten Wahlvorschlagsstimmen exakt
gegen die von der Quelle selbst gemeldeten gültigen Stimmen verglichen – keine Abweichung. Die
Kreistagswahl (`DL_BB_KW2024.xlsx`, dieselbe Quelle) und die Landtagswahl (`DL_BB_LT2024.xlsx`,
Wahlbezirksebene) sind nicht Teil dieser Ergänzung und bleiben vorerst bei GERDA.

> Datenquelle: Amt für Statistik Berlin-Brandenburg, amtliches Ergebnis der Wahlen zu den
> Gemeindevertretungen vom 9. Juni 2024 (2., aktualisierte Auflage vom 8. Oktober 2024); eigene
> Aufbereitung (Stimmenanteile je Wahlvorschlag)

**Lizenz:** Die Quelldatei nennt im Tabellenblatt „Impressum” ausdrücklich eine Creative-Commons-
Lizenz vom Typ Namensnennung 3.0 Deutschland (CC BY 3.0 DE, <http://creativecommons.org/licenses/by/3.0/de/>).

## Coverage-Heatmap: Straßennetz, Gemeindegrenzen, Bevölkerungsdichte

Die Dateien unter `daten/coverage/` (erzeugt von `coverage/bauen.py`, Issue #261) fassen drei
amtliche/offene Quellen je H3-Zelle zusammen; jede einzelne bleibt unter ihrer eigenen Lizenz.

### Straßennetz (OpenStreetMap via Geofabrik)

Quelle: OpenStreetMap-Mitwirkende, bezogen als `germany-latest.osm.pbf` von
<https://download.geofabrik.de/europe/germany.html>.

Lizenz: Open Database License (ODbL) 1.0: <https://opendatacommons.org/licenses/odbl/1-0/>

> Datenquelle: © OpenStreetMap-Mitwirkende, ODbL; eigene Aufbereitung (Filterung auf fußläufig
> relevante Straßentypen, Länge je H3-Zelle)

Nur die in `docs/coverage-score-v1.md` (Repo `plakat-radar-intern`) festgelegten Straßentypen
gehen ein (`highway ∈ {residential, living_street, pedestrian, footway, path, service,
unclassified, tertiary, secondary}`, `foot≠no`, ohne `access=private`) – die App liefert also
keine Rohgeometrie aus, nur eine daraus abgeleitete Kennzahl (Straßenlänge je Zelle in km).

### Gemeindegrenzen (BKG VG250)

Quelle: Bundesamt für Kartographie und Geodäsie (BKG), Verwaltungsgebiete 1:250.000 (VG250),
Gemeinde-Ebene, bezogen über den WFS `https://sgx.geodatenzentrum.de/wfs_vg250`.

Lizenz: Datenlizenz Deutschland – Namensnennung – Version 2.0 (`dl-de/by-2-0`):
<https://www.govdata.de/dl-de/by-2-0>

> © GeoBasis-DE / BKG (Jahr des Datenbezugs), Daten verändert (Gemeinde-AGS je H3-Zelle
> zugeordnet, keine Geometrie ausgeliefert)

Nur der Landflächen-Datensatz je Gemeinde wird verwendet (`GF=4`, siehe VG250-Dokumentation
Abschnitt 3.2.2) – der zusätzliche Wasserflächen-Datensatz von Küsten-Gemeinden (`GF=2`) bleibt
außen vor, da er keine bewohnte/bearbeitbare Fläche beschreibt.

### Bevölkerungsdichte (Zensus 2022, 100-m-Gitter)

Quelle: Statistische Ämter des Bundes und der Länder, Zensus 2022, Ergebnisse auf
Gitterzellenebene (`Zensus2022_Bevoelkerungszahl.zip`, 100-m-Gitter):
<https://www.zensus2022.de/DE/Ergebnisse-des-Zensus/gitterzellen.html>

Lizenz: Datenlizenz Deutschland – Namensnennung – Version 2.0 (`dl-de/by-2-0`):
<https://www.govdata.de/dl-de/by-2-0>

> Datenquelle: Zensus 2022, Statistische Ämter des Bundes und der Länder; eigene Aufbereitung
> (Einwohnerzahl je H3-Zelle aus den 100-m-Gitterzellen aggregiert, durch die Zellfläche geteilt)

Dieselbe amtliche Zensus-2022-Quelle, die die App zur Laufzeit über den Sozialdaten-Chip live
vom ArcGIS-FeatureServer abfragt (`ZensusGridClient.kt` in `plakat-radar-intern`) – hier als
Bulk-Download statt Live-Abfrage, weil eine Live-ID-Abfrage für ganz Deutschland nicht praktikabel
ist.

### Formelversion

`formulaVersion` in jeder Bündel-Datei (aktuell `coverage-formula-v1`) verweist auf
`docs/coverage-score-v1.md` im Repo `plakat-radar-intern` – dort steht die Berechnungsvorschrift,
die aus diesen Rohdaten den eigentlichen Coverage-Score bildet.

## Metadaten in den JSON-Dateien

Jede Datei führt ihre Bedingungen selbst mit:

- `quelle`
- `quellenvermerk`
- `lizenz`
- `lizenz_url`
- `quellendatei`
- bei GERDA zusätzlich `dataset` und `zitation`

`daten/index.json` wiederholt Quelle und Lizenz je Eintrag. Anwendungen sollten deshalb nicht mehr
von einer einzigen gemeinsamen Lizenz für den ganzen Ordner ausgehen.
