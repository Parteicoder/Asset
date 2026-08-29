#!/usr/bin/env python3
"""Parser-Selbsttest ohne Netz, Zugangsdaten oder Fremdpakete."""

from __future__ import annotations

import json
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sammeln as sammler  # noqa: E402
from sammeln import (  # noqa: E402
    Fehler,
    gerda_datei_auswerten,
    gerda_kommunal_auswerten,
    gerda_kreisverzeichnis_auswerten,
    gerda_kreistag_auswerten,
    kerg2_auswerten,
    rlp_zeilen_auswerten,
)


fehler = 0


def pruefe(bedingung, text):
    global fehler
    if bedingung:
        print(f"  ok    {text}")
    else:
        print(f"  FEHLT {text}")
        fehler += 1


# Die GERDA-Prozente sind Bruchteile (0 bis 1). `far_right` ist eine abgeleitete Kennzahl und
# muss wegen der ausdrücklich begrenzten Parteispalten draußen bleiben.
GERDA = """ags,ags_name,election_year,election_date,state,turnout,other,50plus,afd,bsw,cdu,fdp,freie_wahler,gruene,linke_pds,spd,ssw,zentrum,far_right
14730110,Eilenburg,2020,2020-01-01,14,0.600,0.02,,0.28,,0.32,0.05,0.03,0.08,0.07,0.15,,,0.28
14730110,,2024,2024-09-01,14,0.708,0.01,,0.35,0.12,0.30,0.01,0.03,0.05,0.04,0.09,,,0.35
14713000,Leipzig,2024,2024-09-01,14,0.720,0.02,,0.10,,0.15,0.03,0.05,0.10,0.05,0.10,,,0.10
08111000,Stuttgart,2021,2021-03-14,08,0.640,0.02,,0.10,,0.30,0.08,0.02,0.20,0.05,0.23,,,0.10
08111000,Stuttgart,2026,2026-03-08,08,0.701,0.02,,0.20,0.10,0.25,0.04,0.03,0.18,0.05,0.13,,,0.20
"""


print("GERDA: jüngste Wahl und Parteien")
with tempfile.TemporaryDirectory(prefix="plakat-test-") as ordner:
    datei = Path(ordner) / "gerda.csv"
    datei.write_text(GERDA, encoding="utf-8")
    g = gerda_datei_auswerten(datei, {"08", "14"})

pruefe(set(g) == {"08", "14"}, f"beide Länder erkannt ({set(g)})")
pruefe(g["14"]["jahr"] == 2024, f"Sachsen 2024 statt historischer Zeile ({g['14']['jahr']})")
pruefe(g["08"]["jahr"] == 2026, f"Baden-Württemberg 2026 erkannt ({g['08']['jahr']})")
pruefe(set(g["14"]["gebiete"]) == {"14730110"}, "unplausible Leipziger Testzeile verworfen")
eilenburg = g["14"]["gebiete"]["14730110"]
pruefe(eilenburg["name"] == "Eilenburg", "fehlender aktueller Name über denselben AGS ergänzt")
pruefe(eilenburg["beteiligung"] == 70.8, f"Turnout-Bruch in Prozent gewandelt ({eilenburg['beteiligung']})")
pruefe(eilenburg["parteien"].get("AfD") == 35.0, f"AfD korrekt ({eilenburg['parteien'].get('AfD')})")
pruefe(eilenburg["parteien"].get("BSW") == 12.0, f"BSW korrekt ({eilenburg['parteien'].get('BSW')})")
pruefe("Far Right" not in eilenburg["parteien"], "abgeleitete GERDA-Spalte nicht als Partei gezählt")
pruefe(abs(sum(eilenburg["parteien"].values()) - 100.0) < 0.2, "gerundete Anteile ergeben rund 100 Prozent")


print("GERDA: verständlicher Schemafehler")
with tempfile.TemporaryDirectory(prefix="plakat-test-") as ordner:
    datei = Path(ordner) / "kaputt.csv"
    datei.write_text("ags,state,election_year\n14730110,14,2024\n", encoding="utf-8")
    try:
        gerda_datei_auswerten(datei, {"14"})
        pruefe(False, "fehlende Spalten hätten einen Fehler auslösen müssen")
    except Fehler as exc:
        pruefe("ags_name" in str(exc), f"fehlende Spalte genannt ({exc})")


KOMMUNAL = """ags,ags_name,election_year,election_date,state,turnout,cdu_csu,spd,linke_pds,gruene,afd,piraten,fdp,die_partei,freie_wahler,bsw,other
14730110,Eilenburg,2019,,14,0.62,0.20,0.15,0.05,0.10,0.20,,0.05,,0.05,,0.20
14730110,Eilenburg,2024,2024-06-09T00:00:00Z,14,0.701,0.25,0.12,0.04,0.08,0.22,,0.03,0.01,0.05,0.10,0.10
14730270,Taucha,2024,2024-06-09T00:00:00Z,14,0.650,0.20,0.10,0.05,0.05,0.25,,0.05,,,,0.30
07131004,Antweiler,2019,,07,0.70,,,,,,,,,,,1
"""


print("GERDA: Gemeinde- und Stadtratswahlen")
with tempfile.TemporaryDirectory(prefix="plakat-test-") as ordner:
    datei = Path(ordner) / "municipal_harm_25.csv"
    datei.write_text(KOMMUNAL, encoding="utf-8")
    kommunal = gerda_kommunal_auswerten(datei, {"07", "14"})

pruefe(kommunal["14"]["jahr"] == 2024, "jüngste Kommunalwahl je Land gewählt")
pruefe(kommunal["14"]["wahl_datum"] == "2024-06-09", "ISO-Wahltag gekürzt")
pruefe(set(kommunal["14"]["gebiete"]) == {"14730110", "14730270"}, "Gemeinden vollständig")
pruefe(
    kommunal["14"]["gebiete"]["14730110"]["parteien"].get("BSW") == 10.0,
    "BSW-Anteil der Stadtratswahl übernommen",
)
pruefe(
    "örtliche Listen" in kommunal["07"]["gebiete"]["07131004"]["hinweis"],
    "reine Sonstige-Ergebnisse erklärt",
)


KREISVERZEICHNIS = """county,county_name,county_type,state,year
14730,Nordsachsen,Landkreis,14,2024
14713,Leipzig,kreisfreie Stadt,14,2024
"""

KREISTAG = """county_code,election_year,state,eligible_voters,number_voters,valid_votes,invalid_votes,cdu,csu,spd,gruene,afd,bsw,waehlergruppen,einzelbewerber,lokale_liste,bemerkungen,flag_unsuccessful_naive_merge,flag_partial_coverage,turnout,ags,far_right,far_left,far_left_w_linke,total_vote_share,flag_total_votes_incongruent,perc_total_votes_incogruence,area,population
14730,2019,14,1000,600,590,10,0.30,,0.20,0.10,0.20,,0.10,,0.10,,0,0,0.60,14730000,0,0,0,1,0,0,1,1
14730,2024,14,1000,700,690,10,0.25,,0.15,0.10,0.20,0.10,0.10,,0.10,,0,0,0.70,14730000,0,0,0,1,0,0,1,1
14713,2024,14,5000,3500,3400,100,0.25,,0.15,0.10,0.20,0.10,0.10,,0.10,,0,0,0.70,14713000,0,0,0,1,0,0,1,1
"""


print("GERDA: Kreistagswahlen")
with tempfile.TemporaryDirectory(prefix="plakat-test-") as ordner:
    kreise_datei = Path(ordner) / "county_council_seats.csv"
    kreise_datei.write_text(KREISVERZEICHNIS, encoding="utf-8")
    kreistag_datei = Path(ordner) / "county_elec_harm_21_cty.csv"
    kreistag_datei.write_text(KREISTAG, encoding="utf-8")
    kreise = gerda_kreisverzeichnis_auswerten(kreise_datei)
    kreistage = gerda_kreistag_auswerten(kreistag_datei, kreise, {"14"})

pruefe(set(kreistage["14"]["gebiete"]) == {"14730"}, "kreisfreie Stadt ausgelassen")
nordsachsen = kreistage["14"]["gebiete"]["14730"]
pruefe(nordsachsen["name"] == "Nordsachsen", "Kreisname aus Verzeichnis übernommen")
pruefe(nordsachsen["parteien"].get("BSW") == 10.0, "BSW-Anteil der Kreistagswahl übernommen")
pruefe(nordsachsen["parteien"].get("Sonstige") == 10.0, "unbekannte örtliche Listen erhalten")
pruefe(abs(sum(nordsachsen["parteien"].values()) - 100.0) < 0.2, "Kreistagsanteile normiert")


def rlp_zeile(kennung, code, name, gueltig=100, ziel=""):
    zeile = {
        "A": kennung,
        "B": "0",
        "C": code,
        "D": name,
        "E": "G",
        "M": "68.4",
        "DP": str(gueltig) if gueltig else "",
        "HO": ziel,
    }
    stimmen = {"DR": 20, "DT": 30, "DV": 10, "DX": 15, "DZ": 5, "EB": 5,
               "ED": 5, "EF": 2, "EH": 2, "EJ": 1, "EL": 5, "EN": 0}
    for spalte, wert in stimmen.items():
        zeile[spalte] = str(wert) if gueltig else ""
    return zeile


