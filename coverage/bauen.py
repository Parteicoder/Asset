#!/usr/bin/env python3
"""Offline-Bündel für die Campaign-Coverage-Heatmap bauen.

Anders als der Wahldaten-Sammler braucht diese räumliche Pipeline bewusst Fremdpakete:
pyosmium streamt das OSM-PBF, Shapely schneidet Geometrien und h3 4.x erzeugt die Hexagone.
Die unterstützten Hauptversionen stehen in ``coverage/requirements.txt``; insbesondere wird die
h3-4.x-API ``polygon_to_cells(LatLngPoly(...))`` vorausgesetzt.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path


WURZEL = Path(__file__).resolve().parent.parent
ZIEL = WURZEL / "daten" / "coverage"
H3_AUFLOESUNG = 8
FORMELVERSION = "coverage-formula-v1"
WFS_ADRESSE = "https://sgx.geodatenzentrum.de/wfs_vg250"
WFS_SEITENGROESSE = 1000
USER_AGENT = "PlakatKompassAsset/2.0 (+https://github.com/Parteicoder/Plakat-Kompass-Asset)"

# Die Veröffentlichungs-URL kann sich ändern. Nach Prüfung der Landingpage hier eintragen oder
# beim Lauf den bereits geladenen ZIP mit --zensus-zip übergeben.
ZENSUS_ZIP_URL = ""

RELEVANTE_STRASSENTYPEN = {
    "residential",
    "living_street",
    "pedestrian",
    "footway",
    "path",
    "service",
    "unclassified",
    "tertiary",
    "secondary",
}

A = 6_378_137.0
F = 1.0 / 298.257222101
E2 = F * (2.0 - F)
E = math.sqrt(E2)
LAT0 = math.radians(52.0)
LON0 = math.radians(10.0)
FALSE_EASTING = 4_321_000.0
FALSE_NORTHING = 3_210_000.0


class Fehler(Exception):
    """Ein Abbruch mit einer Erklärung, die im Actions-Protokoll verständlich bleibt."""


def _q(phi: float) -> float:
    s = math.sin(phi)
    return (1.0 - E2) * (
        s / (1.0 - E2 * s * s)
        - (1.0 / (2.0 * E)) * math.log((1.0 - E * s) / (1.0 + E * s))
    )


def epsg3035(lon_deg: float, lat_deg: float) -> tuple[float, float]:
    """WGS84-Grad -> EPSG:3035-Meter (ETRS89-LAEA Europa). easting, northing."""
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    qp = _q(math.pi / 2.0)
    q0 = _q(LAT0)
    q = _q(lat)
    beta0 = math.asin(q0 / qp)
    beta = math.asin(q / qp)
    rq = A * math.sqrt(qp / 2.0)
    d = A * (math.cos(LAT0) / math.sqrt(1.0 - E2 * math.sin(LAT0) ** 2)) / (
        rq * math.cos(beta0)
    )
    b = rq * math.sqrt(
        2.0
        / (
            1.0
            + math.sin(beta0) * math.sin(beta)
            + math.cos(beta0) * math.cos(beta) * math.cos(lon - LON0)
        )
    )
    easting = FALSE_EASTING + b * d * math.cos(beta) * math.sin(lon - LON0)
    northing = FALSE_NORTHING + (b / d) * (
        math.cos(beta0) * math.sin(beta)
        - math.sin(beta0) * math.cos(beta) * math.cos(lon - LON0)
    )
    return easting, northing


def zensus_zell_id(easting: float, northing: float, zellgroesse_m: int = 100) -> str:
    """INSPIRE-/Zensus-Zell-ID im Format des Bulk-CSVs zurückgeben."""
    e = int(math.floor(easting / zellgroesse_m)) * zellgroesse_m
    n = int(math.floor(northing / zellgroesse_m)) * zellgroesse_m
    return f"{zellgroesse_m}mN{n // zellgroesse_m}E{e // zellgroesse_m}"


def ist_relevante_strasse(merkmale) -> bool:
    """Den in Coverage Score v1 festgelegten OSM-Filter anwenden."""
    return (
        merkmale.get("highway") in RELEVANTE_STRASSENTYPEN
        and merkmale.get("foot") != "no"
        and merkmale.get("access") != "private"
    )


def schreiben(datei: Path, inhalt: dict) -> bool:
    """Nur bei einer inhaltlichen Änderung schreiben."""
    if datei.exists():
        try:
            if json.loads(datei.read_text(encoding="utf-8")) == inhalt:
                return False
        except (OSError, json.JSONDecodeError):
            pass
    datei.parent.mkdir(parents=True, exist_ok=True)
    datei.write_text(json.dumps(inhalt, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return True


def _normalisiert(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def _zensus_spalten(feldnamen: list[str]) -> tuple[str, str, str]:
    """Gibt (x_mp-Spalte, y_mp-Spalte, Einwohner-Spalte) zurück.

    Die echte Zensus-2022-Bulk-Datei (``Zensus2022_Bevoelkerungszahl_100m-Gitter.csv``) liefert
    die Zellmitte bereits als EPSG:3035-Meter in ``x_mp_100m``/``y_mp_100m`` — daraus wird die
    Gitter-ID selbst über :func:`zensus_zell_id` berechnet, statt die ``GITTER_ID_100m``-Spalte zu
    parsen. Die dort verwendete Schreibweise (``CRS3035RES100mN..E..``) unterscheidet sich vom
    kürzeren Schema, das dieses Modul sonst verwendet; ein eigener Koordinaten-Rechenweg macht das
    Ergebnis unabhängig von einer bestimmten ID-Schreibweise.
    """
    einwohner = next(
        (
            name
            for name in feldnamen
            if "einwohner" in _normalisiert(name) or _normalisiert(name) == "ewz"
        ),
        None,
    )
    if einwohner is None:
        raise Fehler("Zensus-CSV: Keine Einwohner-Spalte in der Kopfzeile gefunden.")
    x_spalte = next((name for name in feldnamen if _normalisiert(name).startswith("xmp")), None)
    y_spalte = next((name for name in feldnamen if _normalisiert(name).startswith("ymp")), None)
    if x_spalte is None or y_spalte is None:
        raise Fehler("Zensus-CSV: Keine x_mp/y_mp-Spalten (Zellmitte) in der Kopfzeile gefunden.")
    return x_spalte, y_spalte, einwohner


def _zensus_text_laden(eingabe: io.TextIOBase) -> dict[str, int]:
    probe = eingabe.read(8192)
    eingabe.seek(0)
    try:
        trennzeichen = csv.Sniffer().sniff(probe, delimiters=";,\t").delimiter
    except csv.Error as exc:
        raise Fehler("Zensus-CSV: Trennzeichen nicht erkennbar.") from exc
    leser = csv.DictReader(eingabe, delimiter=trennzeichen)
    x_spalte, y_spalte, einwohnerspalte = _zensus_spalten(leser.fieldnames or [])
    ergebnis: dict[str, int] = {}
    for nummer, zeile in enumerate(leser, 2):
        roh_x = (zeile.get(x_spalte) or "").strip()
        roh_y = (zeile.get(y_spalte) or "").strip()
        roh_einwohner = (zeile.get(einwohnerspalte) or "").strip()
        try:
            x_mp = float(roh_x)
            y_mp = float(roh_y)
        except ValueError as exc:
            raise Fehler(f"Zensus-CSV Zeile {nummer}: ungültige Zellmitte ({roh_x!r}, {roh_y!r}).") from exc
        try:
            einwohner = int(roh_einwohner)
        except ValueError as exc:
            raise Fehler(f"Zensus-CSV Zeile {nummer}: ungültige Einwohnerzahl {roh_einwohner!r}.") from exc
        if einwohner < 0:
            raise Fehler(f"Zensus-CSV Zeile {nummer}: negative Einwohnerzahl {einwohner}.")
        kennung = zensus_zell_id(x_mp, y_mp)
        if kennung in ergebnis:
            raise Fehler(f"Zensus-CSV Zeile {nummer}: doppelte Gitterzelle {kennung}.")
        ergebnis[kennung] = einwohner
    if not ergebnis:
        raise Fehler("Zensus-CSV enthält keine Datenzeilen.")
    return ergebnis


def zensus_laden(datei: Path) -> dict[str, int]:
    """Bevölkerungswerte aus einem Zensus-ZIP oder einer Fixture-CSV lesen."""
    try:
        if zipfile.is_zipfile(datei):
            with zipfile.ZipFile(datei) as archiv:
                csv_dateien = [info for info in archiv.infolist() if info.filename.lower().endswith(".csv")]
                if not csv_dateien:
                    raise Fehler("Zensus-ZIP enthält keine CSV.")
                # Die Datendatei ist größer als mögliche Begleit-/Schema-CSVs.
                daten_csv = max(csv_dateien, key=lambda info: info.file_size)
                with archiv.open(daten_csv) as roh:
                    return _zensus_text_laden(io.TextIOWrapper(roh, encoding="utf-8-sig"))
        with datei.open(encoding="utf-8-sig", newline="") as eingabe:
            return _zensus_text_laden(eingabe)
    except (OSError, zipfile.BadZipFile, UnicodeError) as exc:
        raise Fehler(f"Zensus-Datei ist nicht lesbar: {exc}") from exc


def wfs_seiten(
    typenames: str,
    cql_filter: str | None = None,
    sortby: str = "ags",
    stats: dict | None = None,
):
    """VG250-Features eines Layers paginiert einzeln liefern (roh, ungeprüft).

    Gemeinsamer HTTP-/Paginierungskern für [gemeinden_laden] und weitere VG250-Layer (z. B.
    Kreise, oder Gemeinden ohne Geofaktor-Filter für die Gebiets-Offline-Daten) - die inhaltliche
    Prüfung (welche Felder Pflicht sind, was ein Duplikat bedeutet) bleibt bewusst bei den
    Aufrufern, die unterscheidet sich je Layer/Zweck.

    Wenn `stats` übergeben wird, trägt diese Funktion `stats["erwartet"]` mit der vom Server
    gemeldeten Gesamtzahl (`numberMatched`) ein - der Aufrufer kann das nach dem Verbrauch aller
    Elemente gegen seine eigene Zählung prüfen (Paginierung könnte sonst still unvollständig sein).
    """
    erwartet: int | None = None
    start = 0
    while True:
        parameter = {
            "SERVICE": "WFS",
            "REQUEST": "GetFeature",
            "VERSION": "2.0.0",
            "TYPENAMES": typenames,
            "OUTPUTFORMAT": "application/json",
            "SRSNAME": "EPSG:4326",
            "COUNT": WFS_SEITENGROESSE,
            "STARTINDEX": start,
            # Ohne feste Sortierung ist die Reihenfolge zwischen zwei GetFeature-Aufrufen laut
            # WFS-Spezifikation nicht garantiert stabil - STARTINDEX-Paginierung könnte dann
            # Elemente überspringen oder doppelt liefern. Bei mehreren Datensätzen mit demselben
            # `ags` (z. B. Gemeinden ohne Geofaktor-Filter, siehe gebiete_bauen.py) reicht "ags"
            # allein nicht als eindeutige Sortierung - Aufrufer können mit `sortby` ein weiteres
            # Feld anhängen (z. B. "ags,gf"), um eine echte Totalordnung zu erzwingen.
            "SORTBY": sortby,
        }
        if cql_filter:
            parameter["CQL_FILTER"] = cql_filter
        anfrage = urllib.request.Request(
            f"{WFS_ADRESSE}?{urllib.parse.urlencode(parameter)}", headers={"User-Agent": USER_AGENT}
        )
        try:
            with urllib.request.urlopen(anfrage, timeout=300) as antwort:
                seite = json.load(antwort)
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            raise Fehler(f"VG250-Abruf ({typenames}) ab Seite {start} fehlgeschlagen: {exc}") from exc
        features = seite.get("features")
        if not isinstance(features, list):
            raise Fehler(f"VG250-Seite ({typenames}) ab {start} enthält keine Feature-Liste.")
        seiten_erwartet = seite.get("numberMatched")
        if isinstance(seiten_erwartet, int):
            if erwartet is None:
                erwartet = seiten_erwartet
                if stats is not None:
                    stats["erwartet"] = erwartet
            elif seiten_erwartet != erwartet:
                raise Fehler(
                    f"VG250 ({typenames}): Gesamtzahl änderte sich während der Paginierung "
                    f"({erwartet} -> {seiten_erwartet}) - Datensatz vermutlich mitten im Abruf "
                    "aktualisiert."
                )
        yield from features
        if len(features) < WFS_SEITENGROESSE:
            return
        start += WFS_SEITENGROESSE


def gemeinden_laden() -> dict[str, tuple[str, object]]:
    """Alle VG250-Gemeinden paginiert als WGS84-Geometrien laden."""
    try:
        from shapely.geometry import shape
    except ImportError as exc:
        raise Fehler("Shapely fehlt; coverage/requirements.txt installieren.") from exc

    gemeinden: dict[str, tuple[str, object]] = {}
    stats: dict = {}
    for feature in wfs_seiten(
        "vg250:vg250_gem",
        # GF (Geofaktor) 4 = Landfläche, genau ein Datensatz je Gemeinde. Küsten-
        # Gemeinden an Nord-/Ostsee/Bodensee haben zusätzlich einen GF=2-Datensatz für
        # ihre Wasserfläche (VG250-Dokumentation Abschnitt 2.5/3.2.2) - ohne diesen
        # Filter taucht z. B. Flensburg zweimal mit demselben AGS auf. Für die H3-Hexagon-
        # Generierung reicht die Landfläche (Zellmittelpunkte liegen praktisch nie im Wasser);
        # für die vollständige Verwaltungsgrenze in coverage/gebiete_bauen.py wird bewusst
        # ohne diesen Filter geladen und je AGS vereinigt, siehe dort.
        cql_filter="gf=4",
        stats=stats,
    ):
        eigenschaften = feature.get("properties") or {}
        ags = str(eigenschaften.get("ags") or "")
        name = str(eigenschaften.get("gen") or "").strip()
        geometrie = shape(feature.get("geometry"))
        if not re.fullmatch(r"\d{8}", ags) or not name or geometrie.geom_type not in {
            "Polygon",
            "MultiPolygon",
        }:
            raise Fehler(f"VG250: ungültige Gemeinde {ags!r} ({name!r}).")
        if ags in gemeinden:
            raise Fehler(f"VG250 enthält den AGS {ags} mehrfach.")
        gemeinden[ags] = (name, geometrie)
        if len(gemeinden) % WFS_SEITENGROESSE == 0:
            print(f"  VG250: {len(gemeinden)} Gemeinden geladen")
    print(f"  VG250: {len(gemeinden)} Gemeinden geladen")
    if stats.get("erwartet") is not None and len(gemeinden) != stats["erwartet"]:
        raise Fehler(
            f"VG250: {len(gemeinden)} Gemeinden geladen, der Server meldete aber "
            f"{stats['erwartet']} insgesamt - Paginierung vermutlich unvollständig."
        )
    return gemeinden


def strassen_laden(datei: Path, ausschnitt: tuple[float, float, float, float] | None = None) -> list[object]:
    """Relevante OSM-Ways aus dem PBF streamen und als WGS84-Linien sammeln."""
    try:
        import osmium
        from shapely.geometry import LineString
    except ImportError as exc:
        raise Fehler("osmium oder Shapely fehlt; coverage/requirements.txt installieren.") from exc

    strassen: list[object] = []

    class StrassenHandler(osmium.SimpleHandler):
        def way(self, way):
            if not ist_relevante_strasse(way.tags):
                return
            try:
                koordinaten = [(knoten.lon, knoten.lat) for knoten in way.nodes]
            except osmium.InvalidLocationError:
                return
            if len(koordinaten) < 2:
                return
            linie = LineString(koordinaten)
            if ausschnitt is None or not (
                linie.bounds[2] < ausschnitt[0]
                or linie.bounds[0] > ausschnitt[2]
                or linie.bounds[3] < ausschnitt[1]
                or linie.bounds[1] > ausschnitt[3]
            ):
                strassen.append(linie)

    try:
        StrassenHandler().apply_file(str(datei), locations=True, idx="flex_mem")
    except (OSError, RuntimeError) as exc:
        raise Fehler(f"OSM-PBF ist nicht lesbar: {exc}") from exc
    print(f"  OSM: {len(strassen)} relevante Ways geladen")
    return strassen


def _polygone(geometrie):
    return [geometrie] if geometrie.geom_type == "Polygon" else list(geometrie.geoms)


def _h3_zellen(geometrie) -> set[str]:
    try:
        import h3
    except ImportError as exc:
        raise Fehler("h3 fehlt; coverage/requirements.txt installieren.") from exc
    zellen: set[str] = set()
    for polygon in _polygone(geometrie):
        aussen = [(lat, lon) for lon, lat in list(polygon.exterior.coords)[:-1]]
        loecher = [
            [(lat, lon) for lon, lat in list(ring.coords)[:-1]] for ring in polygon.interiors
        ]
        zellen.update(h3.polygon_to_cells(h3.LatLngPoly(aussen, *loecher), H3_AUFLOESUNG))
    if not zellen:
        # H3 zaehlt eine Zelle nur ueber ihren Mittelpunkt zur Gemeinde. Sehr kleine oder
        # schmale Gemeinden (z. B. Insel Lütje Hörn) können dadurch ganz ohne Zelle bleiben -
        # ein formal gültiges, aber leeres Bündel wäre echter Coverage-Datenverlust. Der
        # garantiert innenliegende representative_point() liefert wenigstens eine Zelle.
        punkt = geometrie.representative_point()
        zellen.add(h3.latlng_to_cell(punkt.y, punkt.x, H3_AUFLOESUNG))
    return zellen


def _hexagon(zelle: str):
    import h3
    from shapely.geometry import Polygon

    return Polygon([(lon, lat) for lat, lon in h3.cell_to_boundary(zelle)])


def _projiziertes_polygon(polygon):
    from shapely.geometry import Polygon

    return Polygon(
        [epsg3035(lon, lat) for lon, lat in polygon.exterior.coords],
        [[epsg3035(lon, lat) for lon, lat in ring.coords] for ring in polygon.interiors],
    )


def _linienlaenge_m(geometrie) -> float:
    if geometrie.is_empty:
        return 0.0
    if geometrie.geom_type in {"LineString", "LinearRing"}:
        punkte = [epsg3035(lon, lat) for lon, lat in geometrie.coords]
        return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(punkte, punkte[1:]))
    if hasattr(geometrie, "geoms"):
        return sum(_linienlaenge_m(teil) for teil in geometrie.geoms)
    return 0.0


def _zensus_im_hexagon(hexagon, bevoelkerung: dict[str, int]) -> tuple[int, int]:
    from shapely.geometry import Point

    projiziert = _projiziertes_polygon(hexagon)
    min_e, min_n, max_e, max_n = projiziert.bounds
    erstes_e = math.floor(min_e / 100) * 100
    erstes_n = math.floor(min_n / 100) * 100
    summe = 0
    gefunden = 0
    for easting in range(erstes_e, math.ceil(max_e / 100) * 100, 100):
        for northing in range(erstes_n, math.ceil(max_n / 100) * 100, 100):
            if not projiziert.contains(Point(easting + 50, northing + 50)):
                continue
            kennung = zensus_zell_id(easting + 50, northing + 50)
            if kennung in bevoelkerung:
                summe += bevoelkerung[kennung]
                gefunden += 1
    return summe, gefunden


def buendel_bauen(
    gemeinden: dict[str, tuple[str, object]],
    strassen: list[object],
    bevoelkerung: dict[str, int],
    ziel: Path = ZIEL,
    alle_gemeinden: dict[str, tuple[str, object]] | None = None,
) -> tuple[int, int]:
    """Coverage-Zellen berechnen und je Gemeinde idempotent schreiben."""
    try:
        import h3
        from shapely.geometry import Point
        from shapely.strtree import STRtree
    except ImportError as exc:
        raise Fehler("Shapely oder h3 fehlt; coverage/requirements.txt installieren.") from exc

    zellen_je_gemeinde = {ags: _h3_zellen(geometrie) for ags, (_, geometrie) in gemeinden.items()}
    alle_zellen = sorted(set().union(*zellen_je_gemeinde.values())) if zellen_je_gemeinde else []
    strassenbaum = STRtree(strassen) if strassen else None
    eigentuemer = alle_gemeinden or gemeinden
    gemeinde_geometrien = [daten[1] for daten in eigentuemer.values()]
    gemeindebaum = STRtree(gemeinde_geometrien)
    berechnet: dict[str, dict] = {}

    for nummer, zelle in enumerate(alle_zellen, 1):
        hexagon = _hexagon(zelle)
        schnitte = (
            [
                strassen[int(i)].intersection(hexagon)
                for i in strassenbaum.query(hexagon, predicate="intersects")
            ]
            if strassenbaum is not None
            else []
        )
        strassenmeter = sum(_linienlaenge_m(schnitt) for schnitt in schnitte)
        einwohner, zensuszellen = _zensus_im_hexagon(hexagon, bevoelkerung)
        lat, lon = h3.cell_to_latlng(zelle)
        mittelpunkt = Point(lon, lat)
        ueberlappungen = sum(
            gemeinde_geometrien[int(i)].covers(mittelpunkt) for i in gemeindebaum.query(mittelpunkt)
        )
        flags = []
        if ueberlappungen > 1:
            flags.append("GEBIETSGRENZE_UNKLAR")
        # Die Zensus-2022-Veröffentlichung unterdrückt Gitterzellen mit weniger als drei
        # Einwohnern aus Datenschutzgründen vollständig - `zensuszellen == 0` heißt hier meist
        # "kaum bis gar nicht bewohnt", nicht "Statistik fehlt oder ist veraltet". Laut
        # docs/coverage-score-v1.md ist genau dafür `populationDensity = null` vorgesehen (der
        # Score-Engine behandelt das als neutral), nicht das STATISTIK_VERALTET-Flag - das
        # bedeutet dort ausdrücklich "Zuordnung älter als eine dokumentierte Aktualisierungs-
        # frist", eine Prüfung, die dieser Builder (noch) nicht durchführt.
        dichte = round(einwohner / h3.cell_area(zelle, unit="km^2"), 1) if zensuszellen else None
        # Eckpunkte hier vorberechnen statt eine H3-Bibliothek in der Android-App zu brauchen -
        # com.uber:h3 verlangt dort NDK+CMake fuer eine native .so je ABI, waehrend h3-python
        # hier schon Pflicht ist. Geschlossener Ring (erster Punkt am Ende wiederholt): H3
        # verlangt das nicht, aber der Android-Kartenrenderer bekommt so ohne eigene Fallunter-
        # scheidung immer eine geschlossene Flaeche.
        rand = [[lat, lon] for lat, lon in h3.cell_to_boundary(zelle)]
        rand.append(rand[0])
        berechnet[zelle] = {
            "h3CellId": zelle,
            "boundary": rand,
            "relevantRoadKm": round(strassenmeter / 1000.0, 3),
            "populationDensity": dichte,
            "dataQualityFlags": flags,
            "_einwohner": einwohner,
            "_hat_strasse": strassenmeter > 0.0,
        }
        if nummer % 10_000 == 0:
            print(f"  Coverage: {nummer}/{len(alle_zellen)} Zellen berechnet")

    geschrieben = 0
    for ags, zellen in sorted(zellen_je_gemeinde.items()):
        bewohnt = any(berechnet[zelle]["_einwohner"] > 0 for zelle in zellen)
        ausgabe = []
        for zelle in sorted(zellen):
            eintrag = {k: v for k, v in berechnet[zelle].items() if not k.startswith("_")}
            if bewohnt and not berechnet[zelle]["_hat_strasse"]:
                eintrag["dataQualityFlags"] = [
                    "STRASSENNETZ_UNVOLLSTAENDIG",
                    *eintrag["dataQualityFlags"],
                ]
            ausgabe.append(eintrag)
        inhalt = {"gemeindeAgs": ags, "formulaVersion": FORMELVERSION, "zellen": ausgabe}
        geschrieben += schreiben(ziel / f"{ags}.json", inhalt)
    return len(alle_zellen), geschrieben


def _argumente() -> argparse.Namespace:
    zerleger = argparse.ArgumentParser(description="Offline-Coverage-Bündel aus VG250, OSM und Zensus bauen.")
    zerleger.add_argument("--land", metavar="NN", help="nur diese zweistellige Landkennzahl")
    zerleger.add_argument("--nur-gemeinde", metavar="AGS", help="nur diese achtstellige Gemeinde")
    zerleger.add_argument("--osm-pbf", type=Path, required=True, help="lokale germany.osm.pbf")
    zerleger.add_argument(
        "--zensus-zip",
        type=Path,
        help="lokaler Zensus-2022-Bevölkerungs-ZIP (nötig, solange ZENSUS_ZIP_URL leer ist)",
    )
    return zerleger.parse_args()


def main() -> int:
    argumente = _argumente()
    try:
        if argumente.land and not re.fullmatch(r"(?:0[1-9]|1[0-6])", argumente.land):
            raise Fehler("--land erwartet eine zweistellige Kennzahl von 01 bis 16.")
        if argumente.nur_gemeinde and not re.fullmatch(r"\d{8}", argumente.nur_gemeinde):
            raise Fehler("--nur-gemeinde erwartet einen achtstelligen AGS.")
        if (
            argumente.land
            and argumente.nur_gemeinde
            and not argumente.nur_gemeinde.startswith(argumente.land)
        ):
            raise Fehler("--land und --nur-gemeinde widersprechen sich.")
        if not argumente.osm_pbf.is_file():
            raise Fehler(f"OSM-PBF nicht gefunden: {argumente.osm_pbf}")
        if argumente.zensus_zip is not None and not argumente.zensus_zip.is_file():
            raise Fehler(f"Zensus-ZIP nicht gefunden: {argumente.zensus_zip}")

        print("VG250-Gemeinden")
        alle = gemeinden_laden()
        gemeinden = {
            ags: daten
            for ags, daten in alle.items()
            if (not argumente.land or ags.startswith(argumente.land))
            and (not argumente.nur_gemeinde or ags == argumente.nur_gemeinde)
        }
        if not gemeinden:
            raise Fehler("Die Auswahl enthält keine Gemeinde.")
        print(f"  Auswahl: {len(gemeinden)} Gemeinden")
        if argumente.zensus_zip is not None:
            bevoelkerung = zensus_laden(argumente.zensus_zip)
        else:
            if not ZENSUS_ZIP_URL:
                raise Fehler("Zensus-URL ist noch nicht bestätigt; --zensus-zip angeben.")
            with tempfile.TemporaryDirectory(prefix="coverage-zensus-") as ordner:
                zensus_datei = Path(ordner) / "zensus.zip"
                anfrage = urllib.request.Request(ZENSUS_ZIP_URL, headers={"User-Agent": USER_AGENT})
                try:
                    with urllib.request.urlopen(anfrage, timeout=300) as antwort:
                        with zensus_datei.open("wb") as ausgabe:
                            shutil.copyfileobj(antwort, ausgabe, length=1024 * 1024)
                except (urllib.error.URLError, OSError) as exc:
                    raise Fehler(f"Zensus-Download fehlgeschlagen: {exc}") from exc
                bevoelkerung = zensus_laden(zensus_datei)
        print(f"  Zensus: {len(bevoelkerung)} Gitterzellen geladen")
        min_lon = min(daten[1].bounds[0] for daten in gemeinden.values()) - 0.02
        min_lat = min(daten[1].bounds[1] for daten in gemeinden.values()) - 0.02
        max_lon = max(daten[1].bounds[2] for daten in gemeinden.values()) + 0.02
        max_lat = max(daten[1].bounds[3] for daten in gemeinden.values()) + 0.02
        strassen = strassen_laden(argumente.osm_pbf, (min_lon, min_lat, max_lon, max_lat))
        zellen, geschrieben = buendel_bauen(gemeinden, strassen, bevoelkerung, alle_gemeinden=alle)
        print(f"Fertig: {zellen} H3-Zellen, {geschrieben}/{len(gemeinden)} Bündel geschrieben")
        return 0
    except Fehler as exc:
        print(f"\nAbbruch: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
