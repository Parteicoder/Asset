#!/usr/bin/env python3
"""Wahldaten laden und als kompakte JSON-Dateien unter ``daten/`` ablegen.

Landtags-, Gemeinde-/Stadtrats- und Kreistagswahlen werden ohne Anmeldung aus GERDA geladen.
Jede benötigte GERDA-CSV wird pro Lauf genau einmal heruntergeladen und anschließend für alle
gewünschten Länder ausgewertet. Für Länder mit einer eigenen `ergaenzungen`-Konfiguration in
`quellen.json` ersetzt eine amtliche Ergebnisdatei (XLSX oder CSV) das GERDA-Ergebnis für die
Landtagswahl. Das betrifft derzeit Rheinland-Pfalz 2026 (in GERDA noch nicht enthalten), Sachsen
2024, Sachsen-Anhalt 2021, Berlin 2023 und Mecklenburg-Vorpommern 2021 (amtliche Gemeindeebene
statt GERDAs harmonisierter Daten). Dieselbe Ersetzung gibt es analog für Kommunal-/Kreistagswahl
über `kommunal_ergaenzungen`/`kreistag_ergaenzungen` (Rheinland-Pfalz, Mecklenburg-Vorpommern,
Thüringen, Brandenburg, Bayern).

Bundestags- und Europawahl bleiben beim offenen kerg2-Angebot der Bundeswahlleiterin. Der Sammler
benötigt nur die Python-Standardbibliothek und keinerlei Zugangsdaten.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Iterable, Iterator


WURZEL = Path(__file__).resolve().parent.parent
QUELLEN = WURZEL / "quellen.json"
ZIEL = WURZEL / "daten"
# Bewusst NICHT unter ZIEL: Cloudflare Pages deployt ZIEL 1:1 und erlaubt maximal 20.000 Dateien.
# Eine Einzeldatei je Gemeinde-AGS würde dieses Limit reissen (siehe RLP-Vollabdeckung, PR #29).
# Die Direktabruf-Dateien bleiben deshalb nur im Git-Repository, nicht auf daten.plakat-kompass.de.
GEMEINDERAT_ZIEL = WURZEL / "gemeinderat"

ZEITSCHRANKE = 300
VERSUCHE = 3
USER_AGENT = "PlakatKompassAsset/2.0 (+https://github.com/Parteicoder/Plakat-Kompass-Asset)"

LIZENZ_BUND = "Datenlizenz Deutschland, Namensnennung, Version 2.0 (dl-de/by-2-0)"
LIZENZ_BUND_URL = "https://www.govdata.de/dl-de/by-2-0"
QUELLE_BUND = "Die Bundeswahlleiterin, Wiesbaden"
QUELLENVERMERK_BUND = f"Datenquelle: {QUELLE_BUND}"


class Fehler(Exception):
    """Ein Abbruch mit einer Erklärung, die im Actions-Protokoll verständlich bleibt."""


def schreiben(datei: Path, inhalt: dict, zeitfeld: str = "stand", jetzt: str | None = None) -> bool:
    """Nur bei einer inhaltlichen Änderung schreiben; das Laufdatum allein zählt nicht."""
    ohne_zeit = {k: v for k, v in inhalt.items() if k != zeitfeld}
    if datei.exists():
        try:
            alt = json.loads(datei.read_text(encoding="utf-8"))
            if {k: v for k, v in alt.items() if k != zeitfeld} == ohne_zeit:
                return False
        except (OSError, json.JSONDecodeError):
            pass

    datei.parent.mkdir(exist_ok=True)
    datei.write_text(
        json.dumps(
            {**inhalt, zeitfeld: jetzt or date.today().isoformat()},
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    return True


# --------------------------------------------------------------------------- Netz


def lade_datei(adresse: str, ziel: Path) -> int:
    """Eine öffentliche Datei mit Wiederholungen laden und ihre Bytezahl zurückgeben."""
    letzter_fehler: Exception | None = None
    for versuch in range(1, VERSUCHE + 1):
        anfrage = urllib.request.Request(adresse, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(anfrage, timeout=ZEITSCHRANKE) as antwort:
                with ziel.open("wb") as ausgabe:
                    shutil.copyfileobj(antwort, ausgabe, length=1024 * 1024)

            groesse = ziel.stat().st_size
            with ziel.open("rb") as eingabe:
                anfang = eingabe.read(200)
            if anfang.startswith(b"version https://git-lfs.github.com/spec/v1"):
                raise Fehler("GitHub hat nur den Git-LFS-Zeiger statt der Datendatei geliefert.")
            if groesse == 0:
                raise Fehler("Die heruntergeladene Datei ist leer.")
            return groesse
        except urllib.error.HTTPError as exc:
            letzter_fehler = exc
            if exc.code not in (429, 500, 502, 503, 504) or versuch == VERSUCHE:
                raise Fehler(f"HTTP {exc.code} für {adresse}") from exc
            pause = float(exc.headers.get("Retry-After") or 0) or 5.0 * versuch
        except urllib.error.URLError as exc:
            letzter_fehler = exc
            if versuch == VERSUCHE:
                raise Fehler(f"Netzfehler für {adresse}: {exc.reason}") from exc
            pause = 5.0 * versuch
        except (OSError, Fehler) as exc:
            letzter_fehler = exc
            if versuch == VERSUCHE:
                raise Fehler(f"Download fehlgeschlagen: {exc}") from exc
            pause = 5.0 * versuch

        print(f"    Download fehlgeschlagen, neuer Versuch in {pause:.0f} s ({versuch}/{VERSUCHE})")
        time.sleep(pause)

    raise Fehler(f"Download fehlgeschlagen: {letzter_fehler}")


def hole_roh(adresse: str, encoding: str = "utf-8-sig") -> str:
    """Eine öffentliche Textdatei laden, ohne Zugangsdaten oder Cookies zu senden."""
    with tempfile.TemporaryDirectory(prefix="plakat-kompass-") as ordner:
        datei = Path(ordner) / "download"
        lade_datei(adresse, datei)
        return datei.read_text(encoding=encoding, errors="replace")


# --------------------------------------------------------------------------- GERDA


GERDA_PFLICHTSPALTEN = {
    "ags",
    "ags_name",
    "election_year",
    "election_date",
    "state",
    "turnout",
    "other",
    "50plus",
    "zentrum",
}


PARTEINAMEN = {
    "afd": "AfD",
    "biw": "BIW",
    "bp": "BP",
    "bsw": "BSW",
    "bue90_gruene": "GRÜNE",
    "bundnis_c": "Bündnis C",
    "bundnis_deutschland": "BÜNDNIS DEUTSCHLAND",
    "bueso": "BüSo",
    "cdu": "CDU",
    "csu": "CSU",
    "diebasis": "dieBasis",
    "die_heimat_heimat": "Die Heimat",
    "die_humanisten": "Die Humanisten",
    "die_partei": "Die PARTEI",
    "die_rechte": "DIE RECHTE",
    "diewahl_wfg": "DieWahl",
    "fdp": "FDP",
    "freie_sachsen": "FREIE SACHSEN",
    "freie_wahler": "FREIE WÄHLER",
    "freiewaehler": "FREIE WÄHLER",
    "gruene": "GRÜNE",
    "linke_pds": "DIE LINKE",
    "mlpd": "MLPD",
    "npd": "NPD",
    "odp": "ÖDP",
    "other": "Sonstige",
    "pdh": "PdH",
    "piraten": "PIRATEN",
    "spd": "SPD",
    "ssw": "SSW",
    "tier_schutz_partei": "Tierschutzpartei",
    "tierschutz": "Tierschutzpartei",
    "tierschutz_hier": "TIERSCHUTZ hier!",
    "tierschutzallianz": "Tierschutzallianz",
    "v_partei3": "V-Partei³",
    "werteunion": "WerteUnion",
    "volt": "Volt",
}


# GERDA führt Gemeinde-/Stadtratswahlen bewusst mit einem festen Satz großer Parteien. Alles
# Weitere – örtliche Listen, gemeinsame Wahlvorschläge und Einzelbewerber – steht bereits gesammelt
# in `other`. CDU und CSU teilen sich eine Spalte; die Landkennzahl entscheidet über den Namen.
KOMMUNAL_PARTEISPALETEN = (
    "cdu_csu",
    "spd",
    "linke_pds",
    "gruene",
    "afd",
    "piraten",
    "fdp",
    "die_partei",
    "freie_wahler",
    "bsw",
    "other",
)

KOMMUNAL_PARTEINAMEN = {
    "spd": "SPD",
    "linke_pds": "DIE LINKE",
    "gruene": "GRÜNE",
    "afd": "AfD",
    "piraten": "PIRATEN",
    "fdp": "FDP",
    "die_partei": "Die PARTEI",
    "freie_wahler": "FREIE WÄHLER",
    "bsw": "BSW",
    "other": "Sonstige",
}


# Der Kreistagsdatensatz erhält die Namen aller historischen Listen als eigene Spalten (derzeit
# mehrere hundert). Für die App werden wiederkehrende Parteien und die beiden kommunalen
# Sammelgruppen getrennt gezeigt; alle übrigen örtlichen Listen bleiben vollständig als
# `Sonstige` erhalten. Eine unbekannte neue GERDA-Spalte geht dadurch nicht verloren.
KREISTAG_GRUPPEN = (
    ("SPD", ("spd",)),
    ("DIE LINKE", ("linke_pds",)),
    ("GRÜNE", ("gruene",)),
    ("AfD", ("afd",)),
    ("FDP", ("fdp",)),
    ("FREIE WÄHLER", ("freie_waehler", "freie_w_hler")),
    ("BSW", ("bsw",)),
    ("Die PARTEI", ("die_partei",)),
    ("PIRATEN", ("piraten",)),
    ("SSW", ("ssw",)),
    ("ÖDP", ("oedp",)),
    ("Volt", ("volt", "volt_deutschland")),
    ("Tierschutzpartei", ("tierschutz",)),
    ("TIERSCHUTZ hier!", ("tierschutz_hier",)),
    ("Tierschutzallianz", ("tierschutzallianz",)),
    ("BÜNDNIS DEUTSCHLAND", ("b_ndnis_deutschland",)),
    ("Bündnis C", ("buendnis_c",)),
    ("FREIE SACHSEN", ("freie_sachsen",)),
    ("BVB/FREIE WÄHLER", ("bvb_fw",)),
    ("WerteUnion", ("werteunion",)),
    ("Wählervereinigungen", ("waehlergruppen", "waehlervereinigungen")),
    ("Einzelbewerber", ("einzelbewerber",)),
)


def _zahl(text: str | None) -> float | None:
    roh = (text or "").strip().replace("\xa0", "").replace(" ", "")
    if not roh or roh.lower() in {"na", "nan", "null", "."}:
        return None
    if "," in roh and "." in roh:
        roh = roh.replace(".", "").replace(",", ".")
    elif "," in roh:
        roh = roh.replace(",", ".")
    try:
        wert = float(roh)
    except ValueError:
        return None
    return wert if math.isfinite(wert) else None


def _ganzzahl(text: str | None) -> int | None:
    roh = (text or "").strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    if not roh:
        return None
    try:
        wert = Decimal(roh)
    except InvalidOperation:
        return None
    if not wert.is_finite() or wert != wert.to_integral_value():
        return None
    return int(wert)


def _parteiname(spalte: str) -> str:
    if spalte in PARTEINAMEN:
        return PARTEINAMEN[spalte]
    if "_" not in spalte and len(spalte) <= 5:
        return spalte.upper()
    return " ".join(wort.capitalize() for wort in spalte.split("_") if wort)


def _gerda_parteispalten(feldnamen: list[str]) -> list[str]:
    fehlend = sorted(GERDA_PFLICHTSPALTEN - set(feldnamen))
    if fehlend:
        raise Fehler("GERDA-Spalten fehlen: " + ", ".join(fehlend))
    von = feldnamen.index("50plus")
    # `far_right` beginnt den Block abgeleiteter Analysefelder. Falls GERDA neue Parteien nach
    # `zentrum` ergänzt, werden sie so weiterhin mitgenommen.
    bis = feldnamen.index("far_right") if "far_right" in feldnamen else feldnamen.index("zentrum") + 1
    if bis < von:
        raise Fehler("GERDA-Parteispalten stehen in einer unerwarteten Reihenfolge.")
    return ["other", *feldnamen[von:bis]]


def _gerda_letzte_jahre_und_namen(
    datei: Path, gesucht: set[str]
) -> tuple[dict[str, int], dict[str, str]]:
    jahre: dict[str, int] = {}
    namen: dict[str, str] = {}
    with datei.open(encoding="utf-8-sig", newline="") as eingabe:
        leser = csv.DictReader(eingabe)
        _gerda_parteispalten(leser.fieldnames or [])
        for zeile in leser:
            land = (zeile.get("state") or "").strip().zfill(2)
            jahr = _ganzzahl(zeile.get("election_year"))
            if land in gesucht and jahr is not None:
                jahre[land] = max(jahre.get(land, 0), jahr)
                ags = (zeile.get("ags") or "").strip()
                name = (zeile.get("ags_name") or "").strip()
                if re.fullmatch(r"\d{8}", ags) and name:
                    namen[ags] = name
    return jahre, namen


def _gerda_gebiet(
    zeile: dict[str, str], parteispalten: list[str], name_fallback: str = ""
) -> dict | None:
    ags = (zeile.get("ags") or "").strip()
    if not re.fullmatch(r"\d{8}", ags):
        return None
    name = (zeile.get("ags_name") or "").strip() or name_fallback
    if not name:
        return None

    rohanteile: dict[str, float] = defaultdict(float)
    for spalte in parteispalten:
        wert = _zahl(zeile.get(spalte))
        if wert is None or wert <= 0:
            continue
        if wert > 1.05:
            return None
        rohanteile[_parteiname(spalte)] += wert

    summe = sum(rohanteile.values())
    if len(rohanteile) < 3 or not 0.95 <= summe <= 1.05:
        return None

    # Harmonisierung und proportionale Briefwahl-Zuteilung können die GERDA-Summe geringfügig
    # von 1 abweichen lassen. Für die Anzeige wird deshalb auf exakt 100 Prozent normiert.
    faktor = 100.0 / summe
    parteien = {
        name: round(wert * faktor, 1)
        for name, wert in sorted(rohanteile.items(), key=lambda paar: -paar[1])
        if round(wert * faktor, 1) > 0.0
    }

    beteiligung_roh = _zahl(zeile.get("turnout"))
    beteiligung = (
        round(beteiligung_roh * 100.0, 1)
        if beteiligung_roh is not None and 0.0 <= beteiligung_roh <= 1.0
        else None
    )
    return {
        "name": name,
        "beteiligung": beteiligung,
        "parteien": parteien,
    }


def gerda_datei_auswerten(datei: Path, gesucht: set[str]) -> dict[str, dict]:
    """Je Land nur das jüngste in der GERDA-Datei vorhandene Wahljahr auswerten."""
    jahre, namen = _gerda_letzte_jahre_und_namen(datei, gesucht)
    ergebnis = {
        land: {"jahr": jahr, "wahl_datum": "", "gebiete": {}, "herkunft": "gerda"}
        for land, jahr in jahre.items()
    }

    with datei.open(encoding="utf-8-sig", newline="") as eingabe:
        leser = csv.DictReader(eingabe)
        parteispalten = _gerda_parteispalten(leser.fieldnames or [])
        for zeile in leser:
            land = (zeile.get("state") or "").strip().zfill(2)
            jahr = _ganzzahl(zeile.get("election_year"))
            if land not in jahre or jahr != jahre[land]:
                continue
            ags = (zeile.get("ags") or "").strip()
            gebiet = _gerda_gebiet(zeile, parteispalten, namen.get(ags, ""))
            if gebiet is None:
                continue
            if ags in ergebnis[land]["gebiete"]:
                raise Fehler(f"GERDA enthält {ags} im Jahr {jahr} mehrfach.")
            ergebnis[land]["gebiete"][ags] = gebiet
            ergebnis[land]["wahl_datum"] = (zeile.get("election_date") or "").strip()

    for land, daten in ergebnis.items():
        if not daten["gebiete"]:
            raise Fehler(f"GERDA: Für Land {land} hat kein Gebiet die Plausibilitätsprüfung bestanden.")
    return ergebnis


# ------------------------------------------------ Gemeinde- und Kreistagswahlen


def _datum_kurz(text: str | None) -> str:
    """ISO-Zeitstempel aus GERDA auf das für die Anzeige nötige Datum kürzen."""
    roh = (text or "").strip()
    return roh[:10] if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", roh) else ""


def _anteile_in_prozent(rohanteile: dict[str, float], gebiet: str) -> dict[str, float]:
    """Plausible GERDA-Bruchteile auf exakt 100 Prozent normieren und sortieren."""
    positive = {name: wert for name, wert in rohanteile.items() if wert > 0.0}
    summe = sum(positive.values())
    if not positive or not 0.95 <= summe <= 1.05:
        raise Fehler(f"GERDA: Parteianteile für {gebiet} ergeben {summe:.6f} statt ungefähr 1.")
    faktor = 100.0 / summe
    return {
        name: round(wert * faktor, 1)
        for name, wert in sorted(positive.items(), key=lambda paar: (-paar[1], paar[0]))
        if round(wert * faktor, 1) > 0.0
    }


def _beteiligung(zeile: dict[str, str]) -> float | None:
    wert = _zahl(zeile.get("turnout"))
    return round(wert * 100.0, 1) if wert is not None and 0.0 <= wert <= 1.0 else None


def _neueste_gerda_jahre(
    datei: Path,
    gesucht: set[str],
    land_spalte: str = "state",
) -> dict[str, int]:
    jahre: dict[str, int] = {}
    with datei.open(encoding="utf-8-sig", newline="") as eingabe:
        for zeile in csv.DictReader(eingabe):
            land = (zeile.get(land_spalte) or "").strip().zfill(2)
            jahr = _ganzzahl(zeile.get("election_year"))
            if land in gesucht and jahr is not None:
                jahre[land] = max(jahre.get(land, 0), jahr)
    return jahre


def gerda_kommunal_auswerten(datei: Path, gesucht: set[str]) -> dict[str, dict]:
    """Jüngste Gemeinde-/Stadtratswahl je Land auf den 2025er Gemeinde-AGS lesen."""
    pflicht = {
        "ags",
        "ags_name",
        "state",
        "election_year",
        "election_date",
        "turnout",
        *KOMMUNAL_PARTEISPALETEN,
    }
    with datei.open(encoding="utf-8-sig", newline="") as eingabe:
        feldnamen = csv.DictReader(eingabe).fieldnames or []
    fehlend = sorted(pflicht - set(feldnamen))
    if fehlend:
        raise Fehler("GERDA-Kommunalspalten fehlen: " + ", ".join(fehlend))

    jahre = _neueste_gerda_jahre(datei, gesucht)
    ergebnis = {
        land: {"jahr": jahr, "wahl_datum": "", "gebiete": {}, "herkunft": "gerda-kommunal"}
        for land, jahr in jahre.items()
    }

    with datei.open(encoding="utf-8-sig", newline="") as eingabe:
        for zeile in csv.DictReader(eingabe):
            land = (zeile.get("state") or "").strip().zfill(2)
            jahr = _ganzzahl(zeile.get("election_year"))
            if land not in jahre or jahr != jahre[land]:
                continue

            ags = (zeile.get("ags") or "").strip()
            name = (zeile.get("ags_name") or "").strip()
            if not re.fullmatch(r"\d{8}", ags) or not ags.startswith(land) or not name:
                raise Fehler(f"GERDA-Kommunalwahl: ungültiges Gebiet {ags!r} ({name!r}).")

            rohanteile: dict[str, float] = defaultdict(float)
            for spalte in KOMMUNAL_PARTEISPALETEN:
                wert = _zahl(zeile.get(spalte))
                if wert is None:
                    continue
                if not 0.0 <= wert <= 1.05:
                    raise Fehler(f"GERDA-Kommunalwahl: ungültiger Anteil {spalte}={wert} in {ags}.")
                parteiname = (
                    ("CSU" if land == "09" else "CDU")
                    if spalte == "cdu_csu"
                    else KOMMUNAL_PARTEINAMEN[spalte]
                )
                rohanteile[parteiname] += wert

            parteien = _anteile_in_prozent(rohanteile, ags)
            gebiet = {
                "name": name,
                "beteiligung": _beteiligung(zeile),
                "parteien": parteien,
            }
            if set(parteien) == {"Sonstige"}:
                gebiet["hinweis"] = (
                    "GERDA weist hier nur örtliche Listen, Wählervereinigungen oder "
                    "Einzelbewerber zusammengefasst als Sonstige aus."
                )
            if ags in ergebnis[land]["gebiete"]:
                raise Fehler(f"GERDA-Kommunalwahl enthält {ags} im Jahr {jahr} mehrfach.")
            ergebnis[land]["gebiete"][ags] = gebiet

            datum = _datum_kurz(zeile.get("election_date"))
            bisher = ergebnis[land]["wahl_datum"]
            if datum and bisher and datum != bisher:
                raise Fehler(f"GERDA-Kommunalwahl: mehrere Wahltage für Land {land} im Jahr {jahr}.")
            if datum:
                ergebnis[land]["wahl_datum"] = datum

    for land, daten in ergebnis.items():
        if not daten["gebiete"]:
            raise Fehler(f"GERDA-Kommunalwahl: Für Land {land} wurden keine Gemeinden gefunden.")
    return ergebnis


def gerda_kreisverzeichnis_auswerten(datei: Path) -> dict[str, dict[str, str]]:
    """Aktuellen Namen und Typ jedes Kreises aus GERDAs Ratszusammensetzungsdatei lesen."""
    pflicht = {"county", "county_name", "county_type", "state", "year"}
    aktuell: dict[str, tuple[int, dict[str, str]]] = {}
    with datei.open(encoding="utf-8-sig", newline="") as eingabe:
        leser = csv.DictReader(eingabe)
        fehlend = sorted(pflicht - set(leser.fieldnames or []))
        if fehlend:
            raise Fehler("GERDA-Kreisverzeichnisspalten fehlen: " + ", ".join(fehlend))
        for zeile in leser:
            kreis = (zeile.get("county") or "").strip()
            land = (zeile.get("state") or "").strip().zfill(2)
            name = (zeile.get("county_name") or "").strip()
            typ = (zeile.get("county_type") or "").strip()
            jahr = _ganzzahl(zeile.get("year"))
            if not re.fullmatch(r"\d{5}", kreis) or not kreis.startswith(land):
                raise Fehler(f"GERDA-Kreisverzeichnis: ungültiger Kreisschlüssel {kreis!r}.")
            if not name or typ not in {"Landkreis", "kreisfreie Stadt"} or jahr is None:
                raise Fehler(f"GERDA-Kreisverzeichnis: unvollständiger Eintrag für {kreis}.")
            if kreis not in aktuell or jahr > aktuell[kreis][0]:
                aktuell[kreis] = (jahr, {"name": name, "typ": typ, "land": land})
    return {kreis: daten for kreis, (_, daten) in aktuell.items()}


def _kreistag_parteispalten(feldnamen: list[str]) -> list[str]:
    pflicht = {
        "county_code",
        "election_year",
        "state",
        "invalid_votes",
        "turnout",
        "flag_unsuccessful_naive_merge",
        "total_vote_share",
        "cdu",
        "csu",
        "spd",
        "gruene",
        "afd",
        "bsw",
        "waehlergruppen",
        "einzelbewerber",
    }
    fehlend = sorted(pflicht - set(feldnamen))
    if fehlend:
        raise Fehler("GERDA-Kreistagsspalten fehlen: " + ", ".join(fehlend))
    von = feldnamen.index("invalid_votes") + 1
    bis = feldnamen.index("flag_unsuccessful_naive_merge")
    if bis <= von:
        raise Fehler("GERDA-Kreistagsspalten stehen in einer unerwarteten Reihenfolge.")
    return [
        spalte
        for spalte in feldnamen[von:bis]
        if spalte != "bemerkungen" and not spalte.startswith("flag_")
    ]


def _kreistag_gebiet(
    zeile: dict[str, str],
    parteispalten: list[str],
    land: str,
    kreis: str,
    name: str,
) -> dict:
    alle: dict[str, float] = {}
    for spalte in parteispalten:
        wert = _zahl(zeile.get(spalte))
        if wert is None:
            continue
        if not 0.0 <= wert <= 1.05:
            raise Fehler(f"GERDA-Kreistagswahl: ungültiger Anteil {spalte}={wert} in {kreis}.")
        if wert > 0.0:
            alle[spalte] = wert

    gesamtsumme = sum(alle.values())
    gemeldet = _zahl(zeile.get("total_vote_share"))
    if gemeldet is None or abs(gesamtsumme - gemeldet) > 0.01:
        raise Fehler(
            f"GERDA-Kreistagswahl: Spaltensumme {gesamtsumme:.6f} passt in {kreis} "
            f"nicht zur gemeldeten Summe {gemeldet}."
        )

    gruppiert: dict[str, float] = defaultdict(float)
    verbraucht: set[str] = set()
    union_name = "CSU" if land == "09" else "CDU"
    for spalte in ("cdu", "csu"):
        gruppiert[union_name] += alle.get(spalte, 0.0)
        verbraucht.add(spalte)
    for anzeigename, spalten in KREISTAG_GRUPPEN:
        for spalte in spalten:
            gruppiert[anzeigename] += alle.get(spalte, 0.0)
            verbraucht.add(spalte)

    sonstige = sum(wert for spalte, wert in alle.items() if spalte not in verbraucht)
    gruppiert["Sonstige"] += sonstige
    return {
        "name": name,
        "beteiligung": _beteiligung(zeile),
        "parteien": _anteile_in_prozent(gruppiert, kreis),
    }


def gerda_kreistag_auswerten(
    datei: Path,
    kreisverzeichnis: dict[str, dict[str, str]],
    gesucht: set[str],
) -> dict[str, dict]:
    """Jüngste Kreistagswahl je Land lesen; Räte kreisfreier Städte ausdrücklich auslassen."""
    with datei.open(encoding="utf-8-sig", newline="") as eingabe:
        feldnamen = csv.DictReader(eingabe).fieldnames or []
    parteispalten = _kreistag_parteispalten(feldnamen)
    jahre = _neueste_gerda_jahre(datei, gesucht)
    ergebnis = {
        land: {"jahr": jahr, "wahl_datum": "", "gebiete": {}, "herkunft": "gerda-kreistag"}
        for land, jahr in jahre.items()
    }

    with datei.open(encoding="utf-8-sig", newline="") as eingabe:
        for zeile in csv.DictReader(eingabe):
            land = (zeile.get("state") or "").strip().zfill(2)
            jahr = _ganzzahl(zeile.get("election_year"))
            if land not in jahre or jahr != jahre[land]:
                continue
            kreis = (zeile.get("county_code") or "").strip()
            meta = kreisverzeichnis.get(kreis)
            if not re.fullmatch(r"\d{5}", kreis) or not kreis.startswith(land) or meta is None:
                raise Fehler(f"GERDA-Kreistagswahl: ungültiger oder unbekannter Kreis {kreis!r}.")
            if meta["typ"] != "Landkreis":
                continue
            if kreis in ergebnis[land]["gebiete"]:
                raise Fehler(f"GERDA-Kreistagswahl enthält {kreis} im Jahr {jahr} mehrfach.")
            ergebnis[land]["gebiete"][kreis] = _kreistag_gebiet(
                zeile, parteispalten, land, kreis, meta["name"]
            )

    # Das Verzeichnis enthält genau die heutigen Landkreise. Diese Vollständigkeitsprüfung fängt
    # sowohl einen abgebrochenen GERDA-Export als auch versehentlich mitgenommene kreisfreie Städte.
    for land in gesucht:
        erwartet = {
            kreis
            for kreis, meta in kreisverzeichnis.items()
            if meta["land"] == land and meta["typ"] == "Landkreis"
        }
        if not erwartet:
            ergebnis.pop(land, None)  # Stadtstaaten haben keinen Kreistag.
            continue
        gefunden = set(ergebnis.get(land, {}).get("gebiete", {}))
        if gefunden != erwartet:
            fehlt = sorted(erwartet - gefunden)
            zuviel = sorted(gefunden - erwartet)
            raise Fehler(
                f"GERDA-Kreistagswahl Land {land}: erwartet {len(erwartet)} Landkreise, "
                f"gefunden {len(gefunden)}; fehlen {fehlt[:5]}, zusätzlich {zuviel[:5]}."
            )
    return ergebnis


# ---------------------------------------------------------- Rheinland-Pfalz 2026


XLSX_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
RLP_PARTEISPALTEN = {
    "DR": "SPD",
    "DT": "CDU",
    "DV": "GRÜNE",
    "DX": "AfD",
    "DZ": "FDP",
    "EB": "FREIE WÄHLER",
    "ED": "DIE LINKE",
    "EF": "Tierschutzpartei",
    "EH": "Volt",
    "EJ": "ÖDP",
    "EL": "BSW",
    "EN": "PdH",
}


XLSX_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _xlsx_blattpfad(archiv: zipfile.ZipFile, blatt: str) -> str:
    """Den internen Dateipfad eines Tabellenblatts über Namen statt Position finden."""
    wurzel = ET.fromstring(archiv.read("xl/workbook.xml"))
    rid = next(
        (
            eintrag.get(f"{{{XLSX_REL_NS}}}id")
            for eintrag in wurzel.findall(".//a:sheets/a:sheet", XLSX_NS)
            if eintrag.get("name") == blatt
        ),
        None,
    )
    if rid is None:
        raise Fehler(f"XLSX enthält kein Tabellenblatt {blatt!r}.")
    beziehungen = ET.fromstring(archiv.read("xl/_rels/workbook.xml.rels"))
    ziel = next((b.get("Target") for b in beziehungen if b.get("Id") == rid), None)
    if not ziel:
        raise Fehler(f"XLSX: kein Ziel für Tabellenblatt {blatt!r} gefunden.")
    return ziel if ziel.startswith("xl/") else f"xl/{ziel}"


def _xlsx_zeilen(datei: Path, blatt: str | None = None) -> list[dict[str, str]]:
    """Eine XLSX-Tabelle ohne externe Excel-Bibliothek lesen; ohne Namen die erste Tabelle."""
    try:
        with zipfile.ZipFile(datei) as archiv:
            texte: list[str] = []
            if "xl/sharedStrings.xml" in archiv.namelist():
                wurzel = ET.fromstring(archiv.read("xl/sharedStrings.xml"))
                texte = [
                    "".join(knoten.text or "" for knoten in eintrag.findall(".//a:t", XLSX_NS))
                    for eintrag in wurzel.findall("a:si", XLSX_NS)
                ]
            sheet_pfad = _xlsx_blattpfad(archiv, blatt) if blatt else "xl/worksheets/sheet1.xml"
            tabelle = ET.fromstring(archiv.read(sheet_pfad))
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise Fehler(f"XLSX-Datei ist nicht lesbar: {exc}") from exc

    zeilen: list[dict[str, str]] = []
    for zeile in tabelle.findall(".//a:sheetData/a:row", XLSX_NS):
        werte: dict[str, str] = {}
        for zelle in zeile.findall("a:c", XLSX_NS):
            referenz = zelle.get("r") or ""
            treffer = re.match(r"[A-Z]+", referenz)
            if not treffer:
                continue
            typ = zelle.get("t")
            wertknoten = zelle.find("a:v", XLSX_NS)
            if typ == "s" and wertknoten is not None:
                try:
                    wert = texte[int(wertknoten.text or "0")]
                except (IndexError, ValueError):
                    wert = ""
            elif typ == "inlineStr":
                wert = "".join(k.text or "" for k in zelle.findall(".//a:t", XLSX_NS))
            else:
                wert = wertknoten.text if wertknoten is not None and wertknoten.text else ""
            werte[treffer.group()] = wert
        zeilen.append(werte)
    return zeilen


def _kennung(text: str | None) -> str:
    roh = (text or "").strip().replace(" ", "").replace(",", ".")
    if not roh:
        return ""
    try:
        zahl = Decimal(roh)
        if zahl.is_finite() and zahl == zahl.to_integral_value():
            roh = str(int(zahl))
    except InvalidOperation:
        pass
    return roh.zfill(13) if roh.isdigit() else roh


def _rlp_ags(zeile: dict[str, str]) -> str:
    kennung = _kennung(zeile.get("A"))
    if len(kennung) != 13 or not kennung.isdigit():
        raise Fehler(f"RLP: ungültiger Identifikationsschlüssel {zeile.get('A')!r}")
    if zeile.get("C") == "KS":
        return "07" + kennung[3:6] + "000"
    return "07" + kennung[3:6] + kennung[8:11]


def _rlp_zielkennung(text: str | None) -> str:
    """Zusammenlegungsziel: 13 Stellen Gebiet plus fünf Stellen Stimmbezirk."""
    kennung = _kennung(text)
    if kennung.isdigit() and len(kennung) >= 18:
        return kennung[:13]
    return kennung


def _rlp_gebiet(zeile: dict[str, str]) -> dict | None:
    gueltig = _ganzzahl(zeile.get("DP")) or 0
    if gueltig <= 0:
        return None
    stimmen = {name: _ganzzahl(zeile.get(spalte)) or 0 for spalte, name in RLP_PARTEISPALTEN.items()}
    if sum(stimmen.values()) != gueltig:
        raise Fehler(
            f"RLP: Parteistimmen in {zeile.get('D')!r} ergeben {sum(stimmen.values())}, "
            f"erwartet waren {gueltig}."
        )
    parteien = {
        name: round(anzahl / gueltig * 100.0, 1)
        for name, anzahl in sorted(stimmen.items(), key=lambda paar: -paar[1])
        if anzahl > 0
    }
    beteiligung = _zahl(zeile.get("M"))
    return {
        "name": (zeile.get("D") or "").strip(),
        "beteiligung": round(beteiligung, 1) if beteiligung is not None and 0 <= beteiligung <= 100 else None,
        "parteien": parteien,
    }


def rlp_zeilen_auswerten(zeilen: list[dict[str, str]], vollstaendig: bool = False) -> dict:
    """Amtliche Gesamtzeilen für Gemeinden lesen und Zusammenlegungen kenntlich übernehmen."""
    ausgewaehlt = [
        z
        for z in zeilen
        if (_ganzzahl(z.get("B")) == 0 and z.get("E") == "G" and z.get("C") in {"GD", "VF", "KS"})
    ]
    if vollstaendig and not 2200 <= len(ausgewaehlt) <= 2400:
        raise Fehler(f"RLP: Erwartet wurden etwa 2.300 Gemeindezeilen, gefunden wurden {len(ausgewaehlt)}.")

    nach_id = {_kennung(z.get("A")): z for z in ausgewaehlt}
    if len(nach_id) != len(ausgewaehlt):
        raise Fehler("RLP: Gemeinde-Identifikationsschlüssel sind nicht eindeutig.")

    gebiete: dict[str, dict] = {}
    for zeile in ausgewaehlt:
        gebiet = _rlp_gebiet(zeile)
        if gebiet is None:
            ziel_id = _rlp_zielkennung(zeile.get("HO"))
            ziel = nach_id.get(ziel_id)
            ziel_gebiet = _rlp_gebiet(ziel) if ziel else None
            if ziel_gebiet is None:
                raise Fehler(f"RLP: Zusammenlegung für {zeile.get('D')!r} hat kein auswertbares Ziel.")
            gebiet = {
                "name": (zeile.get("D") or "").strip(),
                "beteiligung": ziel_gebiet["beteiligung"],
                "parteien": dict(ziel_gebiet["parteien"]),
                "hinweis": f"Gemeinsam ausgewiesenes Ergebnis mit {ziel_gebiet['name']}",
                "zusammengelegt_mit": _rlp_ags(ziel),
            }

        ags = _rlp_ags(zeile)
        if ags in gebiete:
            raise Fehler(f"RLP: AGS {ags} wurde mehrfach erzeugt.")
        gebiete[ags] = gebiet

    if len(gebiete) != len(ausgewaehlt):
        raise Fehler("RLP: Nicht alle Gemeindezeilen konnten übernommen werden.")
    return gebiete


def rlp_xlsx_auswerten(datei: Path) -> dict:
    zeilen = _xlsx_zeilen(datei)
    kopf_index = next(
        (i for i, z in enumerate(zeilen) if (z.get("A") or "").strip() == "Identifikationsschlüssel"),
        None,
    )
    if kopf_index is None:
        raise Fehler("RLP: Keine XLSX-Kopfzeile gefunden.")
    kopf = zeilen[kopf_index]
    if "gültige Landesstimmen" not in (kopf.get("DP") or "").replace("\n", " "):
        raise Fehler("RLP: Die Spalte DP enthält nicht die gültigen Landesstimmen.")
    for spalte, name in RLP_PARTEISPALTEN.items():
        if (kopf.get(spalte) or "").strip().casefold() != name.casefold():
            raise Fehler(f"RLP: Spalte {spalte} ist nicht {name!r}.")
    return rlp_zeilen_auswerten(zeilen[kopf_index + 1 :], vollstaendig=True)


# ------------------------------------------------------------------- Sachsen 2024


SACHSEN_2024_BLATT = "LW24_endgErgebnisse_GE&TG"

# Spaltenbuchstabe -> (erwarteter Kopfzeilentext, Anzeigename). Die amtliche Datei führt jede
# Partei zweimal: `_1` ist die Wahlkreisstimme (Direktkandidat, für uns irrelevant), `_2` ist die
# Landesstimme (Listenstimme) und entspricht fachlich der Bundes-Zweitstimme. `V-Partei3` und `WU`
# werden auf dieselbe Schreibweise wie anderswo im Projekt normiert.
SACHSEN_PARTEISPALTEN: dict[str, tuple[str, str]] = {
    "AS": ("CDU_2", "CDU"),
    "AT": ("AfD_2", "AfD"),
    "AU": ("DIE LINKE_2", "DIE LINKE"),
    "AV": ("GRÜNE_2", "GRÜNE"),
    "AW": ("SPD_2", "SPD"),
    "AX": ("FDP_2", "FDP"),
    "AY": ("FREIE WÄHLER_2", "FREIE WÄHLER"),
    "AZ": ("Die PARTEI_2", "Die PARTEI"),
    "BA": ("PIRATEN_2", "PIRATEN"),
    "BB": ("ÖDP_2", "ÖDP"),
    "BC": ("BüSo_2", "BüSo"),
    "BD": ("TIERSCHUTZ hier!_2", "TIERSCHUTZ hier!"),
    "BE": ("dieBasis_2", "dieBasis"),
    "BF": ("Bündnis C_2", "Bündnis C"),
    "BG": ("BÜNDNIS DEUTSCHLAND_2", "BÜNDNIS DEUTSCHLAND"),
    "BH": ("BSW_2", "BSW"),
    "BI": ("FREIE SACHSEN_2", "FREIE SACHSEN"),
    "BJ": ("V-Partei3_2", "V-Partei³"),
    "BK": ("WU_2", "WerteUnion"),
}


# Chemnitz, Dresden, Leipzig und Zwickau liefert die amtliche Datei ausschliesslich als mehrere
# Teilgemeinde-Zeilen (je Wahlkreis-Anteil), ohne eine zusammenfassende Gemeindezeile. Ihre
# Teilgemeinden werden deshalb aufsummiert; die Namen folgen der amtlichen Schreibweise, die die
# übrigen kreisfreien Städte in derselben Datei bereits verwenden.
SACHSEN_NUR_TEILGEMEINDEN = {
    "14511000": "Chemnitz, Stadt",
    "14612000": "Dresden, Stadt",
    "14713000": "Leipzig, Stadt",
    "14524330": "Zwickau, Stadt",
}


def _sachsen_gebiet(name: str, zeilen: list[dict[str, str]]) -> dict:
    """Eine oder mehrere Zeilen (Gemeinde oder ihre Teilgemeinden) zu einem Ergebnis verdichten."""
    gueltig = sum(_ganzzahl(z.get("AR")) or 0 for z in zeilen)
    if gueltig <= 0 or not name:
        raise Fehler(f"Sachsen: kein auswertbares Ergebnis für {name!r}.")
    stimmen: dict[str, int] = defaultdict(int)
    for zeile in zeilen:
        for spalte, (_, anzeigename) in SACHSEN_PARTEISPALTEN.items():
            stimmen[anzeigename] += _ganzzahl(zeile.get(spalte)) or 0
    if sum(stimmen.values()) != gueltig:
        raise Fehler(
            f"Sachsen: Parteistimmen in {name!r} ergeben {sum(stimmen.values())}, "
            f"erwartet waren {gueltig} gültige Listenstimmen."
        )
    parteien = {
        anzeigename: round(anzahl / gueltig * 100.0, 1)
        for anzeigename, anzahl in sorted(stimmen.items(), key=lambda paar: -paar[1])
        if anzahl > 0
    }
    gebiet: dict = {"name": name, "beteiligung": None, "parteien": parteien}

    # Einige Gemeinden führen die Briefwahl für ihre Nachbargemeinden mit durch. Deren Briefwähler
    # zählen dann hier mit, obwohl sie hier nicht wahlberechtigt sind. Das verfälscht sowohl die
    # Wahlbeteiligung als auch die Parteianteile, und zwar unabhängig davon, wie stark. Deshalb
    # wird jede betroffene Gemeinde gekennzeichnet, nicht nur die auffälligen.
    briefwahl_fuer_andere = [z for z in zeilen if (z.get("H") or "").strip().upper() == "J"]
    if briefwahl_fuer_andere:
        gebiet["hinweis"] = next(
            ((z.get("I") or "").strip() for z in briefwahl_fuer_andere if (z.get("I") or "").strip()),
            "Gemeinde führte die Briefwahl auch für mindestens eine weitere Gemeinde durch.",
        ) + " Die Stimmen dieser Briefwähler zählen hier mit."

    wahlberechtigte = sum(_ganzzahl(z.get("M")) or 0 for z in zeilen)
    waehler = sum(_ganzzahl(z.get("N")) or 0 for z in zeilen)
    if wahlberechtigte > 0:
        wert = round(waehler / wahlberechtigte * 100.0, 1)
        # In drei Gemeinden übersteigen die mitgezählten fremden Briefwähler die eigene
        # Wahlberechtigtenzahl so deutlich, dass die amtliche Datei bis zu 131,5 Prozent ausweist.
        # Das ist keine Wahlbeteiligung mehr; lieber keine Angabe als eine unmögliche Zahl.
        gebiet["beteiligung"] = wert if 0.0 <= wert <= 100.0 else None
    return gebiet


def sachsen_zeilen_auswerten(zeilen: list[dict[str, str]]) -> dict:
    """Amtliche Gemeindezeilen (Ebene ``GE``) lesen und die vier reinen Teilgemeinde-Städte aus
    ihren Teilgemeinden (Ebene ``TG``) zusammensetzen, weil unser Schlüssel überall der
    achtstellige Gemeinde-AGS ist, nicht die neunstellige Teilgemeindenummer."""
    ge = [z for z in zeilen if z.get("E") == "GE"]
    tg = [z for z in zeilen if z.get("E") == "TG"]
    # Sachsen hatte zur Wahl 2024 rund 415 Gemeinden; ein weiter Rahmen fängt künftige
    # Gebietsreformen ab, ohne einen abgebrochenen Export unbemerkt durchzulassen.
    if not 380 <= len(ge) <= 440:
        raise Fehler(f"Sachsen: Erwartet wurden rund 415 Gemeindezeilen, gefunden wurden {len(ge)}.")

    gebiete: dict[str, dict] = {}
    for zeile in ge:
        ags = (zeile.get("F") or "").strip()
        if not re.fullmatch(r"\d{8}", ags) or not ags.startswith("14"):
            raise Fehler(f"Sachsen: ungültiger Gemeinde-AGS {zeile.get('F')!r}.")
        if ags in gebiete:
            raise Fehler(f"Sachsen: AGS {ags} wurde mehrfach erzeugt.")
        gebiete[ags] = _sachsen_gebiet((zeile.get("G") or "").strip(), [zeile])

    teilgemeinden: dict[str, list[dict[str, str]]] = defaultdict(list)
    for zeile in tg:
        ags9 = (zeile.get("F") or "").strip()
        if not re.fullmatch(r"\d{9}", ags9) or not ags9.startswith("14"):
            raise Fehler(f"Sachsen: ungültiger Teilgemeinde-AGS {zeile.get('F')!r}.")
        teilgemeinden[ags9[:8]].append(zeile)

    unerwartet = set(teilgemeinden) - set(SACHSEN_NUR_TEILGEMEINDEN)
    if unerwartet:
        raise Fehler(
            "Sachsen: unbekannte Teilgemeinde-Städte ohne Gemeindezeile: " + ", ".join(sorted(unerwartet))
        )
    for ags, name in SACHSEN_NUR_TEILGEMEINDEN.items():
        if ags in gebiete:
            raise Fehler(f"Sachsen: {name} hat sowohl eine Gemeinde- als auch Teilgemeindezeilen.")
        if ags not in teilgemeinden:
            raise Fehler(f"Sachsen: keine Teilgemeinden für {name} ({ags}) gefunden.")
        gebiete[ags] = _sachsen_gebiet(name, teilgemeinden[ags])

    return gebiete


def sachsen_xlsx_auswerten(datei: Path) -> dict:
    zeilen = _xlsx_zeilen(datei, SACHSEN_2024_BLATT)
    kopf_index = next(
        (i for i, z in enumerate(zeilen) if (z.get("F") or "").strip() == "AGS"),
        None,
    )
    if kopf_index is None:
        raise Fehler("Sachsen: Keine XLSX-Kopfzeile gefunden.")
    kopf = zeilen[kopf_index]
    if (kopf.get("E") or "").strip() != "Ebene":
        raise Fehler("Sachsen: Spalte E ist nicht die Gemeinde-/Ortsteil-Ebene.")
    if (kopf.get("AR") or "").strip() != "gültige_2":
        raise Fehler("Sachsen: Spalte AR enthält nicht die gültigen Landesstimmen.")
    if (kopf.get("BM") or "").strip() != "Wahlbeteiligung":
        raise Fehler("Sachsen: Spalte BM enthält nicht die Wahlbeteiligung.")
    for spalte, (erwartet, _) in SACHSEN_PARTEISPALTEN.items():
        if (kopf.get(spalte) or "").strip() != erwartet:
            raise Fehler(f"Sachsen: Spalte {spalte} ist nicht {erwartet!r}.")
    return sachsen_zeilen_auswerten(zeilen[kopf_index + 1 :])


# ------------------------------------------------------------- Sachsen-Anhalt 2021

# Amtlicher Kopfzeilentext (mit dem originalen Leerzeichen am Ende) -> Anzeigename. Nur die
# Zweitstimmen-/Landeslistenspalten (F0x) - die Erststimmen (D0x, Wahlkreiskandidat) bleiben
# unberücksichtigt, genau wie die Wahlkreisstimme bei RLP/Sachsen.
SACHSENANHALT_PARTEISPALTEN: dict[str, str] = {
    "F01 - CDU ": "CDU",
    "F02 - AfD ": "AfD",
    "F03 - DIE LINKE ": "DIE LINKE",
    "F04 - SPD ": "SPD",
    "F05 - GRÜNE ": "GRÜNE",
    "F06 - FDP ": "FDP",
    "F07 - FREIE WÄHLER ": "FREIE WÄHLER",
    "F08 - NPD ": "NPD",
    "F09 - Tierschutzpartei ": "Tierschutzpartei",
    "F10 - Tierschutzallianz ": "Tierschutzallianz",
    "F11 - LKR ": "LKR",
    "F12 - Die PARTEI ": "Die PARTEI",
    "F13 - Gartenpartei ": "Gartenpartei",
    "F14 - FBM ": "FBM",
    "F15 - TIERSCHUTZ hier! ": "TIERSCHUTZ hier!",
    "F16 - dieBasis ": "dieBasis",
    "F19 - Klimaliste ST ": "Klimaliste ST",
    "F21 - ÖDP ": "ÖDP",
    "F22 - Die Humanisten ": "Die Humanisten",
    "F23 - Gesundheitsforschung ": "Gesundheitsforschung",
    "F24 - PIRATEN ": "PIRATEN",
    "F25 - WiR2020 ": "WiR2020",
}

SACHSENANHALT_PFLICHTSPALTEN = (
    "Satzart",
    "Schlüsselnummer",
    "Name",
    "A - Wahlberechtigte",
    "B - Wähler",
    "F - Gültige Zweitstimmen",
    *SACHSENANHALT_PARTEISPALTEN,
)


def _sachsenanhalt_gebiet(zeile: dict[str, str]) -> tuple[str, dict]:
    ags = (zeile.get("Schlüsselnummer") or "").strip()
    if not re.fullmatch(r"\d{8}", ags) or not ags.startswith("15"):
        raise Fehler(f"Sachsen-Anhalt: ungültiger Gemeinde-AGS {zeile.get('Schlüsselnummer')!r}.")
    name = (zeile.get("Name") or "").strip()
    gueltig = _ganzzahl(zeile.get("F - Gültige Zweitstimmen"))
    if not gueltig or gueltig <= 0 or not name:
        raise Fehler(f"Sachsen-Anhalt: kein auswertbares Ergebnis für {name!r} ({ags}).")

    stimmen = {
        anzeigename: _ganzzahl(zeile.get(spalte)) or 0
        for spalte, anzeigename in SACHSENANHALT_PARTEISPALTEN.items()
    }
    if sum(stimmen.values()) != gueltig:
        raise Fehler(
            f"Sachsen-Anhalt: Parteistimmen in {name!r} ergeben {sum(stimmen.values())}, "
            f"erwartet waren {gueltig} gültige Zweitstimmen."
        )
    parteien = {
        anzeigename: round(anzahl / gueltig * 100.0, 1)
        for anzeigename, anzahl in sorted(stimmen.items(), key=lambda paar: -paar[1])
        if anzahl > 0
    }

    wahlberechtigte = _ganzzahl(zeile.get("A - Wahlberechtigte")) or 0
    waehler = _ganzzahl(zeile.get("B - Wähler")) or 0
    beteiligung = round(waehler / wahlberechtigte * 100.0, 1) if wahlberechtigte > 0 else None
    if beteiligung is not None and not 0.0 <= beteiligung <= 100.0:
        beteiligung = None

    return ags, {"name": name, "beteiligung": beteiligung, "parteien": parteien}


def sachsenanhalt_zeilen_auswerten(zeilen: list[dict[str, str]]) -> dict:
    gem = [z for z in zeilen if (z.get("Satzart") or "").strip() == "GEM"]
    # Sachsen-Anhalt hatte zur Wahl 2021 218 Gemeinden; ein weiter Rahmen fängt künftige
    # Gebietsreformen ab, ohne einen abgebrochenen Export unbemerkt durchzulassen.
    if not 190 <= len(gem) <= 240:
        raise Fehler(f"Sachsen-Anhalt: Erwartet wurden rund 218 Gemeindezeilen, gefunden wurden {len(gem)}.")

    gebiete: dict[str, dict] = {}
    for zeile in gem:
        ags, gebiet = _sachsenanhalt_gebiet(zeile)
        if ags in gebiete:
            raise Fehler(f"Sachsen-Anhalt: AGS {ags} wurde mehrfach erzeugt.")
        gebiete[ags] = gebiet
    return gebiete


def sachsenanhalt_csv_auswerten(datei: Path) -> dict:
    # Amtliche Datei ist ISO-8859-1/cp1252-kodiert (Windows-Herkunft), nicht UTF-8 wie GERDA.
    with datei.open(encoding="cp1252", newline="") as eingabe:
        leser = csv.DictReader(eingabe, delimiter=";")
        felder = leser.fieldnames or []
        fehlend = [spalte for spalte in SACHSENANHALT_PFLICHTSPALTEN if spalte not in felder]
        if fehlend:
            raise Fehler("Sachsen-Anhalt: Spalten fehlen: " + ", ".join(fehlend))
        zeilen = list(leser)
    return sachsenanhalt_zeilen_auswerten(zeilen)


# ------------------------------------------------------------------- Berlin 2023

BERLIN_2023_BLATT = "AGH_W2"

# Feste Nicht-Parteispalten (Einzelbuchstaben A-R) - alles danach (S, T, ..., AA, AB, ...) ist eine
# Parteispalte, deren Kopfzeilentext direkt der Anzeigename ist (anders als bei Sachsen keine
# `_1`/`_2`-Suffix-Übersetzung nötig). Dynamisch statt fest eingetippter Spaltenliste: eine
# Verschiebung durch eine neue/entfallene Partei zur nächsten Wahl bricht den Parser dann nicht.
BERLIN_NICHT_PARTEISPALTEN = frozenset("ABCDEFGHIJKLMNOPQR")


def _berlin_parteispalten(kopf: dict[str, str]) -> dict[str, str]:
    return {
        spalte: name.strip()
        for spalte, name in kopf.items()
        if spalte not in BERLIN_NICHT_PARTEISPALTEN and (name or "").strip()
    }


def _berlin_gebiet(bezirksnummer: str, bezirksname: str, zeilen: list[dict[str, str]], parteispalten: dict[str, str]) -> dict:
    # Ein Bezirk besteht aus Urnen- ("W") und Briefwahlbezirken ("B") als eigenen Zeilen, keine
    # Überschneidung - beide zählen zum Bezirksergebnis. "Wahlberechtigte insgesamt" steht nur bei
    # den Urnenwahlbezirken (Briefwähler sind über ihren Urnenwahlbezirk schon mitgezählt, ihre
    # eigene Zeile führt dort 0), eine Summe über alle Zeilen ist deshalb ohne Sonderfall korrekt.
    gueltig = sum(_ganzzahl(z.get("Q")) or 0 for z in zeilen)
    if gueltig <= 0:
        raise Fehler(f"Berlin: kein auswertbares Ergebnis für {bezirksname!r}.")

    stimmen: dict[str, int] = defaultdict(int)
    for zeile in zeilen:
        for spalte, name in parteispalten.items():
            stimmen[name] += _ganzzahl(zeile.get(spalte)) or 0
    if sum(stimmen.values()) != gueltig:
        raise Fehler(
            f"Berlin: Parteistimmen in {bezirksname!r} ergeben {sum(stimmen.values())}, "
            f"erwartet waren {gueltig} gültige Zweitstimmen."
        )
    parteien = {
        name: round(anzahl / gueltig * 100.0, 1)
        for name, anzahl in sorted(stimmen.items(), key=lambda paar: -paar[1])
        if anzahl > 0
    }

    wahlberechtigte = sum(_ganzzahl(z.get("K")) or 0 for z in zeilen)
    waehlende = sum(_ganzzahl(z.get("O")) or 0 for z in zeilen)
    beteiligung = round(waehlende / wahlberechtigte * 100.0, 1) if wahlberechtigte > 0 else None
    if beteiligung is not None and not 0.0 <= beteiligung <= 100.0:
        beteiligung = None

    return {"name": bezirksname, "beteiligung": beteiligung, "parteien": parteien}


def berlin_zeilen_auswerten(zeilen: list[dict[str, str]]) -> dict:
    """Amtliche Wahlbezirkszeilen (Ebene Urnen-/Briefwahlbezirk) zu den zwölf Berliner Bezirken
    verdichten - dieselbe Zwölf-AGS-Ebene wie GERDAs Berlin-Eintrag, `Land(2) + 0 + Bezirk(2) +
    000` (z. B. Mitte = 11001000), weil Berlins Bezirke administrativ auf Kreisebene stehen."""
    kopf_index = next(
        (i for i, z in enumerate(zeilen) if (z.get("C") or "").strip() == "Bezirksnummer"),
        None,
    )
    if kopf_index is None:
        raise Fehler("Berlin: Keine XLSX-Kopfzeile gefunden.")
    kopf = zeilen[kopf_index]
    if (kopf.get("Q") or "").strip() != "Gültige Stimmen":
        raise Fehler("Berlin: Spalte Q ist nicht die gültigen Zweitstimmen.")
    parteispalten = _berlin_parteispalten(kopf)
    if len(parteispalten) < 10:
        raise Fehler(f"Berlin: nur {len(parteispalten)} Parteispalten gefunden, erwartet wurden deutlich mehr.")

    zeilen_je_bezirk: dict[str, list[dict[str, str]]] = defaultdict(list)
    namen: dict[str, str] = {}
    for zeile in zeilen[kopf_index + 1 :]:
        bezirksnummer = (zeile.get("C") or "").strip()
        if not re.fullmatch(r"\d{2}", bezirksnummer):
            continue
        zeilen_je_bezirk[bezirksnummer].append(zeile)
        namen.setdefault(bezirksnummer, (zeile.get("D") or "").strip())

    if len(zeilen_je_bezirk) != 12:
        raise Fehler(f"Berlin: 12 Bezirke erwartet, gefunden wurden {len(zeilen_je_bezirk)}.")

    gebiete: dict[str, dict] = {}
    for bezirksnummer, bezirkszeilen in zeilen_je_bezirk.items():
        ags = f"110{bezirksnummer}000"
        gebiete[ags] = _berlin_gebiet(bezirksnummer, namen[bezirksnummer], bezirkszeilen, parteispalten)
    return gebiete


def berlin_xlsx_auswerten(datei: Path) -> dict:
    zeilen = _xlsx_zeilen(datei, BERLIN_2023_BLATT)
    return berlin_zeilen_auswerten(zeilen)


# -------------------------------------------------------- Mecklenburg-Vorpommern


def _ohne_kopftext(eingabe: Iterable[str]) -> Iterator[str]:
    """Die amtlichen LAIV-MV-CSVs beginnen mit vier Titel-/Hinweiszeilen und einer Leerzeile vor
    der echten Kopfzeile - hier an ihrer ersten Spalte "Berechnungsdatum" erkannt statt eine feste
    Zeilenzahl anzunehmen, die bei einer künftigen Exportvariante nicht mehr stimmen müsste."""
    gefunden = False
    for zeile in eingabe:
        if not gefunden:
            if not zeile.startswith("Berechnungsdatum;"):
                continue
            gefunden = True
        yield zeile
    if not gefunden:
        raise Fehler("Mecklenburg-Vorpommern: keine Kopfzeile (Berechnungsdatum;...) gefunden.")


# Alle drei amtlichen CSVs des LAIV-MV (Landesamt für innere Verwaltung) teilen dieses Grundmuster:
# Windows-1252-kodiert, Semikolon-getrennt, deutsche Dezimalkommas, eine Kopfzeile mit fester
# Spaltenmenge plus einer variablen Anzahl Parteispalten am Ende. "Ausgabe" unterscheidet je Zeile
# absolute Stimmenzahl ("A") von Prozent ("P") - wir lesen nur "A" und rechnen die Prozente selbst
# aus (wie bei allen anderen Ländern hier), das ergibt nebenbei die Summenprüfung gegen "Gültige
# Stimmen" gratis mit. Parteispalten werden dynamisch erkannt (wie bei Berlin) statt fest
# eingetippt - die Kommunalwahl-Datei hat über siebzig echte örtliche Wählergruppennamen
# (z. B. "Wählergemeinschaft Wittenhagen", "Bürger für Stralsund"), genau das GERDA sonst als
# "Sonstige" zusammenfasst (siehe Issue #10).
MECKLENBURG_NICHT_PARTEISPALTEN = frozenset(
    {
        "Berechnungsdatum",
        "Ausgabe",
        "Kreis",
        "Kreisname",
        "Amt",
        "Amtsname",
        "Gemeinde",
        "Gemeindename",
        "Wahlbezirke insg.",
        "Erf. Wahlbezirke",
        "Wahlberechtigte",
        "Wähler",
        "Wahlbeteiligung",
        "Erst-/Zweitstimme",
        "Ungültige Stimmen",
        "Gültige Stimmen",
    }
)

# Bei amtsangehörigen Gemeinden (die meisten kleinen MV-Gemeinden gehören zu einem "Amt", einer
# gemeinsamen Verwaltung mehrerer Gemeinden) weist die Quelle die Briefwahl nicht je Gemeinde aus,
# sondern gepoolt auf Amtsebene in einer eigenen Pseudo-Zeile mit Gemeindename "Briefwahl <Amt>".
# Bei der Landtagswahl betrifft das praktisch alle amtsangehörigen Gemeinden, bei der Kommunalwahl
# nur die Minderheit der Fälle, in denen die Briefwahl nicht in ein Urnenwahlbezirk-Ergebnis
# eingerechnet werden konnte. Entscheidung: transparent kennzeichnen statt Gemeinden wegzulassen
# oder Zahlen zu erfinden (analog zur Sachsen-Briefwahl-Kennzeichnung, siehe _sachsen_gebiet).
MECKLENBURG_BRIEFWAHL_HINWEIS = (
    "Nur Urnenwahl - die Briefwahl dieser amtsangehörigen Gemeinde wird von der Quelle nur "
    "gepoolt auf Amtsebene ausgewiesen, nicht einzeln je Gemeinde."
)


def _mecklenburg_parteispalten(felder: list[str]) -> list[str]:
    spalten = [f for f in felder if f not in MECKLENBURG_NICHT_PARTEISPALTEN]
    if len(spalten) < 5:
        raise Fehler(f"Mecklenburg-Vorpommern: nur {len(spalten)} Parteispalten gefunden.")
    return spalten


def _mecklenburg_amtsangehoerige(zeilen: list[dict[str, str]]) -> set[tuple[str, str]]:
    """(Kreis, Amt)-Paare, für die es eine gepoolte "Briefwahl <Amt>"-Zeile gibt."""
    return {
        (zeile.get("Kreis", ""), zeile.get("Amt", ""))
        for zeile in zeilen
        if (zeile.get("Gemeindename") or "").startswith("Briefwahl ")
    }


def _mecklenburg_stimmen_auswerten(
    zeile: dict[str, str], parteispalten: list[str], name: str, bezeichnung: str
) -> tuple[dict[str, float], float | None]:
    gueltig = _ganzzahl(zeile.get("Gültige Stimmen"))
    if not gueltig or gueltig <= 0:
        raise Fehler(f"Mecklenburg-Vorpommern: kein auswertbares Ergebnis für {bezeichnung!r}.")

    stimmen = {spalte: _ganzzahl(zeile.get(spalte)) or 0 for spalte in parteispalten}
    if sum(stimmen.values()) != gueltig:
        raise Fehler(
            f"Mecklenburg-Vorpommern: Parteistimmen in {bezeichnung!r} ergeben "
            f"{sum(stimmen.values())}, erwartet waren {gueltig} gültige Stimmen."
        )
    parteien = {
        anzeigename: round(anzahl / gueltig * 100.0, 1)
        for anzeigename, anzahl in sorted(stimmen.items(), key=lambda paar: -paar[1])
        if anzahl > 0
    }

    wahlberechtigte = _ganzzahl(zeile.get("Wahlberechtigte")) or 0
    waehler = _ganzzahl(zeile.get("Wähler")) or 0
    beteiligung = round(waehler / wahlberechtigte * 100.0, 1) if wahlberechtigte > 0 else None
    if beteiligung is not None and not 0.0 <= beteiligung <= 100.0:
        beteiligung = None
    return parteien, beteiligung


def _mecklenburg_gemeinde_gebiet(
    zeile: dict[str, str],
    parteispalten: list[str],
    amtsangehoerige: set[tuple[str, str]],
) -> tuple[str, dict]:
    ags = (zeile.get("Gemeinde") or "").strip()
    if not re.fullmatch(r"\d{8}", ags) or not ags.startswith("13"):
        raise Fehler(f"Mecklenburg-Vorpommern: ungültiger Gemeinde-AGS {zeile.get('Gemeinde')!r}.")
    name = (zeile.get("Gemeindename") or "").strip()
    if not name:
        raise Fehler(f"Mecklenburg-Vorpommern: Gemeinde {ags} ohne Namen.")

    parteien, beteiligung = _mecklenburg_stimmen_auswerten(zeile, parteispalten, name, f"{name} ({ags})")
    gebiet = {"name": name, "beteiligung": beteiligung, "parteien": parteien}
    if (zeile.get("Kreis", ""), zeile.get("Amt", "")) in amtsangehoerige:
        gebiet["hinweis"] = MECKLENBURG_BRIEFWAHL_HINWEIS
    return ags, gebiet


def _mecklenburg_gemeinden_zeilen_auswerten(zeilen: list[dict[str, str]], erwartete_zeilen: range) -> dict:
    treffer = [z for z in zeilen if (z.get("Ausgabe") or "").strip() == "A"]
    if not treffer:
        raise Fehler("Mecklenburg-Vorpommern: keine Zeilen mit Ausgabe=A gefunden.")
    parteispalten = _mecklenburg_parteispalten(list(treffer[0].keys()))
    if "Erst-/Zweitstimme" in treffer[0]:
        treffer = [z for z in treffer if (z.get("Erst-/Zweitstimme") or "").strip() == "2"]

    amtsangehoerige = _mecklenburg_amtsangehoerige(treffer)
    echte = [z for z in treffer if not (z.get("Gemeindename") or "").startswith("Briefwahl ")]
    if len(echte) not in erwartete_zeilen:
        raise Fehler(
            f"Mecklenburg-Vorpommern: {erwartete_zeilen.start} bis {erwartete_zeilen.stop - 1} "
            f"Gemeindezeilen erwartet, gefunden wurden {len(echte)}."
        )

    gebiete: dict[str, dict] = {}
    for zeile in echte:
        ags, gebiet = _mecklenburg_gemeinde_gebiet(zeile, parteispalten, amtsangehoerige)
        if ags in gebiete:
            raise Fehler(f"Mecklenburg-Vorpommern: AGS {ags} wurde mehrfach erzeugt.")
        gebiete[ags] = gebiet
    return gebiete


def mecklenburg_landtag_zeilen_auswerten(zeilen: list[dict[str, str]]) -> dict:
    # 2021 hatte Mecklenburg-Vorpommern 718 Gemeinden; ein weiter Rahmen fängt künftige
    # Gebietsreformen ab, ohne einen abgebrochenen Export unbemerkt durchzulassen.
    return _mecklenburg_gemeinden_zeilen_auswerten(zeilen, range(650, 800))


def mecklenburg_landtag_csv_auswerten(datei: Path) -> dict:
    with datei.open(encoding="cp1252", newline="") as eingabe:
        zeilen = list(csv.DictReader(_ohne_kopftext(eingabe), delimiter=";"))
    return mecklenburg_landtag_zeilen_auswerten(zeilen)


def mecklenburg_kommunal_zeilen_auswerten(zeilen: list[dict[str, str]]) -> dict:
    return _mecklenburg_gemeinden_zeilen_auswerten(zeilen, range(650, 800))


def mecklenburg_kommunal_csv_auswerten(datei: Path) -> dict:
    with datei.open(encoding="cp1252", newline="") as eingabe:
        zeilen = list(csv.DictReader(_ohne_kopftext(eingabe), delimiter=";"))
    return mecklenburg_kommunal_zeilen_auswerten(zeilen)


def mecklenburg_kreistag_zeilen_auswerten(zeilen: list[dict[str, str]]) -> dict:
    treffer = [z for z in zeilen if (z.get("Ausgabe") or "").strip() == "A"]
    if not treffer:
        raise Fehler("Mecklenburg-Vorpommern (Kreistag): keine Zeilen mit Ausgabe=A gefunden.")
    parteispalten = _mecklenburg_parteispalten(list(treffer[0].keys()))

    gebiete: dict[str, dict] = {}
    for zeile in treffer:
        kreis = (zeile.get("Kreis") or "").strip()
        if kreis == "99":
            continue  # Landesergebnis, kein Gebiet
        if not re.fullmatch(r"\d{1,3}", kreis):
            raise Fehler(f"Mecklenburg-Vorpommern (Kreistag): ungültiger Kreis-Code {kreis!r}.")
        kreisschluessel = "13" + kreis.zfill(3)
        name = (zeile.get("Kreisname") or "").strip()
        if not name:
            raise Fehler(f"Mecklenburg-Vorpommern (Kreistag): Kreis {kreisschluessel} ohne Namen.")
        parteien, beteiligung = _mecklenburg_stimmen_auswerten(zeile, parteispalten, name, name)
        if kreisschluessel in gebiete:
            raise Fehler(f"Mecklenburg-Vorpommern (Kreistag): {kreisschluessel} wurde mehrfach erzeugt.")
        gebiete[kreisschluessel] = {"name": name, "beteiligung": beteiligung, "parteien": parteien}

    if len(gebiete) != 8:
        raise Fehler(f"Mecklenburg-Vorpommern (Kreistag): 8 Kreise/kreisfreie Städte erwartet, gefunden wurden {len(gebiete)}.")
    return gebiete


def mecklenburg_kreistag_csv_auswerten(datei: Path) -> dict:
    with datei.open(encoding="cp1252", newline="") as eingabe:
        zeilen = list(csv.DictReader(_ohne_kopftext(eingabe), delimiter=";"))
    return mecklenburg_kreistag_zeilen_auswerten(zeilen)


# ------------------------------------------------------------------------- Bayern 2026 (Kreistagswahl)

# Das Bayerische Landesamt für Statistik veröffentlicht die Kreistagswahl-Endergebnisse als
# strukturiertes XML (mit eigenem XSD) statt fester Parteispalten - eine <Wahlvorschlag>-Zeile je
# tatsächlich angetretener Liste mit ihrem echten Namen, dadurch bleiben auch die zahlreichen
# örtlichen Wählergruppen und Kreisverbände (z. B. "Bürgerliste Reichenhall",
# "FREIE WÄHLER/Freie Wähler Kreisverband Dachau e.V.") erhalten statt in GERDAs Kreistag-Gruppen
# (KREISTAG_GRUPPEN) unter "Sonstige" zu verschwinden. Bayerns Kommunalwahlrecht erlaubt Kumulieren
# und Panaschieren; die Quelle liefert dafür bereits gewichtete Stimmen (`Gewichtete_Stimmen_*`),
# die für die Sitzverteilung maßgeblich sind - genau diese Gewichtung übernimmt auch dieser Parser,
# statt eigene Rohstimmen zu zählen. Eine Liste, die 2026 nicht mehr angetreten ist, aber 2020 noch
# existierte, taucht nur mit einer Verlaufszeile ohne aktuelle Stimmen-/Sitzangaben auf (kein
# `Gewichtete_Stimmen_absolut`-Element) - das zählt als 0 aktuelle Stimmen, nicht als Fehler.
BAYERN_KREISTAG_URL = "https://kommunalwahl2026.bayern.de/downloads/gremienwahl/Kommunalwahl_Gremien_Landkreise.xml"


def _bayern_wahlvorschlag_stimmen(wahlvorschlag) -> int:
    element = wahlvorschlag.find("Gewichtete_Stimmen_absolut")
    if element is None or not (element.text or "").strip():
        return 0
    wert = _ganzzahl(element.text)
    return wert if wert is not None else 0


def _bayern_kreistag_gebiet(regionaleinheit) -> tuple[str, dict]:
    schluessel = (regionaleinheit.get("Schluesselnummer") or "").strip()
    if not re.fullmatch(r"\d{1,3}", schluessel):
        raise Fehler(f"Bayern (Kreistag): ungültige Schlüsselnummer {schluessel!r}.")
    kreisschluessel = "09" + schluessel.zfill(3)

    wahl = regionaleinheit.find("Wahl[@Bezeichnung='Kreistag']")
    if wahl is None:
        raise Fehler(f"Bayern (Kreistag): keine Kreistagswahl für {kreisschluessel} gefunden.")

    angaben = wahl.find("Allgemeine_Angaben")
    name = (angaben.findtext("Name_der_Regionaleinheit") or "").strip() if angaben is not None else ""
    if not name:
        raise Fehler(f"Bayern (Kreistag): Landkreis {kreisschluessel} ohne Namen.")

    wahlberechtigte = _ganzzahl(angaben.findtext("Stimmberechtigte")) if angaben is not None else None
    waehler = _ganzzahl(angaben.findtext("Waehler")) if angaben is not None else None
    beteiligung = None
    if wahlberechtigte and waehler is not None and wahlberechtigte > 0:
        beteiligung = round(waehler / wahlberechtigte * 100.0, 1)
        if not 0.0 <= beteiligung <= 100.0:
            beteiligung = None

    gueltig = _ganzzahl(wahl.findtext("Stimmenergebnis/Wahlvorschlaege_zusammen/Gewichtete_Stimmen"))
    if not gueltig or gueltig <= 0:
        raise Fehler(f"Bayern (Kreistag): keine gewichteten Stimmen für {name!r} gefunden.")

    stimmen: dict[str, int] = {}
    for vorschlag in wahl.findall("Stimmenergebnis/Wahlvorschlag"):
        bezeichnung = (vorschlag.findtext("Bezeichnung") or "").strip()
        if not bezeichnung:
            raise Fehler(f"Bayern (Kreistag): Wahlvorschlag ohne Namen in {name!r}.")
        stimmen[bezeichnung] = stimmen.get(bezeichnung, 0) + _bayern_wahlvorschlag_stimmen(vorschlag)

    if sum(stimmen.values()) != gueltig:
        raise Fehler(
            f"Bayern (Kreistag): gewichtete Stimmen in {name!r} ergeben {sum(stimmen.values())}, "
            f"erwartet waren {gueltig}."
        )

    parteien = {
        anzeigename: round(anzahl / gueltig * 100.0, 1)
        for anzeigename, anzahl in sorted(stimmen.items(), key=lambda paar: -paar[1])
        if anzahl > 0
    }
    return kreisschluessel, {"name": name, "beteiligung": beteiligung, "parteien": parteien}


def bayern_kreistag_xml_auswerten(datei: Path) -> dict:
    try:
        wurzel = ET.parse(datei).getroot()
    except ET.ParseError as exc:
        raise Fehler(f"Bayern (Kreistag): XML nicht lesbar: {exc}") from exc

    gebiete: dict[str, dict] = {}
    for regionaleinheit in wurzel.findall("Regionaleinheit"):
        kreisschluessel, gebiet = _bayern_kreistag_gebiet(regionaleinheit)
        if kreisschluessel in gebiete:
            raise Fehler(f"Bayern (Kreistag): {kreisschluessel} wurde mehrfach erzeugt.")
        gebiete[kreisschluessel] = gebiet

    # Bayern hat 71 Landkreise; eine feste Prüfung statt eines Rahmens, weil sich diese Zahl seit
    # Jahrzehnten nicht geändert hat und ein abgebrochener Export sonst unbemerkt bliebe.
    if len(gebiete) != 71:
        raise Fehler(f"Bayern (Kreistag): 71 Landkreise erwartet, gefunden wurden {len(gebiete)}.")
    return gebiete


# ------------------------------------------------------------------------- Brandenburg 2024 (Gemeindevertretungswahl)

# Anders als die Breitformat-Quellen anderer Länder liefert das Amt für Statistik
# Berlin-Brandenburg die Gemeindevertretungswahl im Langformat: eine Zeile je Gemeinde UND
# Wahlvorschlag (Spalte "Art des Wahlvorschlags": P=Partei, PV=Parteivereinigung, LV=Listen-
# vereinigung, WG=Wählergruppe, EB=Einzelbewerber) mit dem echten Kurz- und Langnamen in eigenen
# Spalten - dadurch entfällt jede feste Parteispaltenliste, und örtliche Wählergruppen/Einzel-
# bewerber (z. B. "Bürger für Frieden, Vernunft und Gerechtigkeit", "EB Wenzel") bleiben unter
# ihrem echten Namen erhalten statt in GERDAs "other"/Sonstige zu verschwinden (siehe Issue #10,
# analog zu Mecklenburg-Vorpommern oben). Kennzahlen wie "Wahlberechtigt" oder "Gültig" stehen als
# eigene Pseudo-Zeilen mit demselben Spaltenschema in derselben Tabelle, erkennbar an einem der
# festen Namen in BRANDENBURG_GVW_KENNZAHLEN statt eines Wahlvorschlagstyps.
BRANDENBURG_GVW_KENNZAHLEN = frozenset(
    {
        "Anzahl Wahlbezirke",
        "Ausgezählte Wahlbezirke",
        "Wahlberechtigt",
        "Wähler",
        "Wahlschein",
        "Ungültig",
        "Gültig",
        "Sitze",
    }
)


def _brandenburg_ags(zeile: dict[str, str]) -> str:
    """AGS aus Landkreis- und Gemeindenummer bilden (Brandenburg hat keine Regierungsbezirke)."""
    kreis = (zeile.get("C") or "").strip().zfill(2)
    gemeinde = (zeile.get("D") or "").strip().zfill(3)
    if not (kreis.isdigit() and len(kreis) == 2 and gemeinde.isdigit() and len(gemeinde) == 3):
        raise Fehler(f"Brandenburg: ungültige Kreis-/Gemeindenummer {zeile.get('C')!r}/{zeile.get('D')!r}.")
    return "12" + "0" + kreis + gemeinde


def _brandenburg_gvw_gebiet(name: str, zeilen: list[dict[str, str]]) -> dict:
    kennzahlen: dict[str, int] = {}
    stimmen: dict[str, int] = {}
    for zeile in zeilen:
        bezeichnung = (zeile.get("G") or "").strip()
        anzahl = _ganzzahl(zeile.get("I"))
        if not (zeile.get("F") or "").strip():
            if bezeichnung in BRANDENBURG_GVW_KENNZAHLEN:
                kennzahlen[bezeichnung] = anzahl if anzahl is not None else 0
            continue
        if not bezeichnung:
            raise Fehler(f"Brandenburg: Wahlvorschlag ohne Namen in {name!r}.")
        stimmen[bezeichnung] = stimmen.get(bezeichnung, 0) + (anzahl or 0)

    gueltig = kennzahlen.get("Gültig")
    if not gueltig:
        raise Fehler(f"Brandenburg: keine gültigen Stimmen für {name!r} gefunden.")
    if sum(stimmen.values()) != gueltig:
        raise Fehler(
            f"Brandenburg: Stimmen in {name!r} ergeben {sum(stimmen.values())}, "
            f"erwartet waren {gueltig} gültige Stimmen."
        )
    if len(stimmen) < 1:
        raise Fehler(f"Brandenburg: keine Wahlvorschläge für {name!r} gefunden.")

    parteien = {
        anzeigename: round(anzahl / gueltig * 100.0, 1)
        for anzeigename, anzahl in sorted(stimmen.items(), key=lambda paar: -paar[1])
        if anzahl > 0
    }
    wahlberechtigte = kennzahlen.get("Wahlberechtigt") or 0
    waehler = kennzahlen.get("Wähler") or 0
    beteiligung = round(waehler / wahlberechtigte * 100.0, 1) if wahlberechtigte > 0 else None
    if beteiligung is not None and not 0.0 <= beteiligung <= 100.0:
        beteiligung = None
    return {"name": name, "beteiligung": beteiligung, "parteien": parteien}


def brandenburg_gvw_zeilen_auswerten(zeilen: list[dict[str, str]]) -> dict:
    gruppen: dict[str, tuple[str, list[dict[str, str]]]] = {}
    for zeile in zeilen:
        if not (zeile.get("C") or "").strip().isdigit():
            continue  # Kopf-, Impressum- oder Leerzeile (Landkreisnummer ist immer numerisch)
        ags = _brandenburg_ags(zeile)
        name = (zeile.get("E") or "").strip()
        if not name:
            raise Fehler(f"Brandenburg: Gemeinde {ags} ohne Namen.")
        gruppen.setdefault(ags, (name, []))[1].append(zeile)

    # 2024 hatte Brandenburg 413 Gemeindevertretungswahlen; ein weiter Rahmen fängt künftige
    # Gebietsreformen ab, ohne einen abgebrochenen Export unbemerkt durchzulassen.
    if len(gruppen) not in range(350, 450):
        raise Fehler(f"Brandenburg: 350 bis 449 Gemeinden erwartet, gefunden wurden {len(gruppen)}.")

    gebiete: dict[str, dict] = {}
    for ags, (name, zeilen_je_gemeinde) in gruppen.items():
        gebiete[ags] = _brandenburg_gvw_gebiet(name, zeilen_je_gemeinde)
    return gebiete


def brandenburg_gvw_xlsx_auswerten(datei: Path) -> dict:
    zeilen = _xlsx_zeilen(datei, "BB_GVW2024")
    return brandenburg_gvw_zeilen_auswerten(zeilen)


# ------------------------------------------------------------------------- Saarland 2022

# Die amtliche KERG-CSV der Landeswahlleiterin Saarland ist im Breitformat: eine Zeile je Gebiet,
# je Partei/Kenngröße ein Spaltenpaar (Endgültig, Vorperiode) - anders als das Langformat der
# Bundeswahlleiterin (siehe kerg2_auswerten). "Nr" unterscheidet die Gebietsebene ohne eigene
# Spalte: fünfstellig = Gemeinde (Kreis(2) + Gemeinde(3), ergibt mit "100"-Vorsatz den achtstelligen
# AGS), einstellig/zweistellig = Wahlkreis- bzw. Landessumme.


def _saarland_bereinigen(text: str) -> str:
    """C1-Steuerzeichen (z. B. \x96 statt eines Gedankenstrichs) aus der Quelldatei glätten - ein
    bekannter Exportfehler des Landeswahlleiter-Systems, kein Encoding-Fehler unsererseits."""
    return " ".join(re.sub(r"[\x80-\x9f]", "-", text).split())


# Die Kopfzeile führt bundesweite Parteien mit ihrem vollen amtlichen Namen (z. B. "Sozialdemokra-
# tische Partei Deutschlands"), anders als die übrigen Länder in diesem Projekt, die durchgängig
# die geläufige Kurzbezeichnung verwenden (CDU, SPD, ...). Nur bekannte, eindeutige Kurzformen
# hier abbilden - eine unbekannte Partei bleibt bewusst mit ihrem vollen (bereinigten) Namen stehen
# statt eine Abkürzung zu erfinden. Trifft das auf echte örtliche Listen wie "bunt.saar" oder "SGV"
# zu, ist der volle Name ohnehin die richtige, unterscheidbare Anzeige.
SAARLAND_KURZNAMEN = {
    "Christlich Demokratische Union Deutschlands": "CDU",
    "Sozialdemokratische Partei Deutschlands": "SPD",
    "Alternative für Deutschland": "AfD",
    "BÜNDNIS 90/DIE GRÜNEN": "GRÜNE",
    "Freie Demokratische Partei": "FDP",
    "Piratenpartei Deutschland": "PIRATEN",
    "Basisdemokratische Partei Deutschland": "dieBasis",
    "Ökologisch-Demokratische Partei": "ÖDP",
    "Partei der Humanisten": "Die Humanisten",
    "Partei für Gesundheitsforschung": "Gesundheitsforschung",
    "PARTEI MENSCH UMWELT TIERSCHUTZ": "Tierschutzpartei",
    "Volt Deutschland": "Volt",
    (
        "Partei für Arbeit, Rechtsstaat, Tierschutz, Elitenförderung und "
        "basisdemokratische Initiative"
    ): "Die PARTEI",
}


def _saarland_kopf(zeilen: list[list[str]]) -> tuple[int, dict[int, str], int, int, int]:
    kopf_index = next((i for i, z in enumerate(zeilen) if z and z[0].strip() == "Nr"), None)
    if kopf_index is None:
        raise Fehler("Saarland: keine Kopfzeile (Nr;Gebiet;...) gefunden.")
    kopf = zeilen[kopf_index]
    try:
        wahlberechtigte_idx = kopf.index("Wahlberechtigte")
        waehler_idx = kopf.index("Wähler")
        gueltig_idx = kopf.index("Gültige Stimmen")
    except ValueError as exc:
        raise Fehler(f"Saarland: Pflichtspalte fehlt ({exc}).") from exc
    parteispalten = {
        i: SAARLAND_KURZNAMEN.get(bereinigt := _saarland_bereinigen(kopf[i]), bereinigt)
        for i in range(3, wahlberechtigte_idx, 2)
        if kopf[i].strip()
    }
    if len(parteispalten) < 5:
        raise Fehler(f"Saarland: nur {len(parteispalten)} Parteispalten gefunden.")
    return kopf_index, parteispalten, wahlberechtigte_idx, waehler_idx, gueltig_idx


def _saarland_gebiet(
    zeile: list[str],
    parteispalten: dict[int, str],
    wahlberechtigte_idx: int,
    waehler_idx: int,
    gueltig_idx: int,
) -> tuple[str, dict]:
    nr = zeile[0].strip()
    ags = "100" + nr
    if not re.fullmatch(r"\d{8}", ags):
        raise Fehler(f"Saarland: ungültiger Gemeinde-AGS {ags!r}.")
    name = zeile[1].strip()
    gueltig = _ganzzahl(zeile[gueltig_idx]) if len(zeile) > gueltig_idx else None
    if not gueltig or gueltig <= 0 or not name:
        raise Fehler(f"Saarland: kein auswertbares Ergebnis für {name!r} ({ags}).")

    stimmen = {partei: _ganzzahl(zeile[i]) or 0 for i, partei in parteispalten.items()}
    if sum(stimmen.values()) != gueltig:
        raise Fehler(
            f"Saarland: Parteistimmen in {name!r} ergeben {sum(stimmen.values())}, "
            f"erwartet waren {gueltig} gültige Stimmen."
        )
    parteien = {
        anzeigename: round(anzahl / gueltig * 100.0, 1)
        for anzeigename, anzahl in sorted(stimmen.items(), key=lambda paar: -paar[1])
        if anzahl > 0
    }

    wahlberechtigte = (_ganzzahl(zeile[wahlberechtigte_idx]) if len(zeile) > wahlberechtigte_idx else 0) or 0
    waehler = (_ganzzahl(zeile[waehler_idx]) if len(zeile) > waehler_idx else 0) or 0
    beteiligung = round(waehler / wahlberechtigte * 100.0, 1) if wahlberechtigte > 0 else None
    if beteiligung is not None and not 0.0 <= beteiligung <= 100.0:
        beteiligung = None

    return ags, {"name": name, "beteiligung": beteiligung, "parteien": parteien}


def saarland_landtag_zeilen_auswerten(zeilen: list[list[str]]) -> dict:
    kopf_index, parteispalten, wahlberechtigte_idx, waehler_idx, gueltig_idx = _saarland_kopf(zeilen)
    gem = [z for z in zeilen[kopf_index + 1 :] if z and re.fullmatch(r"\d{5}", z[0].strip())]
    # 2022 hatte Saarland 52 Gemeinden; ein weiter Rahmen fängt künftige Gebietsreformen ab, ohne
    # einen abgebrochenen Export unbemerkt durchzulassen.
    if not 45 <= len(gem) <= 60:
        raise Fehler(f"Saarland: Erwartet wurden rund 52 Gemeindezeilen, gefunden wurden {len(gem)}.")

    gebiete: dict[str, dict] = {}
    for zeile in gem:
        ags, gebiet = _saarland_gebiet(zeile, parteispalten, wahlberechtigte_idx, waehler_idx, gueltig_idx)
        if ags in gebiete:
            raise Fehler(f"Saarland: AGS {ags} wurde mehrfach erzeugt.")
        gebiete[ags] = gebiet
    return gebiete


def saarland_landtag_csv_auswerten(datei: Path) -> dict:
    with datei.open(encoding="utf-8-sig", newline="") as eingabe:
        zeilen = list(csv.reader(eingabe, delimiter=";"))
    return saarland_landtag_zeilen_auswerten(zeilen)


# ------------------------------------------------------------ Schleswig-Holstein 2022

# Die amtliche Datei des Statistikamts Nord ist Wahlbezirksebene, nicht Gemeindeebene: Blatt
# "2022", Zeile 1 Titel, Zeile 2 Kopfzeilen (mehrzeiliger Text), Zeile 3 Kurzcodes (A1, A2, ...
# F16), ab Zeile 4 Daten. Spalte A "Statistische Kennziffer" ist ein achtstelliger Code, der sich
# direkt in den amtlichen AGS umrechnen lässt: Stelle 1-2 = Kreis-Nummer innerhalb Schleswig-
# Holsteins (-> "01" + dreistellig gepaddet), Stelle 3-5 = Gemeindenummer innerhalb des Kreises,
# Stelle 6-8 = Wahlbezirk. Das gilt nur für reguläre Wahlbezirkszeilen; Briefwahl-Pseudozeilen
# nutzen Stelle 3 als reservierten Marker "9" statt einer echten Gemeindenummer (siehe unten).
SCHLESWIG_HOLSTEIN_2022_BLATT = "2022"

# Kreis-Nummer (Stelle 1-2 der Kennziffer) -> amtlicher Kreisname, nur zur Absicherung genutzt
# (die Datei führt den Kreisnamen redundant in Spalte B; ein Mismatch zeigt einen Formatbruch an).
SCHLESWIG_HOLSTEIN_KREISE: dict[str, str] = {
    "01": "Flensburg", "02": "Kiel", "03": "Lübeck", "04": "Neumünster",
    "51": "Dithmarschen", "53": "Herzogtum Lauenburg", "54": "Nordfriesland",
    "55": "Ostholstein", "56": "Pinneberg", "57": "Plön",
    "58": "Rendsburg-Eckernförde", "59": "Schleswig-Flensburg",
    "60": "Segeberg", "61": "Steinburg", "62": "Stormarn",
}

# Spaltenbuchstabe (Zweitstimmen, Spalten AN-BC) -> (amtlicher Kopfzeilentext, Anzeigename). Die
# Datei führt jede Partei nur einmal in eigener Schreibweise; alle bis auf "Z." (das amtliche
# Kürzel der historischen Zentrumspartei, siehe auch GERDAs eigene Spaltenbezeichnung "zentrum")
# entsprechen bereits der im Projekt üblichen Kurzbezeichnung.
SCHLESWIG_HOLSTEIN_PARTEISPALTEN: dict[str, tuple[str, str]] = {
    "AN": ("CDU", "CDU"),
    "AO": ("SPD", "SPD"),
    "AP": ("GRÜNE", "GRÜNE"),
    "AQ": ("FDP", "FDP"),
    "AR": ("AfD", "AfD"),
    "AS": ("DIE LINKE", "DIE LINKE"),
    "AT": ("SSW", "SSW"),
    "AU": ("PIRATEN", "PIRATEN"),
    "AV": ("FREIE WÄHLER", "FREIE WÄHLER"),
    "AW": ("Die PARTEI", "Die PARTEI"),
    "AX": ("Z.", "Zentrum"),
    "AY": ("dieBasis", "dieBasis"),
    "AZ": ("Die Humanisten", "Die Humanisten"),
    "BA": ("Gesundheitsforschung", "Gesundheitsforschung"),
    "BB": ("Tierschutzpartei", "Tierschutzpartei"),
    "BC": ("Volt", "Volt"),
}

# Bei amtsangehörigen Gemeinden weist die Quelle die Briefwahl nicht je Gemeinde aus, sondern
# gepoolt auf Amtsebene in eigenen Pseudozeilen (Kennziffer-Stelle 3 = "9", Gemeindename leer,
# nur Ämterschlüssel gesetzt). Das betrifft praktisch alle amtsangehörigen Gemeinden. Entscheidung
# wie bei Mecklenburg-Vorpommern: transparent kennzeichnen statt Zahlen zu erfinden oder Gemeinden
# wegzulassen (siehe MECKLENBURG_BRIEFWAHL_HINWEIS).
SCHLESWIG_HOLSTEIN_BRIEFWAHL_HINWEIS = (
    "Nur Urnenwahl - die Briefwahl dieser amtsangehörigen Gemeinde wird von der Quelle nur "
    "gepoolt auf Amtsebene ausgewiesen, nicht einzeln je Gemeinde."
)

# Maasbüll, Tastrup und Ülsby waren 2022 eigenständige Gemeinden (Amt Hürup bzw. Amt Südangeln)
# und wurden seither zur Gemeinde Uelsby zusammengelegt, die Ülsbys eigenen AGS fortführt. Die
# beiden aufgegangenen historischen AGS existieren im aktuellen Gemeindeschlüssel-Stand nicht
# mehr; ihre 2022er Wahlbezirkszeilen werden deshalb vor der Auswertung in den fortbestehenden
# AGS umgehängt (analog zu Sachsens Teilgemeinden-Zusammenführung, siehe
# SACHSEN_NUR_TEILGEMEINDEN), statt einen inzwischen ungültigen AGS auszugeben.
SCHLESWIG_HOLSTEIN_ZUSAMMENGELEGT: dict[str, str] = {
    "01059141": "01059093",  # Maasbüll -> Uelsby
    "01059101": "01059093",  # Tastrup -> Uelsby
}
SCHLESWIG_HOLSTEIN_ZUSAMMENGELEGT_NAME = "Uelsby"
SCHLESWIG_HOLSTEIN_ZUSAMMENGELEGT_HINWEIS = (
    "Zusammengefasstes Ergebnis der 2022 eigenständigen Gemeinden Maasbüll, Tastrup und Ülsby, "
    "die seither zur Gemeinde Uelsby zusammengelegt wurden. " + SCHLESWIG_HOLSTEIN_BRIEFWAHL_HINWEIS
)


def _schleswig_holstein_kopftext(text: str | None) -> str:
    """Mehrzeiligen Kopfzellentext (mit uneinheitlichen Leerzeichen/Zeilenumbrüchen) glätten."""
    return " ".join((text or "").split())


def _schleswig_holstein_ags(kennziffer: str, kreisname: str) -> str:
    if not re.fullmatch(r"\d{8}", kennziffer):
        raise Fehler(f"Schleswig-Holstein: ungültige Kennziffer {kennziffer!r}.")
    kreis_nr, gemeinde_nr = kennziffer[0:2], kennziffer[2:5]
    erwarteter_kreisname = SCHLESWIG_HOLSTEIN_KREISE.get(kreis_nr)
    if erwarteter_kreisname is None:
        raise Fehler(f"Schleswig-Holstein: unbekannte Kreis-Nummer {kreis_nr!r}.")
    if erwarteter_kreisname != kreisname:
        raise Fehler(
            f"Schleswig-Holstein: Kreis-Nummer {kreis_nr!r} passt nicht zu Kreisname {kreisname!r} "
            f"(erwartet {erwarteter_kreisname!r})."
        )
    return "01" + kreis_nr.zfill(3) + gemeinde_nr


def schleswig_holstein_landtag_zeilen_auswerten(zeilen: list[dict[str, str]]) -> dict:
    def feld(zeile: dict[str, str], spalte: str) -> str:
        wert = zeile.get(spalte)
        return wert.strip() if isinstance(wert, str) else ""

    def brief_marker(zeile: dict[str, str]) -> str | None:
        kennziffer = feld(zeile, "A")
        return kennziffer[2] if len(kennziffer) == 8 else None

    regulaer = [z for z in zeilen if brief_marker(z) in ("0", "1") and feld(z, "C")]
    # 2022 hatte die Datei rund 2.400 reguläre Wahlbezirkszeilen (mehrere je Gemeinde); ein weiter
    # Rahmen fängt künftige Gebietsreformen ab, ohne einen abgebrochenen Export unbemerkt
    # durchzulassen. Die Gemeindezahl selbst wird unten nach dem Gruppieren geprüft.
    if not 2000 <= len(regulaer) <= 2800:
        raise Fehler(
            f"Schleswig-Holstein: Erwartet wurden rund 2.400 reguläre Wahlbezirkszeilen, "
            f"gefunden wurden {len(regulaer)}."
        )

    gruppen: dict[str, list[dict[str, str]]] = defaultdict(list)
    namen: dict[str, tuple[str, str]] = {}
    for zeile in regulaer:
        ags = _schleswig_holstein_ags(feld(zeile, "A"), feld(zeile, "B"))
        gruppen[ags].append(zeile)
        schluessel = (feld(zeile, "B"), feld(zeile, "C"))
        if ags in namen and namen[ags] != schluessel:
            raise Fehler(f"Schleswig-Holstein: AGS {ags} hat uneinheitliche Kreis-/Gemeindenamen.")
        namen[ags] = schluessel
    if len(namen) < 1000:
        raise Fehler(f"Schleswig-Holstein: nur {len(namen)} Gemeinden aus Wahlbezirken zusammengesetzt.")

    nach_kreis_gemeinde = {schluessel: ags for ags, schluessel in namen.items()}

    # Direkt einer Gemeinde zugeordnete Briefwahlzeilen (Kennziffer-Stelle 3 = "9", Gemeindename
    # gesetzt) sind vollständig attribuiert und werden schlicht mitgezählt.
    for zeile in zeilen:
        if brief_marker(zeile) != "9" or not feld(zeile, "C"):
            continue
        schluessel = (feld(zeile, "B"), feld(zeile, "C"))
        ags = nach_kreis_gemeinde.get(schluessel)
        if ags is None:
            raise Fehler(f"Schleswig-Holstein: Briefwahlzeile ohne passende Gemeinde {schluessel!r}.")
        gruppen[ags].append(zeile)

    # Amt-gepoolte Briefwahl-Pseudozeilen (Gemeindename leer) tragen keine Stimmen bei; sie
    # markieren nur, welche Ämter betroffen sind (siehe SCHLESWIG_HOLSTEIN_BRIEFWAHL_HINWEIS).
    gepoolte_aemter = {
        feld(z, "E") for z in zeilen if brief_marker(z) == "9" and not feld(z, "C") and feld(z, "E")
    }

    # Vor der Aggregation zusammenlegen, damit Prozentanteile aus den echten Rohstimmen der drei
    # ehemaligen Gemeinden berechnet werden statt aus bereits gerundeten Prozentwerten.
    for quelle_ags, ziel_ags in SCHLESWIG_HOLSTEIN_ZUSAMMENGELEGT.items():
        quelle_zeilen = gruppen.pop(quelle_ags, None)
        if not quelle_zeilen or ziel_ags not in gruppen:
            raise Fehler(f"Schleswig-Holstein: Zusammenlegung {quelle_ags} -> {ziel_ags} nicht auswertbar.")
        gruppen[ziel_ags].extend(quelle_zeilen)

    gebiete: dict[str, dict] = {}
    for ags, gruppen_zeilen in gruppen.items():
        gueltig = sum(_ganzzahl(z.get("AM")) or 0 for z in gruppen_zeilen)
        if gueltig <= 0:
            raise Fehler(f"Schleswig-Holstein: kein auswertbares Ergebnis für AGS {ags}.")

        stimmen: dict[str, int] = defaultdict(int)
        for zeile in gruppen_zeilen:
            for spalte, (_, anzeigename) in SCHLESWIG_HOLSTEIN_PARTEISPALTEN.items():
                stimmen[anzeigename] += _ganzzahl(zeile.get(spalte)) or 0
        if sum(stimmen.values()) != gueltig:
            raise Fehler(
                f"Schleswig-Holstein: Parteistimmen für AGS {ags} ergeben {sum(stimmen.values())}, "
                f"erwartet waren {gueltig} gültige Zweitstimmen."
            )
        parteien = {
            anzeigename: round(anzahl / gueltig * 100.0, 1)
            for anzeigename, anzahl in sorted(stimmen.items(), key=lambda paar: -paar[1])
            if anzahl > 0
        }

        wahlberechtigte = sum(_ganzzahl(z.get("N")) or 0 for z in gruppen_zeilen)
        waehler = sum(_ganzzahl(z.get("R")) or 0 for z in gruppen_zeilen)
        beteiligung = round(waehler / wahlberechtigte * 100.0, 1) if wahlberechtigte > 0 else None
        if beteiligung is not None and not 0.0 <= beteiligung <= 100.0:
            beteiligung = None

        gebiet = {"name": feld(gruppen_zeilen[0], "C"), "beteiligung": beteiligung, "parteien": parteien}
        if {feld(z, "E") for z in gruppen_zeilen if feld(z, "E")} & gepoolte_aemter:
            gebiet["hinweis"] = SCHLESWIG_HOLSTEIN_BRIEFWAHL_HINWEIS
        gebiete[ags] = gebiet

    for ziel_ags in set(SCHLESWIG_HOLSTEIN_ZUSAMMENGELEGT.values()):
        gebiete[ziel_ags]["name"] = SCHLESWIG_HOLSTEIN_ZUSAMMENGELEGT_NAME
        gebiete[ziel_ags]["hinweis"] = SCHLESWIG_HOLSTEIN_ZUSAMMENGELEGT_HINWEIS

    return gebiete


def schleswig_holstein_landtag_xlsx_auswerten(datei: Path) -> dict:
    zeilen = _xlsx_zeilen(datei, SCHLESWIG_HOLSTEIN_2022_BLATT)
    kopf_index = next(
        (i for i, z in enumerate(zeilen) if _schleswig_holstein_kopftext(z.get("A")) == "Statistische Kennziffer"),
        None,
    )
    if kopf_index is None:
        raise Fehler("Schleswig-Holstein: Keine XLSX-Kopfzeile gefunden.")
    kopf = zeilen[kopf_index]
    pflichtspalten = {
        "B": "Kreisname", "C": "Gemeindename", "E": "Ämterschlüssel", "F": "Ämtername",
        "N": "Wahlberechtigte insgesamt", "R": "Wählerinnen und Wähler insgesamt",
        "AM": "Gültige Zweitstimmen",
    }
    for spalte, erwartet in pflichtspalten.items():
        gefunden = _schleswig_holstein_kopftext(kopf.get(spalte))
        if gefunden != erwartet:
            raise Fehler(f"Schleswig-Holstein: Spalte {spalte} ist {gefunden!r}, erwartet {erwartet!r}.")
    for spalte, (erwartet, _) in SCHLESWIG_HOLSTEIN_PARTEISPALTEN.items():
        gefunden = _schleswig_holstein_kopftext(kopf.get(spalte))
        if gefunden != f"{erwartet} Zweitstimmen":
            raise Fehler(f"Schleswig-Holstein: Spalte {spalte} ist {gefunden!r}, erwartet {erwartet!r}.")
    # Zeile kopf_index+1 ist die Kurzcode-Zeile (A1, A2, ... F16); echte Daten beginnen danach.
    return schleswig_holstein_landtag_zeilen_auswerten(zeilen[kopf_index + 2 :])


# ------------------------------------------------------------- Bundeswahl kerg2


KERG_ERSTE_SPALTE = "Wahlart"
KERG_PARTEI = "Partei"
KERG_WAEHLENDE = ("wählende", "waehlende")


def _kommazahl(feld: str) -> float | None:
    roh = feld.strip().replace(".", "").replace(",", ".")
    try:
        wert = float(roh)
    except ValueError:
        return None
    return wert if 0.0 <= wert <= 100.0 else None


def kerg2_auswerten(csv_text: str, gebietsart: str, stimme: str | None) -> dict:
    """Offenes kerg2-Format der Bundeswahlleiterin nach Gebietsebene und Stimme filtern."""
    zeilen = csv_text.splitlines()
    kopf, ab = None, 0
    for i, zeile in enumerate(zeilen):
        if zeile.split(";", 1)[0].strip().lstrip("﻿") == KERG_ERSTE_SPALTE:
            kopf = [s.strip() for s in zeile.split(";")]
            ab = i + 1
            break
    if kopf is None:
        raise Fehler("Keine kerg2-Kopfzeile gefunden.")

    spalte = {name: i for i, name in enumerate(kopf)}
    fehlend = [s for s in ("Gebietsnummer", "Gruppenart", "Gruppenname", "Prozent") if s not in spalte]
    if fehlend:
        raise Fehler("kerg2-Spalten fehlen: " + ", ".join(fehlend))

    i_nummer, i_art = spalte["Gebietsnummer"], spalte["Gruppenart"]
    i_name, i_prozent = spalte["Gruppenname"], spalte["Prozent"]
    i_gebietsart = spalte.get("Gebietsart")
    i_gebietsname = spalte.get("Gebietsname")
    i_stimme = spalte.get("Stimme")

    gebiete: dict[str, dict] = {}
    for zeile in zeilen[ab:]:
        felder = zeile.split(";")
        if len(felder) <= i_prozent:
            continue
        if i_gebietsart is not None and gebietsart.lower() not in felder[i_gebietsart].strip().lower():
            continue
        nummer = felder[i_nummer].strip()
        if not nummer:
            continue
        eintrag = gebiete.setdefault(nummer, {"name": "", "beteiligung": None, "parteien": {}})
        if i_gebietsname is not None and len(felder) > i_gebietsname and not eintrag["name"]:
            eintrag["name"] = felder[i_gebietsname].strip()

        prozent = _kommazahl(felder[i_prozent])
        if prozent is None:
            continue
        gruppenname = felder[i_name].strip()
        if felder[i_art].strip().lower() == KERG_PARTEI.lower():
            zaehlt = stimme is None or i_stimme is None or felder[i_stimme].strip() == stimme
            if zaehlt:
                eintrag["parteien"][gruppenname] = prozent
        elif gruppenname.lower() in KERG_WAEHLENDE and eintrag["beteiligung"] is None:
            eintrag["beteiligung"] = prozent

    fertig = {}
    for nummer, gebiet in gebiete.items():
        if len(gebiet["parteien"]) < 3 or not 95.0 <= sum(gebiet["parteien"].values()) <= 105.0:
            continue
        fertig[nummer] = {
            "name": gebiet["name"],
            "beteiligung": round(gebiet["beteiligung"], 1) if gebiet["beteiligung"] is not None else None,
            "parteien": {
                name: round(wert, 1)
                for name, wert in sorted(gebiet["parteien"].items(), key=lambda paar: -paar[1])
            },
        }
    return fertig


def eine_bundeswahl(eintrag: dict) -> bool:
    print(f"  {eintrag['titel']}")
    gebiete = kerg2_auswerten(
        hole_roh(eintrag["url"]), eintrag["gebietsart"], eintrag.get("stimme")
    )
    if not gebiete:
        raise Fehler("Datei geladen, aber kein Gebiet hat die Plausibilitätsprüfung bestanden.")
    datei = ZIEL / f"{eintrag['kennung']}.json"
    frisch = schreiben(
        datei,
        {
            "kennung": eintrag["kennung"],
            "titel": eintrag["titel"],
            "jahr": eintrag["jahr"],
            "schluesselart": eintrag["schluesselart"],
            "quelle": QUELLE_BUND,
            "quellenvermerk": QUELLENVERMERK_BUND,
            "lizenz": LIZENZ_BUND,
            "lizenz_url": LIZENZ_BUND_URL,
            "quellendatei": eintrag["url"],
            "gebiete": gebiete,
        },
    )
    print(f"    {len(gebiete)} Gebiete, {datei.relative_to(WURZEL)} {'geschrieben' if frisch else 'unverändert'}")
    return True


# -------------------------------------------------------------------------- Ablauf


def _quellenfelder(quelle: dict) -> dict:
    felder = {
        "quelle": quelle["quelle"],
        "quellenvermerk": quelle["quellenvermerk"],
        "lizenz": quelle["lizenz"],
        "lizenz_url": quelle["lizenz_url"],
        "quellendatei": quelle["url"],
    }
    for optional in (
        "dataset",
        "zitation",
        "quellenseite",
        "kreisverzeichnis_dataset",
        "kreisverzeichnis_url",
    ):
        if quelle.get(optional):
            felder[optional] = quelle[optional]
    return felder


def _gerda_quelle(konfiguration: dict, datensatz: str) -> dict:
    """Gemeinsame GERDA-Metadaten mit genau einem konfigurierten Datensatz verbinden."""
    gerda = konfiguration["gerda"]
    datasets = gerda.get("datasets") or {}
    if datensatz not in datasets:
        raise Fehler(f"GERDA-Datensatz {datensatz!r} fehlt in quellen.json.")
    basis = {name: wert for name, wert in gerda.items() if name != "datasets"}
    return {**basis, **datasets[datensatz]}


# Jede amtliche Ergänzung in quellen.json trägt einen dieser Parsernamen. Ein unbekannter Name
# muss laut scheitern, damit ein Tippfehler in der Konfiguration nicht still übergangen wird.
ERGAENZUNGS_PARSER: dict[str, Callable[[Path], dict]] = {
    "rlp-2026-xlsx": rlp_xlsx_auswerten,
    "sachsen-2024-xlsx": sachsen_xlsx_auswerten,
    "sachsenanhalt-2021-csv": sachsenanhalt_csv_auswerten,
    "berlin-2023-xlsx": berlin_xlsx_auswerten,
    "mecklenburg-vorpommern-2021-csv": mecklenburg_landtag_csv_auswerten,
    "saarland-2022-csv": saarland_landtag_csv_auswerten,
    "schleswig-holstein-2022-xlsx": schleswig_holstein_landtag_xlsx_auswerten,
}

# Live-abgerufene Ergänzungen für Kommunal-/Kreistagswahl, analog zu ERGAENZUNGS_PARSER oben -
# siehe _kommunal_holen. Getrennt von ERGAENZUNGS_PARSER, weil ein Land theoretisch für Landtag,
# Kommunal und Kreistag unterschiedliche Parser bräuchte (unterschiedliche Amtsstellen/Formate).
KOMMUNAL_ERGAENZUNGS_PARSER: dict[str, Callable[[Path], dict]] = {
    "mecklenburg-vorpommern-2024-kommunal-csv": mecklenburg_kommunal_csv_auswerten,
    "brandenburg-2024-gemeindevertretung-xlsx": brandenburg_gvw_xlsx_auswerten,
}
KREISTAG_ERGAENZUNGS_PARSER: dict[str, Callable[[Path], dict]] = {
    "mecklenburg-vorpommern-2024-kreistag-csv": mecklenburg_kreistag_csv_auswerten,
    "bayern-2026-kreistag-xml": bayern_kreistag_xml_auswerten,
}


def _snapshot_gebiete(pfad_rel: str, schluessel: str) -> dict:
    """Gebiete aus einer manuell geprüften JSON-Momentaufnahme lesen (siehe quellen/*.json).

    Anders als die live abgerufenen Ergänzungen (siehe ERGAENZUNGS_PARSER/KOMMUNAL_ERGAENZUNGS_-
    PARSER/KREISTAG_ERGAENZUNGS_PARSER) kommt diese Art Ergänzung nicht per Download: Die
    Quelltabelle liess sich nur mit einer Tabellen-Bibliothek zuverlässig aus einem PDF lesen (oder,
    wie beim rheinland-pfälzischen Kommunal-Sonderfall, nur über hunderte Einzelabrufe je Gemeinde),
    nicht mit der Python-Standardbibliothek, die dieser Sammler sonst ausschliesslich benutzt. Der
    Snapshot liegt deshalb als geprüfte Datei im Repository, mit Quelle, Prüfmethode und Datum in
    der Datei selbst dokumentiert. Eine normale, einmalig live abrufbare CSV/XLSX-Quelle (wie bei
    Mecklenburg-Vorpommern) gehört NICHT hierher, sondern in einen der ERGAENZUNGS_PARSER-Dicts.
    """
    pfad = WURZEL / pfad_rel
    try:
        inhalt = json.loads(pfad.read_text(encoding="utf-8"))
    except OSError as exc:
        raise Fehler(f"Snapshot {pfad_rel} nicht lesbar: {exc}") from exc
    gebiete = inhalt.get(schluessel)
    if not isinstance(gebiete, dict) or not gebiete:
        raise Fehler(f"Snapshot {pfad_rel}: Schlüssel {schluessel!r} fehlt oder ist leer.")
    return gebiete


def _snapshot_ergaenzungen_anwenden(
    ziel: dict[str, dict],
    ergaenzungen: list[dict],
    gesucht: set[str],
) -> list[str]:
    """Wendet manuell geprüfte JSON-Snapshots an.

    Dasselbe Prinzip wie die XLSX-Ergänzungen für Landtagswahlen (volle Ersetzung des
    GERDA-Ergebnisses für ein Land), nur ohne Download – siehe [_snapshot_gebiete]. Eine volle
    Ersetzung ist hier auch dann richtig, wenn der Snapshot – wie bei der rheinland-pfälzischen
    Kommunal-Ergänzung – nur einen Teil der Gemeinden abdeckt: Die übrigen sollen dann fehlen,
    nicht stillschweigend bei GERDAs älterem Stand bleiben.
    """
    gescheitert: list[str] = []
    for ergaenzung in ergaenzungen:
        land = ergaenzung["land"]
        # Live abgerufene Ergänzungen (Schlüssel "parser" statt "datei"/"schluessel", siehe
        # _live_ergaenzungen_anwenden) landen hier nicht - andere Einträge derselben Liste.
        if land not in gesucht or "datei" not in ergaenzung:
            continue
        print(f"  Ergänzung: {ergaenzung['quelle']} {ergaenzung['jahr']}")
        try:
            gebiete = _snapshot_gebiete(ergaenzung["datei"], ergaenzung["schluessel"])
            ziel[land] = {
                "jahr": ergaenzung["jahr"],
                "wahl_datum": ergaenzung.get("wahl_datum", ""),
                "gebiete": gebiete,
                "herkunft": "snapshot-json",
                "quelle": ergaenzung,
            }
            print(f"    {len(gebiete)} Gebiete aus geprüftem Snapshot")
        except Fehler as exc:
            print(f"    FEHLER: {exc}")
            gescheitert.append(f"{ergaenzung['quelle']} {ergaenzung['jahr']}")
    return gescheitert


def _live_ergaenzungen_anwenden(
    ziel: dict[str, dict],
    ergaenzungen: list[dict],
    gesucht: set[str],
    parser_dict: dict[str, Callable[[Path], dict]],
    temp: Path,
    dateiname_praefix: str,
) -> list[str]:
    """Live abgerufene Ergänzungen für Kommunal-/Kreistagswahl - derselbe Download-Parse-Ablauf
    wie der Landtagswahl-Mechanismus in _laender_holen (dort inline, hier als gemeinsame Funktion
    für beide Aufrufer in _kommunal_holen). Einträge ohne "parser"-Schlüssel (der bestehende
    RLP-Kommunal-Snapshot) gehören zu _snapshot_ergaenzungen_anwenden, nicht hierher."""
    gescheitert: list[str] = []
    for ergaenzung in ergaenzungen:
        land = ergaenzung["land"]
        if land not in gesucht or "parser" not in ergaenzung:
            continue
        print(f"  Ergänzung: {ergaenzung['quelle']} {ergaenzung['jahr']}")
        try:
            datei = temp / f"{dateiname_praefix}-{land}.csv"
            groesse = lade_datei(ergaenzung["url"], datei)
            parser = parser_dict.get(ergaenzung.get("parser", ""))
            if parser is None:
                raise Fehler(f"Unbekannter Ergänzungsparser {ergaenzung.get('parser')!r}")
            gebiete = parser(datei)
            ziel[land] = {
                "jahr": ergaenzung["jahr"],
                "wahl_datum": ergaenzung.get("wahl_datum", ""),
                "gebiete": gebiete,
                "herkunft": ergaenzung["parser"],
                "quelle": ergaenzung,
            }
            print(f"    {groesse / 1024 / 1024:.1f} MiB, {len(gebiete)} Gebiete")
        except Fehler as exc:
            print(f"    FEHLER: {exc}")
            gescheitert.append(f"{ergaenzung['quelle']} {ergaenzung['jahr']}")
    return gescheitert


def _laender_holen(konfiguration: dict, laender: list[dict]) -> tuple[dict[str, dict], list[str]]:
    gesucht = {land["land"] for land in laender}
    daten: dict[str, dict] = {}
    gescheitert: list[str] = []
    gerda = _gerda_quelle(konfiguration, "landtag")

    with tempfile.TemporaryDirectory(prefix="plakat-kompass-") as ordner:
        temp = Path(ordner)
        gerda_datei = temp / "state_harm_25.csv"
        print(f"\n{len(laender)} Land/Länder, GERDA wird einmal geladen")
        try:
            groesse = lade_datei(gerda["url"], gerda_datei)
            print(f"  GERDA: {groesse / 1024 / 1024:.1f} MiB geladen")
            for land, ergebnis in gerda_datei_auswerten(gerda_datei, gesucht).items():
                daten[land] = {**ergebnis, "quelle": gerda}
        except Fehler as exc:
            print(f"  GERDA FEHLER: {exc}")
            gescheitert.append("GERDA-Download")

        for ergaenzung in konfiguration.get("ergaenzungen", []):
            land = ergaenzung["land"]
            if land not in gesucht:
                continue
            print(f"  Ergänzung: {ergaenzung['quelle']} {ergaenzung['jahr']}")
            try:
                xlsx = temp / f"land-{land}.xlsx"
                groesse = lade_datei(ergaenzung["url"], xlsx)
                parser = ERGAENZUNGS_PARSER.get(ergaenzung.get("parser", ""))
                if parser is None:
                    raise Fehler(f"Unbekannter Ergänzungsparser {ergaenzung.get('parser')!r}")
                gebiete = parser(xlsx)
                daten[land] = {
                    "jahr": ergaenzung["jahr"],
                    "wahl_datum": ergaenzung.get("wahl_datum", ""),
                    "gebiete": gebiete,
                    "herkunft": ergaenzung["parser"],
                    "quelle": ergaenzung,
                }
                print(f"    {groesse / 1024 / 1024:.1f} MiB, {len(gebiete)} Gemeinden")
            except Fehler as exc:
                print(f"    FEHLER: {exc}")
                gescheitert.append(f"{ergaenzung['quelle']} {ergaenzung['jahr']}")

        gescheitert += _snapshot_ergaenzungen_anwenden(
            daten, konfiguration.get("landtag_ergaenzungen", []), gesucht
        )

    return daten, gescheitert


def _kommunal_holen(
    konfiguration: dict,
    laender: list[dict],
) -> tuple[dict[str, dict], dict[str, dict], list[str]]:
    """Gemeinde-/Stadtrats- und Kreistagsdaten mit je einem GERDA-Abruf laden."""
    gesucht = {land["land"] for land in laender}
    kommunal: dict[str, dict] = {}
    kreistag: dict[str, dict] = {}
    gescheitert: list[str] = []
    kommunal_quelle = _gerda_quelle(konfiguration, "kommunal")
    kreistag_quelle = _gerda_quelle(konfiguration, "kreistag")

    with tempfile.TemporaryDirectory(prefix="plakat-kompass-") as ordner:
        temp = Path(ordner)
        kommunal_datei = temp / "municipal_harm_25.csv"
        print(f"\n{len(laender)} Land/Länder, GERDA-Kommunalwahl wird einmal geladen")
        try:
            groesse = lade_datei(kommunal_quelle["url"], kommunal_datei)
            print(f"  Gemeinde-/Stadtratswahlen: {groesse / 1024 / 1024:.1f} MiB geladen")
            for land, ergebnis in gerda_kommunal_auswerten(kommunal_datei, gesucht).items():
                kommunal[land] = {**ergebnis, "quelle": kommunal_quelle}
        except Fehler as exc:
            print(f"  GERDA KOMMUNAL FEHLER: {exc}")
            gescheitert.append("GERDA Gemeinde-/Stadtratswahlen")

        kreistag_datei = temp / "county_elec_harm_21_cty.csv"
        kreise_datei = temp / "county_council_seats.csv"
        print("  GERDA-Kreistagswahlen und Kreisverzeichnis")
        try:
            groesse = lade_datei(kreistag_quelle["url"], kreistag_datei)
            kreise_groesse = lade_datei(kreistag_quelle["kreisverzeichnis_url"], kreise_datei)
            print(
                f"    {groesse / 1024 / 1024:.1f} MiB Ergebnisse, "
                f"{kreise_groesse / 1024 / 1024:.1f} MiB Kreisverzeichnis"
            )
            kreisverzeichnis = gerda_kreisverzeichnis_auswerten(kreise_datei)
            for land, ergebnis in gerda_kreistag_auswerten(
                kreistag_datei, kreisverzeichnis, gesucht
            ).items():
                kreistag[land] = {**ergebnis, "quelle": kreistag_quelle}
        except Fehler as exc:
            print(f"    GERDA KREISTAG FEHLER: {exc}")
            gescheitert.append("GERDA Kreistagswahlen")

        gescheitert += _snapshot_ergaenzungen_anwenden(
            kommunal, konfiguration.get("kommunal_ergaenzungen", []), gesucht
        )
        gescheitert += _snapshot_ergaenzungen_anwenden(
            kreistag, konfiguration.get("kreistag_ergaenzungen", []), gesucht
        )
        gescheitert += _live_ergaenzungen_anwenden(
            kommunal,
            konfiguration.get("kommunal_ergaenzungen", []),
            gesucht,
            KOMMUNAL_ERGAENZUNGS_PARSER,
            temp,
            "kommunal",
        )
        gescheitert += _live_ergaenzungen_anwenden(
            kreistag,
            konfiguration.get("kreistag_ergaenzungen", []),
            gesucht,
            KREISTAG_ERGAENZUNGS_PARSER,
            temp,
            "kreistag",
        )

    return kommunal, kreistag, gescheitert


def _ausgabepfade(landkennzahl: str, wahlart: str) -> tuple[Path, Path]:
    """Kanonische Landesdatei und weiterhin erreichbare flache Kompatibilitätsdatei."""
    praefix = {
        "landtag": "land",
        "kommunal": "kommunal",
        "kreistag": "kreistag",
    }.get(wahlart)
    if praefix is None:
        raise Fehler(f"Unbekannte Gebietswahl {wahlart!r}.")
    return ZIEL / landkennzahl / f"{wahlart}.json", ZIEL / f"{praefix}-{landkennzahl}.json"


def _mehrfach_schreiben(pfade: tuple[Path, ...], inhalt: dict) -> bool:
    """Identische JSON-Dateien schreiben und dabei einen vorhandenen Datenstand bewahren."""
    vergleich = {k: v for k, v in inhalt.items() if k != "stand"}
    vorhandene_staende: list[str] = []
    for datei in pfade:
        try:
            alt = json.loads(datei.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if {k: v for k, v in alt.items() if k != "stand"} == vergleich:
            stand = str(alt.get("stand") or "")
            if stand:
                vorhandene_staende.append(stand)

    # Die früheste vorhandene Angabe ist der ursprüngliche Datenstand. Ein bloßes Verschieben in
    # den Landesordner darf ihn nicht künstlich auf heute setzen.
    stand = min(vorhandene_staende) if vorhandene_staende else date.today().isoformat()
    text = json.dumps({**vergleich, "stand": stand}, ensure_ascii=False, indent=1) + "\n"
    geaendert = False
    for datei in pfade:
        try:
            if datei.read_text(encoding="utf-8") == text:
                continue
        except OSError:
            pass
        datei.parent.mkdir(parents=True, exist_ok=True)
        datei.write_text(text, encoding="utf-8")
        geaendert = True
    return geaendert


def _gemeinderatsdateien_schreiben(landesdaten: dict) -> bool:
    """Eine direkt abrufbare, kleine Ergebnisdatei je achtstelligem Gemeinde-AGS schreiben."""
    land = str(landesdaten.get("land") or "")
    if not re.fullmatch(r"\d{2}", land):
        raise Fehler(f"Ungültige Landkennzahl für Gemeinderatsdateien: {land!r}.")
    if landesdaten.get("wahlart") != "kommunal" or landesdaten.get("schluesselart") != "ags":
        raise Fehler(f"{land}: Gemeinderatsdateien benötigen eine Kommunalwahl mit AGS.")

    gebiete = landesdaten.get("gebiete")
    if not isinstance(gebiete, dict) or not gebiete:
        raise Fehler(f"{land}: Keine Gemeinden für die Einzeldateien vorhanden.")

    stand = str(landesdaten.get("stand") or date.today().isoformat())
    ordner = GEMEINDERAT_ZIEL / land
    ordner.mkdir(parents=True, exist_ok=True)
    erwartet: set[str] = set()
    geaendert = False

    kopffelder = (
        "wahlart",
        "titel",
        "jahr",
        "wahl_datum",
        "schluesselart",
        "quelle",
        "quellenvermerk",
        "lizenz",
        "lizenz_url",
        "quellendatei",
        "dataset",
        "zitation",
        "quellenseite",
    )
    basis = {
        "land": land,
        "land_name": landesdaten["name"],
        **{feld: landesdaten[feld] for feld in kopffelder if feld in landesdaten},
    }

    for ags, gebiet in sorted(gebiete.items()):
        if not re.fullmatch(r"\d{8}", ags) or not ags.startswith(land):
            raise Fehler(f"{land}: Ungültiger Gemeinde-AGS {ags!r}.")
        if not isinstance(gebiet, dict) or not gebiet.get("name"):
            raise Fehler(f"{land}: Unvollständige Ergebnisdaten für {ags}.")
        dateiname = f"{ags}.json"
        erwartet.add(dateiname)
        inhalt = {
            "ags": ags,
            "name": gebiet["name"],
            **basis,
            **{feld: wert for feld, wert in gebiet.items() if feld != "name"},
        }
        geaendert = schreiben(ordner / dateiname, inhalt, jetzt=stand) or geaendert

    # Nur eindeutig vom Sammler erzeugte achtstellige AGS-Dateien dieses Landes entfernen.
    for datei in ordner.iterdir():
        if datei.is_file() and re.fullmatch(r"\d{8}\.json", datei.name) and datei.name not in erwartet:
            datei.unlink()
            geaendert = True

    erstes_ags = min(gebiete)
    index = {
        "land": land,
        "name": landesdaten["name"],
        "wahlart": "kommunal",
        "ebene": "gemeinde",
        "titel": landesdaten["titel"],
        "jahr": landesdaten["jahr"],
        "wahl_datum": landesdaten.get("wahl_datum", ""),
        "schluesselart": "ags",
        "gemeinden": len(gebiete),
        "dateimuster": "{ags}.json",
        "beispieldatei": f"{erstes_ags}.json",
        **{
            feld: landesdaten[feld]
            for feld in (
                "quelle",
                "quellenvermerk",
                "lizenz",
                "lizenz_url",
                "quellendatei",
                "dataset",
                "zitation",
                "quellenseite",
            )
            if feld in landesdaten
        },
    }
    return schreiben(ordner / "index.json", index, jetzt=stand) or geaendert


def _neuerer_bestand_spiegeln(
    pfade: tuple[Path, ...],
    neues_jahr: int,
    titel: str,
) -> bool:
    """Eine vorhandene neuere Wahl nicht zurückdrehen, aber in beide Pfade spiegeln."""
    vorhandene: list[dict] = []
    for datei in pfade:
        try:
            vorhanden = json.loads(datei.read_text(encoding="utf-8"))
            int(vorhanden.get("jahr", 0))
            vorhandene.append(vorhanden)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
    if not vorhandene:
        return False
    neuester = max(vorhandene, key=lambda daten: int(daten.get("jahr", 0)))
    if int(neuester.get("jahr", 0)) <= int(neues_jahr):
        return False
    _mehrfach_schreiben(pfade, {k: v for k, v in neuester.items() if k != "stand"})
    print(f"  {titel}: vorhandenes Jahr {neuester['jahr']} ist neuer; kein Rückschritt")
    return True


def _land_schreiben(land: dict, ergebnis: dict) -> bool:
    pfade = _ausgabepfade(land["land"], "landtag")
    if _neuerer_bestand_spiegeln(pfade, ergebnis["jahr"], land["name"]):
        return True

    inhalt = {
        "land": land["land"],
        "name": land["name"],
        "titel": f"{land['wahl']} {land['name']} {ergebnis['jahr']}",
        "jahr": ergebnis["jahr"],
        "wahl_datum": ergebnis.get("wahl_datum", ""),
        "schluesselart": "ags",
        **_quellenfelder(ergebnis["quelle"]),
        "gebiete": ergebnis["gebiete"],
    }
    frisch = _mehrfach_schreiben(pfade, inhalt)
    print(
        f"  {land['name']}: {len(ergebnis['gebiete'])} Gebiete, "
        f"{pfade[0].relative_to(WURZEL)} {'geschrieben' if frisch else 'unverändert'}"
    )
    return True


def _gebietswahl_schreiben(land: dict, ergebnis: dict, wahlart: str) -> bool:
    if wahlart == "kommunal":
        titel = f"Gemeinde- und Stadtratswahl {land['name']} {ergebnis['jahr']}"
        schluesselart = "ags"
    elif wahlart == "kreistag":
        titel = f"Kreistagswahl {land['name']} {ergebnis['jahr']}"
        schluesselart = "kreis-ags"
    else:
        raise Fehler(f"Unbekannte Gebietswahl {wahlart!r}.")

    pfade = _ausgabepfade(land["land"], wahlart)
    if _neuerer_bestand_spiegeln(pfade, ergebnis["jahr"], titel):
        if wahlart == "kommunal":
            gespeicherte_daten = json.loads(pfade[0].read_text(encoding="utf-8"))
            frisch = _gemeinderatsdateien_schreiben(gespeicherte_daten)
            print(
                f"    {len(gespeicherte_daten['gebiete'])} Gemeinderats-Einzeldateien "
                f"{'geschrieben' if frisch else 'unverändert'}"
            )
        return True

    inhalt = {
        "land": land["land"],
        "name": land["name"],
        "wahlart": wahlart,
        "titel": titel,
        "jahr": ergebnis["jahr"],
        "wahl_datum": ergebnis.get("wahl_datum", ""),
        "schluesselart": schluesselart,
        **_quellenfelder(ergebnis["quelle"]),
        "gebiete": ergebnis["gebiete"],
    }
    frisch = _mehrfach_schreiben(pfade, inhalt)
    print(
        f"  {titel}: {len(ergebnis['gebiete'])} Gebiete, "
        f"{pfade[0].relative_to(WURZEL)} {'geschrieben' if frisch else 'unverändert'}"
    )
    if wahlart == "kommunal":
        gespeicherte_daten = json.loads(pfade[0].read_text(encoding="utf-8"))
        einzel_frisch = _gemeinderatsdateien_schreiben(gespeicherte_daten)
        print(
            f"    {len(gespeicherte_daten['gebiete'])} Gemeinderats-Einzeldateien "
            f"unter gemeinderat/{land['land']} "
            f"{'geschrieben' if einzel_frisch else 'unverändert'}"
        )
    return True


def _wahl_dateien(wahlart: str) -> list[Path]:
    """Je Land die Ordnerdatei bevorzugen und beim Übergang auf die flache Datei zurückfallen."""
    praefix = {"landtag": "land", "kommunal": "kommunal", "kreistag": "kreistag"}[wahlart]
    dateien: dict[str, Path] = {}
    for datei in sorted(ZIEL.glob(f"{praefix}-*.json")):
        try:
            land = str(json.loads(datei.read_text(encoding="utf-8"))["land"])
        except (KeyError, OSError, json.JSONDecodeError):
            continue
        dateien[land] = datei
    for datei in sorted(ZIEL.glob(f"[0-9][0-9]/{wahlart}.json")):
        dateien[datei.parent.name] = datei
    return [dateien[land] for land in sorted(dateien)]


def _index_schreiben() -> None:
    def kurz(datei: Path, kompatibilitaetsdatei: Path | None = None) -> dict:
        inhalt = json.loads(datei.read_text(encoding="utf-8"))
        eintrag = {
            "titel": inhalt["titel"],
            "jahr": inhalt["jahr"],
            "schluesselart": inhalt.get("schluesselart", "ags"),
            "stand": inhalt["stand"],
            "gebiete": len(inhalt["gebiete"]),
            "quelle": inhalt.get("quelle", ""),
            "lizenz": inhalt.get("lizenz", ""),
            "lizenz_url": inhalt.get("lizenz_url", ""),
            "datei": datei.relative_to(ZIEL).as_posix(),
        }
        if kompatibilitaetsdatei is not None and kompatibilitaetsdatei.exists():
            eintrag["kompatibilitaetsdatei"] = kompatibilitaetsdatei.name
        return eintrag

    def kurz_land(datei: Path, wahlart: str) -> dict:
        inhalt = json.loads(datei.read_text(encoding="utf-8"))
        _, alias = _ausgabepfade(inhalt["land"], wahlart)
        kompatibilitaet = alias if datei != alias else None
        return {
            "land": inhalt["land"],
            "name": inhalt["name"],
            **kurz(datei, kompatibilitaet),
        }

    laender = [kurz_land(datei, "landtag") for datei in _wahl_dateien("landtag")]
    kommunal = [kurz_land(datei, "kommunal") for datei in _wahl_dateien("kommunal")]
    # Nur fuer die Git-only-Datei GEMEINDERAT_ZIEL/index.json gesammelt, nicht Teil von `kommunal`
    # oben (das landet unveraendert in der oeffentlichen daten/index.json - siehe GEMEINDERAT_ZIEL).
    gemeinderat_quelldaten = []
    for eintrag in kommunal:
        land = eintrag["land"]
        gemeindeindex = GEMEINDERAT_ZIEL / land / "index.json"
        if gemeindeindex.exists():
            gemeinderat_quelldaten.append(
                {
                    "land": land,
                    "name": eintrag["name"],
                    "titel": eintrag["titel"],
                    "jahr": eintrag["jahr"],
                    "stand": eintrag["stand"],
                    "gemeinden": eintrag["gebiete"],
                }
            )
    kreistage = [kurz_land(datei, "kreistag") for datei in _wahl_dateien("kreistag")]
    bund = [
        kurz(datei)
        for datei in sorted(ZIEL.glob("*.json"))
        if datei.name != "index.json"
        and not datei.name.startswith(("land-", "kommunal-", "kreistag-"))
    ]
    lizenzen = sorted(
        {
            (eintrag["lizenz"], eintrag["lizenz_url"])
            for eintrag in [*bund, *laender, *kommunal, *kreistage]
            if eintrag["lizenz"]
        }
    )
    jetzt = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    gemeinderat_laender = [
        {
            **eintrag,
            "index": f"{eintrag['land']}/index.json",
            "dateimuster": f"{eintrag['land']}/{{ags}}.json",
        }
        for eintrag in gemeinderat_quelldaten
    ]
    schreiben(
        GEMEINDERAT_ZIEL / "index.json",
        {
            "erzeugt": "",
            "wahlart": "kommunal",
            "ebene": "gemeinde",
            "schluesselart": "ags",
            "beschreibung": (
                "Eine Ergebnisdatei je Gemeinde-AGS. Liegt nur im Git-Repository, nicht auf "
                "daten.plakat-kompass.de (siehe GEMEINDERAT_ZIEL in scripts/sammeln.py)."
            ),
            "dateimuster": "{land}/{ags}.json",
            "einzeldateien": sum(eintrag["gemeinden"] for eintrag in gemeinderat_laender),
            "laender": gemeinderat_laender,
        },
        zeitfeld="erzeugt",
        jetzt=jetzt,
    )
    schreiben(
        ZIEL / "index.json",
        {
            "erzeugt": "",
            "lizenz": "Je Datei unterschiedlich; siehe lizenz und lizenz_url des Eintrags.",
            "lizenz_url": (
                "https://github.com/Parteicoder/Plakat-Kompass-Asset/blob/main/LIZENZ-DATEN.md"
            ),
            "lizenzen": [{"name": name, "url": url} for name, url in lizenzen],
            "bund": bund,
            "laender": laender,
            "kommunal": kommunal,
            "kreistage": kreistage,
        },
        zeitfeld="erzeugt",
        jetzt=jetzt,
    )


def _uebersicht_fuer_github(gescheitert: list[str]) -> None:
    ziel = os.environ.get("GITHUB_STEP_SUMMARY")
    if not ziel:
        return
    zeilen = ["## Gesammelte Dateien", "", "| Datei | Gebiete | Stand |", "|---|---:|---|"]
    bund = [
        datei
        for datei in sorted(ZIEL.glob("*.json"))
        if datei.name != "index.json"
        and not datei.name.startswith(("land-", "kommunal-", "kreistag-"))
    ]
    landesdateien = [
        *_wahl_dateien("landtag"),
        *_wahl_dateien("kommunal"),
        *_wahl_dateien("kreistag"),
    ]
    for datei in [*bund, *landesdateien]:
        try:
            daten = json.loads(datei.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        anzahl = len(daten["gebiete"]) if "gebiete" in daten else ""
        stand = (daten.get("stand") or daten.get("erzeugt") or "")[:10]
        zeilen.append(f"| `{datei.relative_to(ZIEL).as_posix()}` | {anzahl} | {stand} |")
    if gescheitert:
        zeilen += ["", "### Gescheitert", ""] + [f"- {name}" for name in gescheitert]
    with open(ziel, "a", encoding="utf-8") as ausgabe:
        ausgabe.write("\n".join(zeilen) + "\n")


def hauptlauf(
    nur_land: str | None,
    nur_bund: bool = False,
    nur_laender: bool = False,
    nur_kommunal: bool = False,
) -> int:
    konfiguration = json.loads(QUELLEN.read_text(encoding="utf-8"))
    gescheitert: list[str] = []
    verarbeitet = 0

    laender = konfiguration["laender"]
    if nur_land:
        laender = [land for land in laender if land["land"] == nur_land]
        if not laender:
            raise Fehler(f"Kennzahl {nur_land} steht nicht in quellen.json.")

    if not nur_land and not nur_laender and not nur_kommunal:
        print(f"{len(konfiguration.get('bund', []))} Bundeswahlen, Quelle Bundeswahlleiterin")
        for eintrag in konfiguration.get("bund", []):
            try:
                eine_bundeswahl(eintrag)
                verarbeitet += 1
            except Fehler as exc:
                print(f"    FEHLER: {exc}")
                gescheitert.append(eintrag["titel"])

    # ponytail: gerda_gesperrt ist ein temporärer Ausschluss (Genehmigung ausstehend,
    # siehe quellen.json), keine dauerhafte Architektur - Land einfach wieder in den
    # normalen Lauf lassen, sobald die Genehmigung vorliegt.
    gesperrt = {eintrag["land"] for eintrag in konfiguration.get("gerda_gesperrt", [])}

    if not nur_bund and not nur_kommunal:
        ergebnisse, fehler = _laender_holen(konfiguration, laender)
        gescheitert.extend(fehler)
        for land in laender:
            if land["land"] in gesperrt:
                print(f"  {land['name']}: zurückgehalten (Genehmigung ausstehend, siehe quellen.json)")
                continue
            ergebnis = ergebnisse.get(land["land"])
            if ergebnis is None:
                gescheitert.append(land["name"])
                continue
            _land_schreiben(land, ergebnis)
            verarbeitet += 1

    if not nur_bund and not nur_laender:
        kommunal, kreistage, fehler = _kommunal_holen(konfiguration, laender)
        gescheitert.extend(fehler)
        for land in laender:
            landkennzahl = land["land"]
            if landkennzahl in gesperrt:
                print(f"  {land['name']}: Gemeinde-/Stadtrats- und Kreistagswahl zurückgehalten (Genehmigung ausstehend, siehe quellen.json)")
                continue
            kommunalergebnis = kommunal.get(landkennzahl)
            if kommunalergebnis is None:
                gescheitert.append(f"Gemeinde-/Stadtratswahl {land['name']}")
            else:
                _gebietswahl_schreiben(land, kommunalergebnis, "kommunal")
                verarbeitet += 1

            # Stadtstaaten und kreisfreie Städte haben keinen Kreistag. Für die drei Stadtstaaten
            # gibt es deshalb absichtlich keine Datei und auch keinen Fehler.
            kreistagsergebnis = kreistage.get(landkennzahl)
            if kreistagsergebnis is not None:
                _gebietswahl_schreiben(land, kreistagsergebnis, "kreistag")
                verarbeitet += 1
            elif landkennzahl not in {"02", "04", "11"}:
                gescheitert.append(f"Kreistagswahl {land['name']}")

    _index_schreiben()
    print(f"\nFertig: {verarbeitet} Dateien verarbeitet, {len(gescheitert)} Fehler")
    if gescheitert:
        print("  gescheitert: " + ", ".join(dict.fromkeys(gescheitert)))
    _uebersicht_fuer_github(list(dict.fromkeys(gescheitert)))
    return 1 if gescheitert else 0


def main() -> int:
    zerleger = argparse.ArgumentParser(description="Wahldaten aus GERDA und offenen amtlichen Dateien sammeln.")
    zerleger.add_argument("--land", metavar="NN", help="nur diese Landkennzahl (1 bis 16)")
    gruppe = zerleger.add_mutually_exclusive_group()
    gruppe.add_argument("--nur-bund", action="store_true", help="nur Bundestags- und Europawahl")
    gruppe.add_argument("--nur-laender", action="store_true", help="nur die sechzehn Landtagswahlen")
    gruppe.add_argument(
        "--nur-kommunal",
        action="store_true",
        help="nur Gemeinde-/Stadtrats- und Kreistagswahlen",
    )
    argumente = zerleger.parse_args()

    try:
        nur_land = None
        if argumente.land:
            if not argumente.land.isdigit() or not 1 <= int(argumente.land) <= 16:
                raise Fehler("--land erwartet eine Zahl von 1 bis 16.")
            if argumente.nur_bund:
                raise Fehler("--land und --nur-bund schließen sich aus.")
            nur_land = f"{int(argumente.land):02d}"
        return hauptlauf(
            nur_land,
            argumente.nur_bund,
            argumente.nur_laender,
            argumente.nur_kommunal,
        )
    except Fehler as exc:
        print(f"\nAbbruch: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