print("Rheinland-Pfalz: amtliche Gemeindezeilen")
ziel_id = "1021321008900"
rlp = rlp_zeilen_auswerten([
    rlp_zeile("1011320301800", "GD", "Daaden"),
    rlp_zeile(ziel_id, "GD", "Peterslahr"),
    # Die amtliche XLSX hängt fünf Stimmbezirksstellen an das Zusammenlegungsziel.
    rlp_zeile("1021321002900", "GD", "Eulenberg", gueltig=0, ziel=ziel_id + "00000"),
    rlp_zeile("1110000000", "KS", "Koblenz, Kreisfreie Stadt"),
])
pruefe("07132018" in rlp, f"Daadens vollständiger AGS abgeleitet ({list(rlp)})")
pruefe("07111000" in rlp, "kurzer XLSX-Schlüssel der kreisfreien Stadt mit Nullen ergänzt")
pruefe(rlp["07132018"]["parteien"].get("CDU") == 30.0, "Landesstimmenanteil aus Stimmenzahl berechnet")
pruefe(rlp["07132029"]["zusammengelegt_mit"] == "07132089", "Zusammenlegungsziel als AGS gespeichert")
pruefe("Gemeinsam" in rlp["07132029"]["hinweis"], "gemeinsam ausgewiesenes Ergebnis gekennzeichnet")


print("XLSX-Grundleser")
SHARED = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Hallo</t></si></sst>"""
SHEET = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1"><v>42</v></c></row>
</sheetData></worksheet>"""
with tempfile.TemporaryDirectory(prefix="plakat-test-") as ordner:
    datei = Path(ordner) / "mini.xlsx"
    with zipfile.ZipFile(datei, "w", zipfile.ZIP_DEFLATED) as archiv:
        archiv.writestr("xl/sharedStrings.xml", SHARED)
        archiv.writestr("xl/worksheets/sheet1.xml", SHEET)
    xlsx = sammler._xlsx_zeilen(datei)
pruefe(xlsx == [{"A": "Hallo", "B": "42"}], f"gemeinsame Texte und Zahlen gelesen ({xlsx})")


print("XLSX: Tabellenblatt nach Namen statt Position finden")
WORKBOOK = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Erste" sheetId="1" r:id="rId1"/><sheet name="Ziel" sheetId="2" r:id="rId2"/></sheets>
</workbook>"""
WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
</Relationships>"""
BLATT_1 = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
<row r="1"><c r="A1"><v>1</v></c></row>
</sheetData></worksheet>"""
BLATT_2 = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
<row r="1"><c r="A1"><v>2</v></c></row>
</sheetData></worksheet>"""
with tempfile.TemporaryDirectory(prefix="plakat-test-") as ordner:
    datei = Path(ordner) / "mehrblatt.xlsx"
    with zipfile.ZipFile(datei, "w", zipfile.ZIP_DEFLATED) as archiv:
        archiv.writestr("xl/workbook.xml", WORKBOOK)
        archiv.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS)
        archiv.writestr("xl/worksheets/sheet1.xml", BLATT_1)
        archiv.writestr("xl/worksheets/sheet2.xml", BLATT_2)
    ziel_zeilen = sammler._xlsx_zeilen(datei, "Ziel")
    try:
        sammler._xlsx_zeilen(datei, "Fehlt")
        unbekannt_scheitert = False
    except Fehler:
        unbekannt_scheitert = True
pruefe(ziel_zeilen == [{"A": "2"}], f"benanntes statt erstes Tabellenblatt gelesen ({ziel_zeilen})")
pruefe(unbekannt_scheitert, "unbekannter Blattname schlägt kontrolliert fehl")


def sachsen_zeile(ags, ebene, name, stimmen, wahlberechtigte=1000, waehler=700, briefwahl=""):
    zeile = {"E": ebene, "F": ags, "G": name, "M": str(wahlberechtigte), "N": str(waehler)}
    if briefwahl:
        zeile["H"] = "J"
        zeile["I"] = briefwahl
    zeile["AR"] = str(sum(stimmen.values()))
    for spalte, (_, anzeigename) in sammler.SACHSEN_PARTEISPALTEN.items():
        zeile[spalte] = str(stimmen.get(anzeigename, 0))
    return zeile


print("Sachsen: Gemeindezeilen und reine Teilgemeinde-Städte zusammensetzen")
# Die Vollständigkeitsprüfung verlangt mindestens 380 Gemeindezeilen; das wird hier mit
# gleichförmigen Fixture-Gemeinden erfüllt.
ge_zeilen = [
    sachsen_zeile(f"14{n:06d}", "GE", f"Gemeinde {n}", {"CDU": 40, "AfD": 30, "SPD": 20, "GRÜNE": 10})
    for n in range(1, 415)
]
chemnitz_1 = sachsen_zeile("145110001", "TG", "Chemnitz 1", {"CDU": 30, "AfD": 20, "BSW": 10})
chemnitz_2 = sachsen_zeile("145110002", "TG", "Chemnitz 2", {"CDU": 15, "AfD": 15, "BSW": 10})
# Alle vier reinen Teilgemeinde-Städte müssen vorkommen, sonst schlägt der Sammler bewusst fehl
# (siehe nächste Prüfung); Dresden, Leipzig und Zwickau reichen hier mit je einer Teilgemeinde.
sonstige_staedte = [
    sachsen_zeile("146120001", "TG", "Dresden 1", {"CDU": 10, "AfD": 10}),
    sachsen_zeile("147130001", "TG", "Leipzig 1", {"CDU": 10, "AfD": 10}),
    sachsen_zeile("145243301", "TG", "Zwickau, Stadt (Stadtbezirk West)", {"CDU": 10, "AfD": 10}),
]
sachsen = sammler.sachsen_zeilen_auswerten([*ge_zeilen, chemnitz_1, chemnitz_2, *sonstige_staedte])
pruefe(len(sachsen) == 418, f"Gemeinden plus vier zusammengesetzte Städte ({len(sachsen)})")
pruefe(sachsen["14511000"]["name"] == "Chemnitz, Stadt", "amtlicher Stadtname statt Teilgemeindename")
pruefe(
    sachsen["14511000"]["parteien"]["CDU"] == 45.0,
    f"Chemnitz-CDU-Stimmen aus zwei Teilgemeinden aufsummiert ({sachsen['14511000']['parteien']})",
)
pruefe(
    sachsen["14511000"]["beteiligung"] == 70.0,
    "Chemnitz-Beteiligung aus summierten Wahlberechtigten und Wählern berechnet",
)

print("Sachsen: unbekannte Teilgemeinde-Stadt ohne Gemeindezeile schlägt fehl")
try:
    sammler.sachsen_zeilen_auswerten(
        [
            *ge_zeilen,
            chemnitz_1,
            chemnitz_2,
            *sonstige_staedte,
            sachsen_zeile("199990001", "TG", "Unbekannt 1", {"CDU": 10}),
        ]
    )
    unbekannte_stadt_scheitert = False
except Fehler:
    unbekannte_stadt_scheitert = True
pruefe(unbekannte_stadt_scheitert, "Teilgemeinde ohne bekannte Zielgemeinde schlägt kontrolliert fehl")

print("Sachsen: fehlende Teilgemeinde-Stadt schlägt fehl")
try:
    sammler.sachsen_zeilen_auswerten([*ge_zeilen, chemnitz_1, chemnitz_2])
    fehlende_stadt_scheitert = False
except Fehler:
    fehlende_stadt_scheitert = True
pruefe(fehlende_stadt_scheitert, "fehlende Teilgemeinde-Stadt (Dresden/Leipzig/Zwickau) schlägt kontrolliert fehl")

print("Sachsen: Briefwahl für Nachbargemeinden")
# Die amtliche Datei weist für solche Gemeinden bis zu 131,5 Prozent Wahlbeteiligung aus, weil
# fremde Briefwähler mitzählen. Eine unmögliche Zahl darf nicht in die App gelangen.
ueber_hundert = sammler._sachsen_gebiet(
    "Schönfeld",
    [sachsen_zeile("14627250", "GE", "Schönfeld", {"CDU": 100}, wahlberechtigte=1428, waehler=1878,
                   briefwahl="Gemeinde führte Briefwahl ebenfalls für Lampertswalde durch.")],
)
unter_hundert = sammler._sachsen_gebiet(
    "Seiffen",
    [sachsen_zeile("14521570", "GE", "Seiffen", {"CDU": 100}, wahlberechtigte=1000, waehler=873,
                   briefwahl="Gemeinde führte Briefwahl ebenfalls für Heidersdorf durch.")],
)
pruefe(ueber_hundert["beteiligung"] is None, f"über 100 Prozent wird verworfen ({ueber_hundert['beteiligung']})")
pruefe("Briefwähler" in ueber_hundert.get("hinweis", ""), "Briefwahl-Sonderfall wird erklärt")
pruefe(
    unter_hundert["beteiligung"] == 87.3,
    f"plausible Beteiligung bleibt trotz Sonderfall erhalten ({unter_hundert['beteiligung']})",
)
pruefe("Briefwähler" in unter_hundert.get("hinweis", ""), "auch der unauffällige Sonderfall wird gekennzeichnet")


print("Sachsen: widersprüchliche Stimmensumme schlägt fehl")
kaputt = sachsen_zeile("14999999", "GE", "Kaputt", {"CDU": 40})
kaputt["AR"] = "999"
try:
    sammler._sachsen_gebiet("Kaputt", [kaputt])
    summenfehler_scheitert = False
except Fehler:
    summenfehler_scheitert = True
pruefe(summenfehler_scheitert, "Stimmensumme ungleich gültigen Listenstimmen schlägt kontrolliert fehl")


def sachsenanhalt_zeile(ags, name, stimmen, wahlberechtigte=1000, waehler=700, satzart="GEM"):
    zeile = {
        "Satzart": satzart,
        "Schlüsselnummer": ags,
        "Name": name,
        "A - Wahlberechtigte": str(wahlberechtigte),
        "B - Wähler": str(waehler),
        "F - Gültige Zweitstimmen": str(sum(stimmen.values())),
    }
    for spalte, anzeigename in sammler.SACHSENANHALT_PARTEISPALTEN.items():
        zeile[spalte] = str(stimmen.get(anzeigename, 0))
    return zeile


print("Sachsen-Anhalt: amtliche Gemeindezeilen")
sachsenanhalt_zeilen = [
    sachsenanhalt_zeile(
        f"15{n:06d}",
        f"Gemeinde {n}",
        {"CDU": 40, "AfD": 30, "SPD": 20, "GRÜNE": 10},
    )
    for n in range(1, 219)
]
sachsenanhalt = sammler.sachsenanhalt_zeilen_auswerten(sachsenanhalt_zeilen)
pruefe(len(sachsenanhalt) == 218, f"alle Gemeinden geparst ({len(sachsenanhalt)})")
pruefe(
    sachsenanhalt["15000001"]["parteien"] == {"CDU": 40.0, "AfD": 30.0, "SPD": 20.0, "GRÜNE": 10.0},
    f"Parteianteile aus Stimmenzahl berechnet ({sachsenanhalt['15000001']['parteien']})",
)


print("Sachsen-Anhalt: andere Satzarten werden ignoriert")
land_zeile = sachsenanhalt_zeile("15000000", "Land Sachsen-Anhalt", {"CDU": 100}, satzart="LAND")
mit_landeszeile = sammler.sachsenanhalt_zeilen_auswerten([*sachsenanhalt_zeilen, land_zeile])
pruefe(len(mit_landeszeile) == 218, f"nur GEM-Zeilen geparst ({len(mit_landeszeile)})")
pruefe("15000000" not in mit_landeszeile, "Land-Summenzeile nicht als Gemeinde übernommen")


print("Sachsen-Anhalt: ungültiger oder fehlender AGS schlägt fehl")
ohne_ags = sachsenanhalt_zeile("15000001", "Ohne AGS", {"CDU": 100})
ohne_ags.pop("Schlüsselnummer")
ungueltige_ags_scheitern = True
for zeile in (
    ohne_ags,
    sachsenanhalt_zeile("1500001", "Zu kurz", {"CDU": 100}),
    sachsenanhalt_zeile("14000001", "Falsches Land", {"CDU": 100}),
):
    try:
        sammler._sachsenanhalt_gebiet(zeile)
        ungueltige_ags_scheitern = False
    except Fehler:
        pass
pruefe(ungueltige_ags_scheitern, "fehlender, zu kurzer und landesfremder AGS schlagen kontrolliert fehl")


print("Sachsen-Anhalt: widersprüchliche Stimmensumme schlägt fehl")
sachsenanhalt_kaputt = sachsenanhalt_zeile("15000001", "Kaputt", {"CDU": 40})
sachsenanhalt_kaputt["F - Gültige Zweitstimmen"] = "999"
try:
    sammler._sachsenanhalt_gebiet(sachsenanhalt_kaputt)
    sachsenanhalt_summenfehler_scheitert = False
except Fehler:
    sachsenanhalt_summenfehler_scheitert = True
pruefe(
    sachsenanhalt_summenfehler_scheitert,
    "Stimmensumme ungleich gültigen Zweitstimmen schlägt kontrolliert fehl",
)


print("Sachsen-Anhalt: Wahlbeteiligung")
_, beteiligung_plausibel = sammler._sachsenanhalt_gebiet(
    sachsenanhalt_zeile("15000001", "Plausibel", {"CDU": 100}, wahlberechtigte=1000, waehler=873)
)
_, beteiligung_unplausibel = sammler._sachsenanhalt_gebiet(
    sachsenanhalt_zeile("15000002", "Unplausibel", {"CDU": 100}, wahlberechtigte=1000, waehler=1001)
)
pruefe(beteiligung_plausibel["beteiligung"] == 87.3, "Beteiligung aus Wahlberechtigten und Wählern berechnet")
pruefe(beteiligung_unplausibel["beteiligung"] is None, "über 100 Prozent wird verworfen")


print("Sachsen-Anhalt: zu wenige Gemeindezeilen schlagen fehl")
try:
    sammler.sachsenanhalt_zeilen_auswerten(sachsenanhalt_zeilen[:5])
    sachsenanhalt_unvollstaendig_scheitert = False
except Fehler:
    sachsenanhalt_unvollstaendig_scheitert = True
pruefe(sachsenanhalt_unvollstaendig_scheitert, "unvollständiger Gemeindeexport schlägt kontrolliert fehl")


BERLIN_TEST_PARTEISPALTEN = {
    "S": "SPD",
    "T": "CDU",
    "U": "GRUENE",
    "V": "AfD",
    "W": "LINKE",
    "X": "FDP",
    "Y": "Tierschutzpartei",
    "Z": "dieBasis",
    "AA": "Volt",
    "AB": "Sonstige",
}
BERLIN_KOPF = {
    "C": "Bezirksnummer",
    "Q": "Gültige Stimmen",
    **BERLIN_TEST_PARTEISPALTEN,
}


def berlin_zeile(
    bezirksnummer,
    name,
    urne_stimmen,
    brief_stimmen,
    wahlberechtigte=1000,
    urnen_waehlende=600,
    brief_waehlende=273,
):
    def rohzeile(art, stimmen, berechtigte, waehlende):
        zeile = {
            "C": bezirksnummer,
            "D": name,
            "F": art,
            "K": str(berechtigte),
            "O": str(waehlende),
            "Q": str(sum(stimmen.values())),
        }
        for spalte, anzeigename in BERLIN_TEST_PARTEISPALTEN.items():
            zeile[spalte] = str(stimmen.get(anzeigename, 0))
        return zeile

    return [
        rohzeile("W", urne_stimmen, wahlberechtigte, urnen_waehlende),
        rohzeile("B", brief_stimmen, 0, brief_waehlende),
    ]


print("Berlin: amtliche Urnen- und Briefwahlbezirkszeilen")
berlin_zeilen = [BERLIN_KOPF]
for n in range(1, 13):
    berlin_zeilen.extend(
        berlin_zeile(f"{n:02d}", f"Bezirk {n}", {"SPD": 40, "CDU": 30}, {"SPD": 10, "CDU": 20})
    )
berlin = sammler.berlin_zeilen_auswerten(berlin_zeilen)
erwartete_ags = {f"110{n:02d}000" for n in range(1, 13)}
pruefe(set(berlin) == erwartete_ags, f"alle zwölf Bezirke mit korrektem AGS geparst ({set(berlin)})")
pruefe(
    berlin["11001000"]["parteien"] == {"SPD": 50.0, "CDU": 50.0},
    f"Parteianteile aus Urnen- und Briefwahl summiert ({berlin['11001000']['parteien']})",
)


print("Berlin: ungültige oder fehlende Bezirksnummern werden ignoriert")
ungueltige_berlin_zeilen = berlin_zeile("1", "Zu kurz", {"SPD": 1}, {"CDU": 1})
fehlende_berlin_zeilen = berlin_zeile("01", "Ohne Nummer", {"SPD": 1}, {"CDU": 1})
for zeile in fehlende_berlin_zeilen:
    zeile.pop("C")
berlin_mit_ungueltigen = sammler.berlin_zeilen_auswerten(
    [*berlin_zeilen, *ungueltige_berlin_zeilen, *fehlende_berlin_zeilen]
)
pruefe(set(berlin_mit_ungueltigen) == erwartete_ags, "ungültige Bezirkszeilen erzeugen kein Gebiet")


print("Berlin: zu wenige Bezirke schlagen fehl")
try:
    sammler.berlin_zeilen_auswerten([BERLIN_KOPF, *berlin_zeilen[1:11]])
    berlin_unvollstaendig_scheitert = False
except Fehler:
    berlin_unvollstaendig_scheitert = True
pruefe(berlin_unvollstaendig_scheitert, "unvollständiger Bezirksexport schlägt kontrolliert fehl")


print("Berlin: widersprüchliche Stimmensumme schlägt fehl")
berlin_kaputt = berlin_zeile("01", "Kaputt", {"SPD": 40}, {"CDU": 20})
berlin_kaputt[1]["Q"] = "999"
try:
    sammler._berlin_gebiet("01", "Kaputt", berlin_kaputt, BERLIN_TEST_PARTEISPALTEN)
    berlin_summenfehler_scheitert = False
except Fehler:
    berlin_summenfehler_scheitert = True
pruefe(
    berlin_summenfehler_scheitert,
    "Stimmensumme ungleich gültigen Zweitstimmen schlägt kontrolliert fehl",
)


print("Berlin: Wahlbeteiligung aus Urnen- und Briefwahl")
berlin_beteiligung = sammler._berlin_gebiet(
    "01",
    "Mitte",
    berlin_zeile("01", "Mitte", {"SPD": 60}, {"CDU": 40}),
    BERLIN_TEST_PARTEISPALTEN,
)
pruefe(berlin_beteiligung["beteiligung"] == 87.3, "Wahlbeteiligung aus W- und B-Zeilen summiert")


print("Berlin: Parteispalten werden dynamisch aus der Kopfzeile gelesen")
berlin_parteispalten = sammler._berlin_parteispalten(
    {"A": "Metadaten", "R": "Metadaten", "S": " SPD ", "T": "", "AA": "Volt"}
)
pruefe(berlin_parteispalten == {"S": "SPD", "AA": "Volt"}, "nur nicht-leere Parteispalten ab S erkannt")


def mecklenburg_zeile(
    ausgabe,
    kreis,
    kreisname,
    amt,
    amtsname,
    gemeinde,
    gemeindename,
    stimmen,
    wahlberechtigte=1000,
    waehler=700,
    erst_zweit=None,
):
    zeile = {
        "Berechnungsdatum": "01.01.2026",
        "Ausgabe": ausgabe,
        "Kreis": kreis,
        "Kreisname": kreisname,
        "Amt": amt,
        "Amtsname": amtsname,
        "Gemeinde": gemeinde,
        "Gemeindename": gemeindename,
        "Wahlbezirke insg.": "1",
        "Erf. Wahlbezirke": "1",
        "Wahlberechtigte": str(wahlberechtigte),
        "Wähler": str(waehler),
        "Wahlbeteiligung": "70,0",
        "Ungültige Stimmen": "0",
        "Gültige Stimmen": str(sum(v for v in stimmen.values() if isinstance(v, int))),
        **{k: (v if isinstance(v, str) else str(v)) for k, v in stimmen.items()},
    }
    if erst_zweit is not None:
        zeile["Erst-/Zweitstimme"] = erst_zweit
    return zeile


# Der Sammler erwartet 650 bis 800 Gemeindezeilen (echte Werte: 717 Landtag 2021, 724 Kommunal
# 2024) - eine feste Anzahl generischer Füllgemeinden (eigenes Amt je Gemeinde, keine
# Briefwahl-Pseudozeile, also kein hinweis) simuliert einen vollständigen Export, dazwischen ein
# paar konkrete Gemeinden für die eigentlichen Prüfungen.
def mv_fuellgemeinden(anzahl, erst_zweit=None):
    return [
        mecklenburg_zeile(
            "A", "71", "Mecklenburgische Seenplatte", str(n), f"Amt {n}",
            f"13{n:06d}", f"Gemeinde {n}",
            {"CDU": 40, "SPD": 30, "AfD": 20, "GRÜNE": 5, "FDP": 5},
            erst_zweit=erst_zweit,
        )
        for n in range(1, anzahl + 1)
    ]


print("Mecklenburg-Vorpommern: Landtagswahl-Gemeindezeilen, Ausgabe=A und Erst-/Zweitstimme=2")
mv_landtag_zeilen = [
    *mv_fuellgemeinden(699, erst_zweit="2"),
    mecklenburg_zeile("A", "71", "Mecklenburgische Seenplatte", "800", "Amt Amtsfrei", "13071001", "Amtsfrei", {"CDU": 40, "SPD": 30, "AfD": 30}, erst_zweit="2"),
    mecklenburg_zeile("P", "71", "Mecklenburgische Seenplatte", "800", "Amt Amtsfrei", "13071001", "Amtsfrei", {"CDU": 999, "SPD": 999, "AfD": 999}, erst_zweit="2"),
    mecklenburg_zeile("A", "71", "Mecklenburgische Seenplatte", "800", "Amt Amtsfrei", "13071001", "Amtsfrei", {"CDU": 1, "SPD": 1, "AfD": 1}, erst_zweit="1"),
    mecklenburg_zeile("A", "71", "Mecklenburgische Seenplatte", "51", "Demmin-Land", "13071002", "Angehoerig", {"CDU": 50, "SPD": 50, "AfD": "x"}, erst_zweit="2"),
    mecklenburg_zeile("A", "71", "Mecklenburgische Seenplatte", "51", "Demmin-Land", "13071751", "Briefwahl Demmin-Land", {"CDU": 5, "SPD": 5, "AfD": "x"}, erst_zweit="2"),
]
mv_landtag = sammler.mecklenburg_landtag_zeilen_auswerten(mv_landtag_zeilen)
pruefe(len(mv_landtag) == 701, f"nur echte Gemeinden, keine Briefwahl-Pseudozeile ({len(mv_landtag)})")
pruefe(
    mv_landtag["13071001"]["parteien"] == {"CDU": 40.0, "SPD": 30.0, "AfD": 30.0},
    f"nur Ausgabe=A und Erst-/Zweitstimme=2 verwendet ({mv_landtag['13071001']['parteien']})",
)
pruefe("hinweis" not in mv_landtag["13071001"], "amtsfreie Gemeinde ohne Briefwahl-Lücke bekommt keinen hinweis")
pruefe(
    mv_landtag["13071002"]["parteien"] == {"CDU": 50.0, "SPD": 50.0},
    f"'x' in Parteispalte übersprungen statt als 0 gewertet oder Fehler ({mv_landtag['13071002']['parteien']})",
)
pruefe("hinweis" in mv_landtag["13071002"], "amtsangehörige Gemeinde mit passender Briefwahl-Zeile bekommt hinweis")


print("Mecklenburg-Vorpommern: ungültiger AGS schlägt fehl")
kaputte_ags_zeile = mecklenburg_zeile("A", "71", "MSE", "1", "Amt", "1307100", "Zu kurz", {"CDU": 100}, erst_zweit="2")
try:
    sammler.mecklenburg_landtag_zeilen_auswerten([*mv_landtag_zeilen, kaputte_ags_zeile])
    mv_ags_scheitert = False
except Fehler:
    mv_ags_scheitert = True
pruefe(mv_ags_scheitert, "zu kurzer/ungültiger Gemeinde-AGS schlägt kontrolliert fehl")


print("Mecklenburg-Vorpommern: Kommunalwahl-Gemeindezeilen (keine Erst-/Zweitstimme-Spalte)")
mv_kommunal_zeilen = [
    *mv_fuellgemeinden(700),
    mecklenburg_zeile("A", "3", "Rostock", "1", "Rostock", "13003000", "Rostock", {"CDU": 60, "SPD": 40}),
    mecklenburg_zeile("A", "71", "Mecklenburgische Seenplatte", "51", "Demmin-Land", "13071002", "Angehoerig", {"CDU": 50, "SPD": 50}),
]
mv_kommunal = sammler.mecklenburg_kommunal_zeilen_auswerten(mv_kommunal_zeilen)
pruefe(len(mv_kommunal) == 702, f"alle Gemeinden geparst ({len(mv_kommunal)})")
pruefe("hinweis" not in mv_kommunal["13003000"], "Gemeinde ohne passende Briefwahl-Zeile bekommt keinen hinweis")
pruefe("hinweis" not in mv_kommunal["13071002"], "ohne eigene Briefwahl-Pseudozeile in dieser Zeilenliste kein hinweis")


print("Mecklenburg-Vorpommern: Kreistagswahl (Kreisebene, Kreis 99 wird übersprungen)")
MV_KREISTAG_STANDARD = {"CDU": 30, "SPD": 30, "AfD": 20, "GRÜNE": 10, "FDP": 10}
mv_kreistag_zeilen = [
    mecklenburg_zeile("A", "3", "Rostock, Hansestadt", "", "", "", "", {"CDU": 60, "SPD": 20, "AfD": 10, "GRÜNE": 5, "FDP": 5}),
    mecklenburg_zeile("A", "4", "Schwerin", "", "", "", "", MV_KREISTAG_STANDARD),
    mecklenburg_zeile("A", "71", "Mecklenburgische Seenplatte", "", "", "", "", MV_KREISTAG_STANDARD),
    mecklenburg_zeile("A", "72", "Landkreis Rostock", "", "", "", "", MV_KREISTAG_STANDARD),
    mecklenburg_zeile("A", "73", "Vorpommern-Rügen", "", "", "", "", MV_KREISTAG_STANDARD),
    mecklenburg_zeile("A", "74", "Nordwestmecklenburg", "", "", "", "", MV_KREISTAG_STANDARD),
    mecklenburg_zeile("A", "75", "Vorpommern-Greifswald", "", "", "", "", MV_KREISTAG_STANDARD),
    mecklenburg_zeile("A", "76", "Ludwigslust-Parchim", "", "", "", "", MV_KREISTAG_STANDARD),
    mecklenburg_zeile("A", "99", "Mecklenburg-Vorpommern", "", "", "", "", MV_KREISTAG_STANDARD),
]
mv_kreistag = sammler.mecklenburg_kreistag_zeilen_auswerten(mv_kreistag_zeilen)
pruefe(len(mv_kreistag) == 8, f"8 Kreise/kreisfreie Städte, Kreis 99 übersprungen ({len(mv_kreistag)})")
pruefe(
    mv_kreistag["13003"]["parteien"] == {"CDU": 60.0, "SPD": 20.0, "AfD": 10.0, "GRÜNE": 5.0, "FDP": 5.0},
    f"Kreisschlüssel aus zweistelligem Kreiscode zusammengesetzt ({mv_kreistag.get('13003')})",
)
pruefe("13099" not in mv_kreistag, "Landesergebnis (Kreis 99) ist kein Gebiet")


def bayern_wahlvorschlag_xml(name, stimmen=None):
    """stimmen=None simuliert eine Liste, die 2026 nicht mehr angetreten ist (nur Verlaufszeile,
    kein Gewichtete_Stimmen_absolut-Element - siehe _bayern_wahlvorschlag_stimmen)."""
    if stimmen is None:
        return f"<Wahlvorschlag><Bezeichnung>{name}</Bezeichnung><Veraenderung_Sitze>-1</Veraenderung_Sitze></Wahlvorschlag>"
    return (
        f"<Wahlvorschlag><Bezeichnung>{name}</Bezeichnung>"
        f"<Gewichtete_Stimmen_absolut>{stimmen}</Gewichtete_Stimmen_absolut></Wahlvorschlag>"
    )


def bayern_regionaleinheit_xml(schluessel, name, stimmberechtigte, waehler, parteien):
    gesamt = sum(v for v in parteien.values() if v is not None)
    vorschlaege = "".join(bayern_wahlvorschlag_xml(p, v) for p, v in parteien.items())
    return f"""<Regionaleinheit Schluesselnummer="{schluessel}">
<Wahl Bezeichnung="Kreistag">
<Allgemeine_Angaben><Name_der_Regionaleinheit>{name}</Name_der_Regionaleinheit>
<Stimmberechtigte>{stimmberechtigte}</Stimmberechtigte><Waehler>{waehler}</Waehler></Allgemeine_Angaben>
<Stimmenergebnis><Wahlvorschlaege_zusammen><Gewichtete_Stimmen>{gesamt}</Gewichtete_Stimmen></Wahlvorschlaege_zusammen>
{vorschlaege}
</Stimmenergebnis></Wahl></Regionaleinheit>"""


def bayern_fuellkreise(anzahl, start=1):
    return [
        bayern_regionaleinheit_xml(str(900 + n), f"Füllkreis {n}", 1000, 600, {"CSU": 400, "SPD": 200})
        for n in range(start, start + anzahl)
    ]


print("Bayern: Kreistagswahl-XML, echte Wählergruppen bleiben erhalten, nicht angetretene Liste zählt als 0")
bayern_einheiten = [
    *bayern_fuellkreise(70),
    bayern_regionaleinheit_xml(
        "171", "Altötting", 88740, 51941,
        {"CSU": 19483, "AfD": 7332, "SPD": 6600, "Bürgerliste Reichenhall": 5200, "FDP": None},
    ),
]
bayern_xml = "<?xml version='1.0' encoding='UTF-8'?><Ergebnisse>" + "".join(bayern_einheiten) + "</Ergebnisse>"
with tempfile.TemporaryDirectory(prefix="plakat-test-") as ordner:
    datei = Path(ordner) / "landkreise.xml"
    datei.write_text(bayern_xml, encoding="utf-8")
    bayern_kreistag = sammler.bayern_kreistag_xml_auswerten(datei)
pruefe(len(bayern_kreistag) == 71, f"71 Landkreise erwartet ({len(bayern_kreistag)})")
pruefe(
    "Bürgerliste Reichenhall" in bayern_kreistag["09171"]["parteien"],
    "echte örtliche Wählergruppe bleibt unter ihrem Namen erhalten",
)
pruefe(
    "FDP" not in bayern_kreistag["09171"]["parteien"],
    "nicht mehr angetretene Liste ohne Gewichtete_Stimmen_absolut wird als 0 gewertet, nicht als Fehler",
)
pruefe(
    bayern_kreistag["09171"]["beteiligung"] == round(51941 / 88740 * 100, 1),
    f"Wahlbeteiligung aus Wähler/Stimmberechtigte berechnet ({bayern_kreistag['09171']['beteiligung']})",
)


print("Bayern: falsche Anzahl Landkreise schlägt fehl")
bayern_zu_wenig_xml = "<?xml version='1.0' encoding='UTF-8'?><Ergebnisse>" + "".join(bayern_fuellkreise(70)) + "</Ergebnisse>"
with tempfile.TemporaryDirectory(prefix="plakat-test-") as ordner:
    datei = Path(ordner) / "landkreise.xml"
    datei.write_text(bayern_zu_wenig_xml, encoding="utf-8")
    try:
        sammler.bayern_kreistag_xml_auswerten(datei)
        bayern_anzahl_scheitert = False
    except Fehler:
        bayern_anzahl_scheitert = True
pruefe(bayern_anzahl_scheitert, "70 statt 71 Landkreise schlägt kontrolliert fehl")


# Brandenburg liefert die Gemeindevertretungswahl im Langformat: eine Zeile je Gemeinde UND
# Wahlvorschlag (Spalte F = Art des Wahlvorschlags), Kennzahlen wie "Wahlberechtigt" oder "Gültig"
# stehen als eigene Pseudo-Zeilen ohne gesetztes F. brandenburg_zeile baut genau eine solche Zeile.
def brandenburg_zeile(kreis, gemeinde, gemeindename, art, kurzname, anzahl):
    return {
        "C": kreis, "D": gemeinde, "E": gemeindename,
        "F": art, "G": kurzname, "I": str(anzahl),
    }


def brandenburg_kennzahl(kreis, gemeinde, gemeindename, bezeichnung, anzahl):
    return {"C": kreis, "D": gemeinde, "E": gemeindename, "G": bezeichnung, "I": str(anzahl)}


def brandenburg_gemeinde_zeilen(kreis, gemeinde, gemeindename, wahlberechtigt, waehler, stimmen):
    gueltig = sum(stimmen.values())
    zeilen = [
        brandenburg_kennzahl(kreis, gemeinde, gemeindename, "Wahlberechtigt", wahlberechtigt),
        brandenburg_kennzahl(kreis, gemeinde, gemeindename, "Wähler", waehler),
        brandenburg_kennzahl(kreis, gemeinde, gemeindename, "Gültig", gueltig),
    ]
    for typ, kurzname, anzahl in stimmen_mit_typ(stimmen):
        zeilen.append(brandenburg_zeile(kreis, gemeinde, gemeindename, typ, kurzname, anzahl))
    return zeilen


def stimmen_mit_typ(stimmen):
    """stimmen ist ein dict Kurzname -> Anzahl; Typ ist für den Parser irrelevant (nur ob F gesetzt ist)."""
    return [("P", kurzname, anzahl) for kurzname, anzahl in stimmen.items()]


def bb_fuellgemeinden(anzahl, start_kreis="01"):
    zeilen = []
    for n in range(1, anzahl + 1):
        zeilen += brandenburg_gemeinde_zeilen(
            str(start_kreis), f"{n:03d}", f"Füllgemeinde {n}", 1000, 500,
            {"CDU": 250, "SPD": 150, "AfD": 100},
        )
    return zeilen


print("Brandenburg: Gemeindevertretungswahl-Langformat, echte Wählergruppen/Einzelbewerber bleiben erhalten")
bb_zeilen = [
    {"A": "Stimmart", "B": "ARS", "C": "Landkreis-\nnummer", "D": "Gemeinde-\nnummer", "E": "Gemeindename"},  # Kopfzeile
    *bb_fuellgemeinden(410, start_kreis="60"),
    *brandenburg_gemeinde_zeilen(
        "51", "000", "Brandenburg an der Havel, Stadt", 871, 426,
        {
            "CDU": 55, "SPD": 162, "AfD": 85, "GRÜNE/B 90": 36, "DIE LINKE": 15,
            "BVB / FREIE WÄHLER": 3, "FDP": 3,
            "Bürger für Frieden, Vernunft und Gerechtigkeit": 51,
            "EB Wenzel": 13,
        },
    ),
]
bb_gvw = sammler.brandenburg_gvw_zeilen_auswerten(bb_zeilen)
pruefe(len(bb_gvw) == 411, f"Kopfzeile übersprungen, alle Gemeinden geparst ({len(bb_gvw)})")
pruefe(
    "Bürger für Frieden, Vernunft und Gerechtigkeit" in bb_gvw["12051000"]["parteien"],
    "echte örtliche Wählergruppe bleibt unter ihrem Namen erhalten statt Sonstige",
)
pruefe(
    "EB Wenzel" in bb_gvw["12051000"]["parteien"],
    "echter Einzelbewerber bleibt unter seinem Namen erhalten",
)
pruefe(
    bb_gvw["12051000"]["beteiligung"] == round(426 / 871 * 100, 1),
    f"Wahlbeteiligung aus Wähler/Wahlberechtigt berechnet ({bb_gvw['12051000']['beteiligung']})",
)
pruefe(bb_gvw["12060001"]["parteien"] == {"CDU": 50.0, "SPD": 30.0, "AfD": 20.0}, "Füllgemeinde korrekt aufgeschlüsselt")


print("Brandenburg: Stimmensumme ungleich gemeldeter gültiger Stimmen schlägt fehl")
bb_kaputt = [
    *bb_fuellgemeinden(410, start_kreis="61"),
    brandenburg_kennzahl("51", "000", "Kaputt", "Wahlberechtigt", 100),
    brandenburg_kennzahl("51", "000", "Kaputt", "Wähler", 50),
    brandenburg_kennzahl("51", "000", "Kaputt", "Gültig", 999),
    brandenburg_zeile("51", "000", "Kaputt", "P", "CDU", 10),
]
try:
    sammler.brandenburg_gvw_zeilen_auswerten(bb_kaputt)
    bb_summe_scheitert = False
except Fehler:
    bb_summe_scheitert = True
pruefe(bb_summe_scheitert, "Stimmensumme ungleich Gültig schlägt kontrolliert fehl")


SAARLAND_TEST_PARTEIEN = ["CDU", "SPD", "AfD", "GRÜNE", "bunt.saar \x96 sozial-ökologische liste"]


def saarland_kopf(parteien=SAARLAND_TEST_PARTEIEN):
    zeile = ["Nr", "Gebiet", "gehört zu"]
    for partei in parteien:
        zeile += [partei, ""]
    zeile += [
        "Wahlberechtigte", "",
        "Wähler", "",
        "Ungültige Stimmen", "",
        "Gültige Stimmen", "",
        "Übrige", "",
    ]
    return zeile


def saarland_zeile(nr, name, stimmen, parteien=SAARLAND_TEST_PARTEIEN, wahlberechtigte=1000, waehler=700, gehoert_zu="1"):
    gueltig = sum(stimmen.values())
    zeile = [nr, name, gehoert_zu]
    for partei in parteien:
        zeile += [str(stimmen.get(partei, 0)), ""]
    zeile += [str(wahlberechtigte), "", str(waehler), "", str(waehler - gueltig), "", str(gueltig), "", "", ""]
    return zeile


print("Saarland: amtliche Gemeindezeilen")
saarland_gemeinden = [
    saarland_zeile(f"4{n:04d}", f"Gemeinde {n}", {"CDU": 40, "SPD": 30, "AfD": 20, "GRÜNE": 10})
    for n in range(1000, 1052)
]
saarland_wahlkreis_zeile = saarland_zeile("1", "Wahlkreis Saarbrücken", {"CDU": 40 * 52, "SPD": 30 * 52, "AfD": 20 * 52, "GRÜNE": 10 * 52}, wahlberechtigte=52000, waehler=36400, gehoert_zu="10")
saarland_land_zeile = saarland_zeile("10", "Saarland", {"CDU": 40 * 52, "SPD": 30 * 52, "AfD": 20 * 52, "GRÜNE": 10 * 52}, wahlberechtigte=52000, waehler=36400, gehoert_zu="")
saarland_zeilen = [saarland_kopf(), *saarland_gemeinden, saarland_wahlkreis_zeile, saarland_land_zeile]
saarland = sammler.saarland_landtag_zeilen_auswerten(saarland_zeilen)
pruefe(len(saarland) == 52, f"alle Gemeinden geparst, Wahlkreis-/Landeszeile übersprungen ({len(saarland)})")
pruefe("10041000" in saarland, "Nr zu achtstelligem AGS mit '100'-Vorsatz zusammengesetzt")
pruefe(
    saarland["10041000"]["parteien"] == {"CDU": 40.0, "SPD": 30.0, "AfD": 20.0, "GRÜNE": 10.0},
    f"Parteianteile aus Stimmenzahl berechnet ({saarland['10041000']['parteien']})",
)
pruefe(saarland["10041000"]["beteiligung"] == 70.0, "Beteiligung aus Wahlberechtigten und Wählern berechnet")


print("Saarland: bundesweite Parteien auf Kurzname abgebildet, unbekannte Namen bleiben unverändert")
SAARLAND_LANGNAMEN_TEST = [
    "Sozialdemokratische Partei Deutschlands",
    "Christlich Demokratische Union Deutschlands",
    "Alternative für Deutschland",
    "BÜNDNIS 90/DIE GRÜNEN",
    "bunt.saar sozial-ökologische liste",
]
_, saarland_lang_spalten, lang_wber_idx, lang_waehler_idx, lang_gueltig_idx = sammler._saarland_kopf(
    [saarland_kopf(SAARLAND_LANGNAMEN_TEST)]
)
_, saarland_lang_gebiet = sammler._saarland_gebiet(
    saarland_zeile(
        "41000",
        "Kurznamen",
        {
            "Sozialdemokratische Partei Deutschlands": 40,
            "Christlich Demokratische Union Deutschlands": 30,
            "Alternative für Deutschland": 20,
            "BÜNDNIS 90/DIE GRÜNEN": 5,
            "bunt.saar sozial-ökologische liste": 5,
        },
        parteien=SAARLAND_LANGNAMEN_TEST,
    ),
    saarland_lang_spalten,
    lang_wber_idx,
    lang_waehler_idx,
    lang_gueltig_idx,
)
pruefe(
    saarland_lang_gebiet["parteien"]
    == {"SPD": 40.0, "CDU": 30.0, "AfD": 20.0, "GRÜNE": 5.0, "bunt.saar sozial-ökologische liste": 5.0},
    f"bekannte Langnamen zu Kurzname, unbekannter Name unverändert ({saarland_lang_gebiet['parteien']})",
)


print("Saarland: C1-Steuerzeichen in Parteinamen geglättet")
_, sonderzeichen_parteispalten, sz_wber_idx, sz_waehler_idx, sz_gueltig_idx = sammler._saarland_kopf([saarland_kopf()])
_, saarland_sonderzeichen_gebiet = sammler._saarland_gebiet(
    saarland_zeile("41000", "Sonderzeichen", {"CDU": 60, "bunt.saar \x96 sozial-ökologische liste": 40}),
    sonderzeichen_parteispalten, sz_wber_idx, sz_waehler_idx, sz_gueltig_idx,
)
pruefe(
    "bunt.saar - sozial-ökologische liste" in saarland_sonderzeichen_gebiet["parteien"],
    f"Steuerzeichen durch Bindestrich ersetzt ({list(saarland_sonderzeichen_gebiet['parteien'])})",
)


print("Saarland: ungültiger Gemeinde-AGS schlägt fehl")
kopf_index, parteispalten, wber_idx, waehler_idx, gueltig_idx = sammler._saarland_kopf([saarland_kopf()])
try:
    sammler._saarland_gebiet(
        saarland_zeile("4100", "Zu kurz", {"CDU": 100}), parteispalten, wber_idx, waehler_idx, gueltig_idx
    )
    saarland_ags_scheitert = False
except Fehler:
    saarland_ags_scheitert = True
pruefe(saarland_ags_scheitert, "zu kurzer Gemeinde-Schlüssel schlägt kontrolliert fehl")


print("Saarland: widersprüchliche Stimmensumme schlägt fehl")
saarland_kaputt = saarland_zeile("41000", "Kaputt", {"CDU": 40})
saarland_kaputt[gueltig_idx] = "999"
try:
    sammler._saarland_gebiet(saarland_kaputt, parteispalten, wber_idx, waehler_idx, gueltig_idx)
    saarland_summenfehler_scheitert = False
except Fehler:
    saarland_summenfehler_scheitert = True
pruefe(saarland_summenfehler_scheitert, "Stimmensumme ungleich gültigen Stimmen schlägt kontrolliert fehl")


print("Saarland: zu wenige Gemeindezeilen schlagen fehl")
try:
    sammler.saarland_landtag_zeilen_auswerten([saarland_kopf(), *saarland_gemeinden[:5]])
    saarland_unvollstaendig_scheitert = False
except Fehler:
    saarland_unvollstaendig_scheitert = True
pruefe(saarland_unvollstaendig_scheitert, "unvollständiger Gemeindeexport schlägt kontrolliert fehl")


def schleswig_holstein_zeile(
    kennziffer, kreisname, gemeindename, amtsschluessel, amtername, parteien,
    wahlberechtigte=1000, waehler=700,
):
    gueltig = sum(parteien.values())
    zeile = {
        "A": kennziffer, "B": kreisname, "C": gemeindename, "D": "Testwahlbezirk",
        "E": amtsschluessel, "F": amtername,
        "N": str(wahlberechtigte), "R": str(waehler), "AM": str(gueltig),
    }
    for spalte, (_, anzeigename) in sammler.SCHLESWIG_HOLSTEIN_PARTEISPALTEN.items():
        zeile[spalte] = str(parteien.get(anzeigename, 0))
    return zeile


# Der Sammler erwartet 2.000 bis 2.800 reguläre Wahlbezirkszeilen; feste Füllgemeinden (ein
# Wahlbezirk je Gemeinde, kein Amt, also kein hinweis) simulieren einen vollständigen Export. Die
# Gemeindenummer ist Teil der Kennziffer (Stelle 3-5) und muss wie im Original mit "0" oder "1"
# beginnen, sonst würde sie fälschlich als Briefwahl-Pseudozeile ("9") oder gar nicht erkannt.
# Nummern unter 030 bleiben in jedem Kreis für die gezielten Prüfungen unten frei; Kreis 59
# (Schleswig-Flensburg) bleibt komplett frei für den Zusammenlegungs-Testfall.
def sh_fuellgemeinden(anzahl):
    kreise = ("51", "53", "54", "55", "56", "57", "58", "60", "61", "62", "01", "02", "03", "04")
    zeilen = []
    for kreis_nr in kreise:
        for gemeinde_nr in range(30, 200):
            if len(zeilen) >= anzahl:
                return zeilen
            zeilen.append(schleswig_holstein_zeile(
                f"{kreis_nr}{gemeinde_nr:03d}001",
                sammler.SCHLESWIG_HOLSTEIN_KREISE[kreis_nr],
                f"Füllgemeinde {kreis_nr}-{gemeinde_nr}", "", "",
                {"CDU": 40, "SPD": 30, "AfD": 20, "GRÜNE": 10},
            ))
    return zeilen


# Maasbüll, Tastrup und Ülsby (siehe SCHLESWIG_HOLSTEIN_ZUSAMMENGELEGT) müssen in jedem Aufruf von
# schleswig_holstein_landtag_zeilen_auswerten vorkommen, sonst schlägt die Zusammenlegung selbst
# fehl (bewusst so wie Sachsens SACHSEN_NUR_TEILGEMEINDEN) - als gemeinsame Grundlage einmal
# gebaut und in jede Testzeilenliste unten übernommen.
sh_zusammenlegung_basis = [
    schleswig_holstein_zeile("59141001", "Schleswig-Flensburg", "Maasbüll-Test", "19", "Testamt Hürup", {"CDU": 30, "SPD": 20}, wahlberechtigte=200, waehler=100),
    schleswig_holstein_zeile("59101001", "Schleswig-Flensburg", "Tastrup-Test", "19", "Testamt Hürup", {"CDU": 20, "SPD": 10}, wahlberechtigte=100, waehler=60),
    schleswig_holstein_zeile("59093001", "Schleswig-Flensburg", "Ülsby-Test", "87", "Testamt Südangeln", {"CDU": 10, "SPD": 10}, wahlberechtigte=80, waehler=40),
]

sh_normalfall_zeilen = [
    schleswig_holstein_zeile("51010001", "Dithmarschen", "Testgemeinde Normal", "", "", {"CDU": 40, "SPD": 30, "AfD": 20, "GRÜNE": 9, "Zentrum": 1}, wahlberechtigte=600, waehler=400),
    schleswig_holstein_zeile("51010002", "Dithmarschen", "Testgemeinde Normal", "", "", {"CDU": 40, "SPD": 30, "AfD": 20, "GRÜNE": 9, "Zentrum": 1}, wahlberechtigte=600, waehler=400),
]
sh_direkte_briefwahl_zeilen = [
    schleswig_holstein_zeile("51011001", "Dithmarschen", "Testgemeinde Brief", "10", "Testamt Ohne Pool", {"CDU": 50, "SPD": 50}, wahlberechtigte=500, waehler=300),
    # Kennziffer-Stelle 3 = "9", aber Gemeindename gesetzt: direkt attribuierte Briefwahl, zählt mit.
    schleswig_holstein_zeile("51911001", "Dithmarschen", "Testgemeinde Brief", "10", "Testamt Ohne Pool", {"CDU": 10, "SPD": 10}, wahlberechtigte=0, waehler=20),
]
sh_gepoolte_briefwahl_zeilen = [
    schleswig_holstein_zeile("51012001", "Dithmarschen", "Testgemeinde Pool", "20", "Testamt Mit Pool", {"CDU": 30, "SPD": 20}, wahlberechtigte=300, waehler=150),
    # Kennziffer-Stelle 3 = "9" und Gemeindename LEER: Amt-gepoolte Pseudozeile. Absichtlich
    # riesige Stimmenzahlen, damit ein versehentliches Mitzählen sofort auffallen würde.
    schleswig_holstein_zeile("51912002", "Dithmarschen", "", "20", "Testamt Mit Pool", {"CDU": 999, "SPD": 999}, wahlberechtigte=0, waehler=9999),
]

print("Schleswig-Holstein: Wahlbezirke zu Gemeinden aggregiert, AGS aus Kennziffer abgeleitet")
sh_zeilen = [
    *sh_fuellgemeinden(2000),
    *sh_zusammenlegung_basis,
    *sh_normalfall_zeilen,
    *sh_direkte_briefwahl_zeilen,
    *sh_gepoolte_briefwahl_zeilen,
]
sh_landtag = sammler.schleswig_holstein_landtag_zeilen_auswerten(sh_zeilen)
pruefe(
    sh_landtag["01051010"]["parteien"] == {"CDU": 40.0, "SPD": 30.0, "AfD": 20.0, "GRÜNE": 9.0, "Zentrum": 1.0},
    f"zwei Wahlbezirke einer Gemeinde aufsummiert, Spalte 'Z.' als 'Zentrum' angezeigt ({sh_landtag['01051010']['parteien']})",
)
pruefe(sh_landtag["01051010"]["beteiligung"] == 66.7, f"Beteiligung aus summierten Wahlberechtigten/Wählern ({sh_landtag['01051010']['beteiligung']})")
pruefe("hinweis" not in sh_landtag["01051010"], "Gemeinde ohne Amt bekommt keinen Briefwahl-hinweis")

pruefe(
    sh_landtag["01051011"]["parteien"] == {"CDU": 50.0, "SPD": 50.0},
    f"direkt attribuierte Briefwahlzeile zählt mit ({sh_landtag['01051011']['parteien']})",
)
pruefe("hinweis" not in sh_landtag["01051011"], "Amt ohne gepoolte Pseudozeile bekommt keinen hinweis")

pruefe(
    sh_landtag["01051012"]["parteien"] == {"CDU": 60.0, "SPD": 40.0},
    f"Amt-gepoolte Pseudozeile NICHT mitgezählt, nur die eigene Wahlbezirkszeile ({sh_landtag['01051012']['parteien']})",
)
pruefe(sh_landtag["01051012"]["beteiligung"] == 50.0, "Beteiligung ohne die gepoolten 9999 Wähler berechnet")
pruefe(sh_landtag["01051012"].get("hinweis") == sammler.SCHLESWIG_HOLSTEIN_BRIEFWAHL_HINWEIS, "Amt mit gepoolter Briefwahl bekommt den Standard-hinweis")

pruefe("01059141" not in sh_landtag and "01059101" not in sh_landtag, "aufgegangene Maasbüll/Tastrup-AGS verschwinden nach der Zusammenlegung")
uelsby = sh_landtag.get("01059093", {})
pruefe(uelsby.get("name") == "Uelsby", f"zusammengelegte Gemeinde trägt den aktuellen Namen ({uelsby.get('name')})")
pruefe(
    uelsby.get("parteien") == {"CDU": 60.0, "SPD": 40.0},
    f"Rohstimmen aller drei ehemaligen Gemeinden vor der Prozentrechnung summiert ({uelsby.get('parteien')})",
)
pruefe(uelsby.get("beteiligung") == 52.6, f"Beteiligung aus summierten Wahlberechtigten/Wählern aller drei Gemeinden ({uelsby.get('beteiligung')})")
pruefe("Maasbüll" in uelsby.get("hinweis", "") and "gepoolt" in uelsby.get("hinweis", ""), "Zusammenlegungs- und Briefwahl-hinweis kombiniert")


print("Schleswig-Holstein: Kreis-Nummer passt nicht zu Kreisname schlägt fehl")
sh_falscher_kreis = schleswig_holstein_zeile("51013001", "Falscher Kreisname", "Egal", "", "", {"CDU": 100})
try:
    sammler.schleswig_holstein_landtag_zeilen_auswerten([*sh_zeilen, sh_falscher_kreis])
    sh_kreis_scheitert = False
except Fehler:
    sh_kreis_scheitert = True
pruefe(sh_kreis_scheitert, "Kennziffer-Kreisnummer und Kreisname-Spalte widersprechen sich, schlägt kontrolliert fehl")


print("Schleswig-Holstein: widersprüchliche Stimmensumme schlägt fehl")
sh_kaputt = schleswig_holstein_zeile("51014001", "Dithmarschen", "Kaputt", "", "", {"CDU": 40})
sh_kaputt["AM"] = "999"
try:
    sammler.schleswig_holstein_landtag_zeilen_auswerten([*sh_zeilen, sh_kaputt])
    sh_summenfehler_scheitert = False
except Fehler:
    sh_summenfehler_scheitert = True
pruefe(sh_summenfehler_scheitert, "Parteistimmen ungleich gültigen Zweitstimmen schlägt kontrolliert fehl")


print("Schleswig-Holstein: zu wenige Wahlbezirkszeilen schlagen fehl")
try:
    sammler.schleswig_holstein_landtag_zeilen_auswerten([*sh_zusammenlegung_basis, *sh_normalfall_zeilen])
    sh_unvollstaendig_scheitert = False
except Fehler:
    sh_unvollstaendig_scheitert = True
pruefe(sh_unvollstaendig_scheitert, "unvollständiger Wahlbezirksexport schlägt kontrolliert fehl")


# Bund, Länder und Wahlkreise stehen in kerg2 nebeneinander. Wahlkreis 1 darf nicht versehentlich
# das Landesergebnis von Schleswig-Holstein bekommen; außerdem zählt bei der Bundestagswahl nur
# die Zweitstimme.
KERG = """Diese Datei enthält Ergebnisse der Bundestagswahl 2025.
Herausgeberin: Die Bundeswahlleiterin

Wahlart;Wahltag;Gebietsart;Gebietsnummer;Gebietsname;Gruppenart;Gruppenname;Stimme;Anzahl;Prozent
BT;23.02.2025;Land;1;Schleswig-Holstein;System-Gruppe;Wählende;;900000;80,0
BT;23.02.2025;Land;1;Schleswig-Holstein;Partei;CDU;2;300000;99,0
BT;23.02.2025;Wahlkreis;1;Flensburg - Schleswig;System-Gruppe;Wählende;;70000;72,5
BT;23.02.2025;Wahlkreis;1;Flensburg - Schleswig;Partei;CDU;1;30000;11,1
BT;23.02.2025;Wahlkreis;1;Flensburg - Schleswig;Partei;CDU;2;30000;30,0
BT;23.02.2025;Wahlkreis;1;Flensburg - Schleswig;Partei;SPD;2;25000;25,0
BT;23.02.2025;Wahlkreis;1;Flensburg - Schleswig;Partei;AfD;2;20000;20,0
BT;23.02.2025;Wahlkreis;1;Flensburg - Schleswig;Partei;GRÜNE;2;25000;25,0
"""


print("kerg2: Gebietsebene und Zweitstimme")
kerg = kerg2_auswerten(KERG, "Wahlkreis", "2")
pruefe(set(kerg) == {"1"}, f"nur Wahlkreiszeile ({set(kerg)})")
pruefe(kerg["1"]["name"] == "Flensburg - Schleswig", "Gebietsname übernommen")
pruefe(kerg["1"]["beteiligung"] == 72.5, "Wahlkreis- statt Landesbeteiligung")
pruefe(kerg["1"]["parteien"].get("CDU") == 30.0, "Zweit- statt Erststimme")


print("kerg2: führende Null")
europa = KERG.replace("BT;23.02.2025;Wahlkreis;1", "EP;09.06.2024;Kreis;01001").replace(";2;", ";;")
kerg_eu = kerg2_auswerten(europa, "Kreis", None)
pruefe("01001" in kerg_eu, f"Kreisschlüssel bleibt Text ({list(kerg_eu)})")


print("Schreiben nur bei fachlicher Änderung")
with tempfile.TemporaryDirectory(prefix="plakat-test-") as ordner:
    datei = Path(ordner) / "daten.json"
    erstes = sammler.schreiben(datei, {"wert": 1}, jetzt="2026-01-01")
    zweites = sammler.schreiben(datei, {"wert": 1}, jetzt="2026-02-01")
    stand = json.loads(datei.read_text(encoding="utf-8"))["stand"]
pruefe(erstes and not zweites, "identische Daten erzeugen keinen neuen Stand")
pruefe(stand == "2026-01-01", f"ursprünglicher Stand bleibt erhalten ({stand})")


print("Landesordner und flache Kompatibilitätsdatei")
with tempfile.TemporaryDirectory(prefix="plakat-test-") as ordner:
    basis = Path(ordner)
    pfade = (basis / "14" / "kommunal.json", basis / "kommunal-14.json")
    inhalt = {"land": "14", "jahr": 2024, "gebiete": {"14730110": {"name": "Eilenburg"}}}
    erstes = sammler._mehrfach_schreiben(pfade, inhalt)
    zweites = sammler._mehrfach_schreiben(pfade, inhalt)
    identisch = pfade[0].read_bytes() == pfade[1].read_bytes()
    stand = json.loads(pfade[0].read_text(encoding="utf-8"))["stand"]
pruefe(erstes and not zweites, "beide Pfade werden idempotent geschrieben")
pruefe(identisch, "Ordnerdatei und Kompatibilitätsdatei sind bytegleich")
pruefe(stand == sammler.date.today().isoformat(), "Datenstand gesetzt")


print("Gemeinderats-Einzeldateien je AGS")
with tempfile.TemporaryDirectory(prefix="plakat-test-") as ordner:
    altes_ziel = sammler.ZIEL
    altes_gemeinderat_ziel = sammler.GEMEINDERAT_ZIEL
    sammler.ZIEL = Path(ordner) / "daten"
    sammler.GEMEINDERAT_ZIEL = Path(ordner) / "gemeinderat"
    landesdaten = {
        "land": "14",
        "name": "Sachsen",
        "wahlart": "kommunal",
        "titel": "Gemeinde- und Stadtratswahl Sachsen 2024",
        "jahr": 2024,
        "wahl_datum": "2024-06-09",
        "schluesselart": "ags",
        "quelle": "GERDA",
        "quellenvermerk": "Datenquelle: GERDA",
        "lizenz": "CC BY 4.0",
        "lizenz_url": "https://creativecommons.org/licenses/by/4.0/",
        "quellendatei": "https://example.invalid/kommunal.csv",
        "gebiete": {
            "14730110": {
                "name": "Eilenburg, Stadt",
                "beteiligung": 60.0,
                "parteien": {"AfD": 31.7, "CDU": 21.5},
            },
            "14730270": {
                "name": "Taucha, Stadt",
                "beteiligung": 65.0,
                "parteien": {"AfD": 25.0, "CDU": 20.0},
            },
        },
        "stand": "2026-08-11",
    }
    gemeindeordner = sammler.GEMEINDERAT_ZIEL / "14"
    gemeindeordner.mkdir(parents=True)
    (gemeindeordner / "14739999.json").write_text("{}\n", encoding="utf-8")
    try:
        erstes = sammler._gemeinderatsdateien_schreiben(landesdaten)
        einzeldatei = json.loads(
            (gemeindeordner / "14730110.json").read_text(encoding="utf-8")
        )
        landesindex = json.loads((gemeindeordner / "index.json").read_text(encoding="utf-8"))
        stale_entfernt = not (gemeindeordner / "14739999.json").exists()
        zweites = sammler._gemeinderatsdateien_schreiben(landesdaten)
    finally:
        sammler.ZIEL = altes_ziel
        sammler.GEMEINDERAT_ZIEL = altes_gemeinderat_ziel
pruefe(erstes and not zweites, "Einzeldateien werden idempotent geschrieben")
pruefe(stale_entfernt, "veraltete AGS-Datei entfernt")
pruefe(einzeldatei["ags"] == "14730110", "AGS steht als Text in der Einzeldatei")
pruefe(einzeldatei["land_name"] == "Sachsen", "Land ist ohne Namenskollision enthalten")
pruefe(einzeldatei["parteien"]["AfD"] == 31.7, "Parteiergebnis direkt abrufbar")
pruefe(einzeldatei["stand"] == "2026-08-11", "Datenstand der Landesdatei übernommen")
pruefe(landesindex["gemeinden"] == 2, "Landesindex enthält die Gemeindezahl")
pruefe(landesindex["dateimuster"] == "{ags}.json", "Landesindex erklärt den Direktabruf")


print("Snapshot-Ergänzungen: Gebiete aus geprüfter JSON-Datei")
with tempfile.TemporaryDirectory(prefix="plakat-test-") as ordner:
    altes_wurzel = sammler.WURZEL
    sammler.WURZEL = Path(ordner)
    (Path(ordner) / "quellen").mkdir()
    (Path(ordner) / "quellen" / "snapshot.json").write_text(
        json.dumps({"kreistag_2024": {"07131": {"name": "Ahrweiler", "beteiligung": 64.3, "parteien": {"CDU": 37.5}}}}),
        encoding="utf-8",
    )
    try:
        gebiete = sammler._snapshot_gebiete("quellen/snapshot.json", "kreistag_2024")
        try:
            sammler._snapshot_gebiete("quellen/snapshot.json", "kommunal_2024")
            fehlender_schluessel_erkannt = False
        except sammler.Fehler:
            fehlender_schluessel_erkannt = True
        try:
            sammler._snapshot_gebiete("quellen/fehlt.json", "kreistag_2024")
            fehlende_datei_erkannt = False
        except sammler.Fehler:
            fehlende_datei_erkannt = True
    finally:
        sammler.WURZEL = altes_wurzel
pruefe(gebiete["07131"]["name"] == "Ahrweiler", "Gebiete werden aus der Snapshot-Datei gelesen")
pruefe(fehlender_schluessel_erkannt, "fehlender Schlüssel schlägt kontrolliert fehl")
pruefe(fehlende_datei_erkannt, "fehlende Datei schlägt kontrolliert fehl")


print("Snapshot-Ergänzungen: volle Ersetzung, auch mit weniger Gebieten als vorher")
with tempfile.TemporaryDirectory(prefix="plakat-test-") as ordner:
    altes_wurzel = sammler.WURZEL
    sammler.WURZEL = Path(ordner)
    (Path(ordner) / "quellen").mkdir()
    (Path(ordner) / "quellen" / "snapshot.json").write_text(
        json.dumps({"kommunal_2024": {"07111000": {"name": "Koblenz, Stadt", "beteiligung": 60.4, "parteien": {"CDU": 27.7}}}}),
        encoding="utf-8",
    )
    ziel = {
        "07": {"jahr": 2019, "gebiete": {
            "07111000": {"name": "Koblenz, Stadt", "beteiligung": 57.7},
            "07131079": {"name": "Trierscheid", "beteiligung": 87.0},
        }},
    }
    ergaenzungen = [{
        "land": "07", "jahr": 2024, "wahl_datum": "2024-06-09",
        "datei": "quellen/snapshot.json", "schluessel": "kommunal_2024",
        "quelle": "Landeswahlleiter Rheinland-Pfalz", "quellenvermerk": "x",
        "lizenz": "y", "lizenz_url": "https://example.invalid", "url": "https://example.invalid/quelle.pdf",
    }]
    try:
        gescheitert = sammler._snapshot_ergaenzungen_anwenden(ziel, ergaenzungen, {"07"})
        gescheitert_unbekanntes_land = sammler._snapshot_ergaenzungen_anwenden(
            {}, [{**ergaenzungen[0], "land": "99"}], {"07"}
        )
    finally:
        sammler.WURZEL = altes_wurzel
pruefe(not gescheitert, "keine Fehlermeldung bei gültiger Ergänzung")
pruefe(len(ziel["07"]["gebiete"]) == 1, "Ergänzung ersetzt vollständig statt zusammenzuführen")
pruefe("07131079" not in ziel["07"]["gebiete"], "nicht mehr abgedeckte Gebiete fehlen bewusst, keine Altdaten")
pruefe(ziel["07"]["jahr"] == 2024, "Jahr der Ergänzung wird übernommen")
pruefe(gescheitert_unbekanntes_land == [], "Land ausserhalb der Suche bleibt unangetastet, kein Fehler")


print()
if fehler:
    print(f"{fehler} Prüfung(en) fehlgeschlagen")
    raise SystemExit(1)
print("Alle Prüfungen bestanden")
