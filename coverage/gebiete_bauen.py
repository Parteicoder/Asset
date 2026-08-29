#!/usr/bin/env python3
"""Offline-Gebietsdaten (AGS-Lookup + Gemeindegrenze) fürs Feld ohne Overpass bauen.

Löst dasselbe Problem, das schon einmal für die Coverage-Heatmap gelöst wurde
(Sub-Projekt 3): die App fragt bisher live bei jeder Kartenbewegung beim
öffentlichen Overpass-API ab, welche Gemeinde (AGS) unter einem Punkt liegt und
wie deren Umriss aussieht - im Feld unzuverlässig. VG250 liegt hier über
``bauen.py`` schon vollständig im Speicher; nur die Geometrie selbst wurde
bisher nie veröffentlicht, nur die daraus abgeleiteten H3-Zellen.

Ein File je Gemeinde (wie bei ``daten/coverage/<ags>.json``) sprengt Cloudflare
Pages' ~20.000-Dateien-Limit (``daten/`` liegt schon bei rund 19.500 Dateien) -
deshalb hier ein File je Bundesland (16 Dateien, ``daten/gebiete/v1/<land>.
json.gz``) plus ein winziger, in die APK gebündelter "Land-Router"
(``router.json``, 16 grob vereinfachte Bundesland-Umrisse), der das
Henne-Ei-Problem löst: welche Landdatei überhaupt laden, bevor man weiß, in
welchem Bundesland der Punkt liegt.

Koordinaten werden als E6-Integer (Grad × 1.000.000, gerundet) gespeichert -
kleiner als Fließkomma-JSON und eindeutig dekodierbar, sowohl hier als auch in
Kotlin.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import io
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bauen  # noqa: E402


ZIEL = bauen.WURZEL / "daten" / "gebiete" / "v1"

# Gleiche Zahl wie ``coverage/bauen.py`` für einen kompletten Deutschland-Lauf liefert (siehe
# ``daten/coverage/*.json``-Dateienzahl). Bei einer echten VG250-Bestandsänderung bewusst
# aktualisieren, nicht stillschweigend übernehmen.
ERWARTETE_GEMEINDEN_GESAMT = 10_949

# Cloudflare Pages begrenzt einzelne Assets auf 25 MiB; 20 MiB Marge, bevor eine Vereinfachung
# nötig wird (siehe Docstring oben - VG250 wird im ersten Wurf bewusst NICHT vereinfacht).
MAX_DATEIGROESSE_BYTES = 20 * 1024 * 1024

# Nur zur Vorauswahl der Landdatei gedacht, nicht für die eigentliche Zuordnung - deshalb grob.
LAND_SIMPLIFY_TOLERANZ_GRAD = 0.01  # ~1 km
# Blähen den vereinfachten Umriss künstlich auf, damit ein Punkt nahe einer Landesgrenze in BEIDEN
# benachbarten Land-Umrissen liegt. Die App probiert dann beide Landdateien durch, statt bei einer
# knapp falschen Zuordnung leer auszugehen - die exakte Zuordnung passiert ohnehin erst über die
# echten Gemeinde-Polygone in der Landdatei selbst.
LAND_PUFFER_GRAD = 0.03  # ~3 km


def gemeinden_vollstaendig_laden() -> dict[str, tuple[str, object]]:
    """Alle VG250-Gemeinde-Anteile (alle Geofaktoren) laden und je AGS vereinigen.

    Anders als ``bauen.gemeinden_laden()`` (die bewusst nur die Landfläche, GF=4, für die
    H3-Hexagon-Erzeugung nimmt, siehe Kommentar dort): für eine vollständige Verwaltungsgrenze
    zum Zeichnen und für ein korrektes AGS-Lookup auch nahe Küsten/Seen muss die GESAMTE
    Gemeindefläche her, einschließlich der separaten Wasserflächen-Datensätze, die VG250 je
    Küsten-Gemeinde zusätzlich führt (Nord-/Ostsee/Bodensee). Deshalb hier ohne CQL_FILTER laden
    und je AGS mit ``unary_union`` vereinigen, statt wie ``gemeinden_laden`` ein Duplikat als
    Fehler zu werten - mehrere Anteile je AGS sind hier der Normalfall, nicht die Ausnahme.
    """
    try:
        from shapely.geometry import shape
        from shapely.ops import unary_union
    except ImportError as exc:
        raise bauen.Fehler("Shapely fehlt; coverage/requirements.txt installieren.") from exc

    teile: dict[str, list] = {}
    namen: dict[str, str] = {}
    stats: dict = {}
    anzahl_anteile = 0
    # "ags,gf" statt nur "ags": mehrere Anteile teilen sich hier denselben AGS (Land- und
    # Wasserfläche), "ags" allein ist also keine eindeutige Sortierung mehr - ohne ein
    # zusätzliches, eindeutiges Sortierfeld ist die Reihenfolge gleicher AGS zwischen zwei
    # STARTINDEX-Aufrufen laut WFS-Spezifikation nicht garantiert stabil (ein Anteil könnte
    # zwischen zwei Seiten verschwinden, während ein anderer doppelt auftaucht - die
    # Gesamtzahl bliebe dabei unauffällig gleich).
    for feature in bauen.wfs_seiten("vg250:vg250_gem", sortby="ags,gf", stats=stats):
        eigenschaften = feature.get("properties") or {}
        ags = str(eigenschaften.get("ags") or "")
        name = str(eigenschaften.get("gen") or "").strip()
        geometrie = shape(feature.get("geometry"))
        if not re.fullmatch(r"\d{8}", ags) or not name or geometrie.geom_type not in {
            "Polygon",
            "MultiPolygon",
        }:
            raise bauen.Fehler(f"VG250: ungültiger Gemeinde-Anteil {ags!r} ({name!r}).")
        # Jeden Anteil einzeln reparieren, BEVOR er in die spätere Vereinigung geht: ein
        # ungültiger Einzelanteil kann `unary_union` mit einer GEOS-Ausnahme abbrechen lassen,
        # nicht nur ein ungültiges Ergebnis liefern - dann greift eine Reparatur erst nach dem
        # Vereinigen zu spät.
        teile.setdefault(ags, []).append(_geometrie_reparieren(geometrie, f"VG250-Anteil {ags}"))
        namen.setdefault(ags, name)
        anzahl_anteile += 1
        if anzahl_anteile % bauen.WFS_SEITENGROESSE == 0:
            print(f"  VG250 (vollständig): {anzahl_anteile} Anteile / {len(teile)} Gemeinden geladen")
    print(f"  VG250 (vollständig): {anzahl_anteile} Anteile / {len(teile)} Gemeinden geladen")
    if stats.get("erwartet") is not None and anzahl_anteile != stats["erwartet"]:
        raise bauen.Fehler(
            f"VG250: {anzahl_anteile} Anteile geladen, der Server meldete aber "
            f"{stats['erwartet']} insgesamt - Paginierung vermutlich unvollständig."
        )

    gemeinden: dict[str, tuple[str, object]] = {}
    for ags, geometrien in teile.items():
        try:
            vereinigt = unary_union(geometrien)
        except Exception as exc:  # GEOS kann bei numerisch schwierigen, je einzeln gültigen
            # Eingaben werfen statt ein (ungültiges) Ergebnis zurückzugeben - siehe oben.
            raise bauen.Fehler(f"VG250: Vereinigung der Anteile von {ags} schlug fehl: {exc}") from exc
        # Auch das Vereinigungsergebnis selbst kann noch ungültig sein (Selbstüberschneidung an
        # der Nahtstelle, beobachtet z. B. bei AGS 16064077) oder Fremdteile enthalten
        # (Punkte/Linien an Berührstellen) - deshalb hier zusätzlich zur Reparatur der Anteile.
        gemeinden[ags] = (namen[ags], _geometrie_reparieren(vereinigt, f"Vereinigung {ags}"))
    return gemeinden


def _nur_flaechen(geometrie):
    """Nur die Polygon-/MultiPolygon-Anteile einer (evtl. gemischten) Geometrie, oder None."""
    if geometrie.geom_type in {"Polygon", "MultiPolygon"}:
        return geometrie
    if geometrie.geom_type == "GeometryCollection":
        from shapely.ops import unary_union

        flaechen = [teil for teil in geometrie.geoms if teil.geom_type in {"Polygon", "MultiPolygon"}]
        return unary_union(flaechen) if flaechen else None
    return None


def _geometrie_reparieren(geometrie, beschreibung: str):
    """``shapely.make_valid`` bei Bedarf, dann nur die flächigen Teile behalten.

    Punkte/Linien-Fremdteile (z. B. an einer Berührstelle zweier Anteile) sind für ein
    Flächen-Datenset korrekt zu verwerfen; eine dadurch materiell veränderte (nicht nur formal
    reparierte) Fläche fiele bei der Stichproben-/Rundtrip-Prüfung weiter unten auf.
    """
    from shapely import make_valid

    repariert = geometrie if geometrie.is_valid else make_valid(geometrie)
    flaechen = _nur_flaechen(repariert)
    if flaechen is None:
        raise bauen.Fehler(f"{beschreibung}: enthält nach Reparatur keine Fläche mehr.")
    return flaechen


def kreise_laden() -> dict[str, str]:
    """AGS (fünfstellig) -> Name für alle Kreise aus VG250 laden."""
    kreise: dict[str, str] = {}
    stats: dict = {}
    anzahl = 0
    # gf=4 (Landfläche) wie bei bauen.gemeinden_laden: Kreise sind hier reine Namens- und
    # Schlüssel-Quelle (keine Geometrie), ein Datensatz je AGS reicht und macht Duplikate zu
    # einem echten Fehler statt sie still zu überschreiben.
    for feature in bauen.wfs_seiten("vg250:vg250_krs", cql_filter="gf=4", stats=stats):
        eigenschaften = feature.get("properties") or {}
        ags = str(eigenschaften.get("ags") or "")
        name = str(eigenschaften.get("gen") or "").strip()
        if not re.fullmatch(r"\d{5}", ags) or not name:
            raise bauen.Fehler(f"VG250: ungültiger Kreis {ags!r} ({name!r}).")
        if ags in kreise:
            raise bauen.Fehler(f"VG250 enthält den Kreis-AGS {ags} mehrfach.")
        kreise[ags] = name
        anzahl += 1
    print(f"  VG250: {len(kreise)} Kreise geladen")
    if stats.get("erwartet") is not None and anzahl != stats["erwartet"]:
        raise bauen.Fehler(
            f"VG250: {anzahl} Kreise geladen, der Server meldete aber {stats['erwartet']} "
            "insgesamt - Paginierung vermutlich unvollständig."
        )
    return kreise


def _runde_halbe_von_null_weg(x: float) -> int:
    """Rundung mit fester, sprachübergreifend nachbaubarer Regel bei genau .5.

    Bewusst NICHT Pythons ``round()`` (rundet exakte .5-Werte zur nächsten geraden Zahl,
    "Bankers Rounding") - Kotlins ``Math.round`` rundet bei negativen Werten anders. Round-half-
    away-from-zero ist in beiden Sprachen eindeutig und leicht 1:1 nachzubauen.
    """
    return math.floor(x + 0.5) if x >= 0 else math.ceil(x - 0.5)


def _e6(grad: float) -> int:
    return _runde_halbe_von_null_weg(grad * 1_000_000)


def _ring_zu_e6(koordinaten) -> list[int]:
    flach: list[int] = []
    for lon, lat in koordinaten:
        flach.append(_e6(lon))
        flach.append(_e6(lat))
    return flach


def _polygon_zu_dict(polygon) -> dict:
    return {
        "outer": _ring_zu_e6(polygon.exterior.coords),
        "holes": [_ring_zu_e6(ring.coords) for ring in polygon.interiors],
    }


def _geometrie_zu_polygone(geometrie) -> list[dict]:
    teile = [geometrie] if geometrie.geom_type == "Polygon" else list(geometrie.geoms)
    return [_polygon_zu_dict(teil) for teil in teile]


def _bbox_e6(geometrie) -> list[int]:
    min_lon, min_lat, max_lon, max_lat = geometrie.bounds
    return [_e6(min_lon), _e6(min_lat), _e6(max_lon), _e6(max_lat)]


def land_buendel(
    land: str,
    gemeinden: dict[str, tuple[str, object]],
    kreise: dict[str, str],
    quelldatum: str,
) -> dict:
    """Ein Bundesland-Bündel: alle seine Gemeinden mit AGS, Name, Bbox und Polygon(en)."""
    eintraege = []
    verwendete_kreise: dict[str, str] = {}
    for ags in sorted(ags for ags in gemeinden if ags.startswith(land)):
        name, geometrie = gemeinden[ags]
        kreis_ags = ags[:5]
        if kreis_ags not in kreise:
            raise bauen.Fehler(
                f"Gemeinde {ags}: Kreis {kreis_ags} nicht in den geladenen Kreisen gefunden - "
                "wird sonst still ohne Kreis-Namen ausgeliefert."
            )
        verwendete_kreise[kreis_ags] = kreise[kreis_ags]
        eintraege.append(
            {
                "ags": ags,
                "name": name,
                "kreis": kreis_ags,
                "bbox": _bbox_e6(geometrie),
                "polygons": _geometrie_zu_polygone(geometrie),
            }
        )
    return {
        "schemaVersion": 1,
        "sourceDate": quelldatum,
        "land": land,
        "kreise": verwendete_kreise,
        "gemeinden": eintraege,
    }


def router_bauen(gemeinden: dict[str, tuple[str, object]]) -> dict:
    """Kleiner Land-Router: pro Bundesland ein grob vereinfachter, leicht aufgeblähter Umriss.

    Dient nur der Vorauswahl "welche Landdatei laden" - bewusst ungenau (siehe
    LAND_SIMPLIFY_TOLERANZ_GRAD/LAND_PUFFER_GRAD), damit er klein genug bleibt, um in die APK
    gebündelt zu werden. Die eigentliche, exakte Zuordnung passiert danach über die echten
    Gemeinde-Polygone in der ausgewählten Landdatei.
    """
    from shapely.ops import unary_union

    laender: dict[str, list] = {}
    for ags, (_, geometrie) in gemeinden.items():
        laender.setdefault(ags[:2], []).append(geometrie)

    umrisse = []
    for land in sorted(laender):
        vereinigt = unary_union(laender[land])
        vereinfacht = vereinigt.simplify(LAND_SIMPLIFY_TOLERANZ_GRAD, preserve_topology=True)
        aufgeblaeht = vereinfacht.buffer(LAND_PUFFER_GRAD)
        umrisse.append({"land": land, "polygons": _geometrie_zu_polygone(aufgeblaeht)})
    return {"schemaVersion": 1, "laender": umrisse}


def _gzip_schreiben(pfad: Path, inhalt: dict) -> int:
    """Deterministisch (fester mtime=0, kein eingebetteter Dateiname) und atomar schreiben.

    Ohne festen mtime bettet gzip die aktuelle Bauzeit in die Bytes ein - dasselbe Datenset
    ergäbe dann bei jedem Lauf ein anderes Bündel, was Diffs/Idempotenz-Prüfungen (vgl.
    ``bauen.schreiben``) sinnlos macht. Über eine Zwischendatei + ``replace`` schreiben, damit ein
    Abbruch mitten im Schreiben (z. B. durch die Größenprüfung des Aufrufers) nie eine halb
    geschriebene Zieldatei hinterlässt.
    """
    pfad.parent.mkdir(parents=True, exist_ok=True)
    roh = json.dumps(inhalt, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    puffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=puffer, mtime=0, compresslevel=9) as ausgabe:
        ausgabe.write(roh)
    gepackt = puffer.getvalue()
    zwischenziel = pfad.with_name(pfad.name + ".tmp")
    zwischenziel.write_bytes(gepackt)
    zwischenziel.replace(pfad)
    return len(gepackt)


def ring_enthaelt(ring: list[int], lon_e6: int, lat_e6: int) -> bool:
    """Ray-Casting auf einem flachen E6-Ring (lon,lat,lon,lat,...). Referenzimplementierung, an

    die sich die Kotlin-Seite (Android) 1:1 hält - siehe Loch-Erweiterung von
    WahldatenGeometrie.kt im App-Repo.
    """
    n = len(ring) // 2
    innen = False
    j = n - 1
    for i in range(n):
        xi, yi = ring[2 * i], ring[2 * i + 1]
        xj, yj = ring[2 * j], ring[2 * j + 1]
        if (yi > lat_e6) != (yj > lat_e6) and lon_e6 < (xj - xi) * (lat_e6 - yi) / (yj - yi) + xi:
            innen = not innen
        j = i
    return innen


def punkt_in_polygon(polygon: dict, lon_e6: int, lat_e6: int) -> bool:
    """Drin, wenn im äußeren Ring UND in keinem der Löcher (inneren Ringe)."""
    if not ring_enthaelt(polygon["outer"], lon_e6, lat_e6):
        return False
    return not any(ring_enthaelt(loch, lon_e6, lat_e6) for loch in polygon.get("holes", []))


def punkt_zu_ags(gemeinden: list[dict], lon_e6: int, lat_e6: int) -> str | None:
    """Bbox-Vorfilter, dann Ray-Casting nur auf die Bbox-Treffer - Referenz fürs App-seitige Lookup."""
    for gemeinde in gemeinden:
        min_lon, min_lat, max_lon, max_lat = gemeinde["bbox"]
        if not (min_lon <= lon_e6 <= max_lon and min_lat <= lat_e6 <= max_lat):
            continue
        if any(punkt_in_polygon(polygon, lon_e6, lat_e6) for polygon in gemeinde["polygons"]):
            return gemeinde["ags"]
    return None


def _pruefe_geometrien_gueltig(gemeinden: dict[str, tuple[str, object]]) -> None:
    ungueltig = [ags for ags, (_, geometrie) in gemeinden.items() if not geometrie.is_valid]
    if ungueltig:
        raise bauen.Fehler(f"{len(ungueltig)} ungültige Geometrie(n), z. B. {ungueltig[:5]}")


def _e6_ring_zu_grad(flach: list[int]) -> list[tuple[float, float]]:
    return [(flach[i] / 1_000_000, flach[i + 1] / 1_000_000) for i in range(0, len(flach), 2)]


def _e6_polygon_zu_shapely(polygon: dict):
    from shapely.geometry import Polygon

    return Polygon(
        _e6_ring_zu_grad(polygon["outer"]),
        [_e6_ring_zu_grad(loch) for loch in polygon.get("holes", [])],
    )


def _pruefe_serialisierte_geometrien(buendel: dict) -> None:
    """Validiert die tatsächlich ausgelieferten, E6-gerundeten Polygone - nicht nur die

    Ursprungsgeometrie vor der Rundung (das prüft ``_pruefe_geometrien_gueltig``). Rundung auf
    ~11 cm könnte theoretisch einen Ring entarten lassen (zwei benachbarte Punkte landen auf
    demselben Gitterpunkt) - das wäre sonst erst auf dem Gerät sichtbar geworden.
    """
    for gemeinde in buendel["gemeinden"]:
        for polygon in gemeinde["polygons"]:
            geometrie = _e6_polygon_zu_shapely(polygon)
            if not geometrie.is_valid:
                raise bauen.Fehler(
                    f"Gemeinde {gemeinde['ags']}: E6-gerundetes Polygon ist ungültig - "
                    "vermutlich durch die Rundung entartete Kante(n)."
                )


def _land_am_punkt(router: dict, lon_e6: int, lat_e6: int) -> set[str]:
    """Alle Länder, deren (absichtlich aufgeblähter) Router-Umriss den Punkt enthält."""
    return {
        eintrag["land"]
        for eintrag in router["laender"]
        if any(punkt_in_polygon(polygon, lon_e6, lat_e6) for polygon in eintrag["polygons"])
    }


# AGS -> ein garantiert innenliegender Testpunkt (lon, lat). Deckt bekannte Grenzfälle ab:
# Büsingen ist eine von der Schweiz umschlossene Enklave, Bremen/Bremerhaven sind zwei nicht
# zusammenhängende Gemeinden desselben Bundeslands.
STICHPROBEN: dict[str, tuple[float, float]] = {
    "08335015": (8.6892, 47.6975),  # Büsingen am Hochrhein
    "04011000": (8.8017, 53.0793),  # Bremen
    "04012000": (8.5810, 53.5396),  # Bremerhaven
}


def _stichproben_pruefen(
    gemeinden: dict[str, tuple[str, object]],
    gebaute_laender: dict[str, dict],
    router: dict | None,
) -> None:
    """Handverlesene Grenzfälle plus ein vollständiger Rundtrip über JEDE gebaute Gemeinde.

    Die Handverlese-Punkte oben decken bekannte Sonderfälle ab; der Rundtrip danach prüft für
    jede tatsächlich gebaute Gemeinde, dass ihr repräsentativer Punkt im eigenen Bündel wieder
    zum eigenen AGS auflöst UND (falls ein Router mitgebaut wurde) dass der Router den Punkt
    korrekt dem erwarteten Land zuordnet - eine zu knapp vereinfachte/gepufferte Landgrenze
    würde hier aufsummiert über ~11.000 Gemeinden ziemlich sicher auffallen, drei Handverlese-
    Punkte allein hätten das nicht zuverlässig getan.
    """
    from shapely.geometry import Point

    for ags, (lon, lat) in STICHPROBEN.items():
        if ags not in gemeinden:
            raise bauen.Fehler(f"Stichprobe {ags}: nicht in den geladenen Gemeinden enthalten.")
        _, geometrie = gemeinden[ags]
        if not geometrie.covers(Point(lon, lat)):
            raise bauen.Fehler(f"Stichprobe {ags}: Testpunkt liegt laut Shapely nicht in der Gemeinde.")

    for land, buendel in gebaute_laender.items():
        for gemeinde in buendel["gemeinden"]:
            ags = gemeinde["ags"]
            punkt = gemeinden[ags][1].representative_point()
            lon_e6, lat_e6 = _e6(punkt.x), _e6(punkt.y)
            treffer = punkt_zu_ags(buendel["gemeinden"], lon_e6, lat_e6)
            if treffer != ags:
                raise bauen.Fehler(
                    f"Gemeinde {ags}: repräsentativer Punkt löst im eigenen Bündel zu "
                    f"{treffer!r} statt {ags!r} auf - E6-Rundung/Ray-Casting weicht von Shapely ab."
                )
            if router is not None:
                laender_am_punkt = _land_am_punkt(router, lon_e6, lat_e6)
                if land not in laender_am_punkt:
                    raise bauen.Fehler(
                        f"Gemeinde {ags}: repräsentativer Punkt liegt laut Router in "
                        f"{sorted(laender_am_punkt) or '(keinem Land)'}, nicht im erwarteten "
                        f"Land {land} - Router-Vereinfachung/Puffer reicht nicht aus."
                    )


def _argumente() -> argparse.Namespace:
    zerleger = argparse.ArgumentParser(
        description="Offline-Gebietsdaten (AGS-Lookup + Gemeindegrenze) aus VG250 bauen."
    )
    zerleger.add_argument("--land", metavar="NN", help="nur diese zweistellige Landkennzahl bauen")
    return zerleger.parse_args()


def main() -> int:
    argumente = _argumente()
    try:
        if argumente.land and not re.fullmatch(r"(?:0[1-9]|1[0-6])", argumente.land):
            raise bauen.Fehler("--land erwartet eine zweistellige Kennzahl von 01 bis 16.")

        print("VG250-Gemeinden (vollständig, alle Geofaktoren)")
        gemeinden = gemeinden_vollstaendig_laden()
        if len(gemeinden) != ERWARTETE_GEMEINDEN_GESAMT:
            raise bauen.Fehler(
                f"VG250: {len(gemeinden)} Gemeinden geladen, erwartet wurden "
                f"{ERWARTETE_GEMEINDEN_GESAMT} - VG250-Bestand hat sich vermutlich geändert. "
                "Bei einer echten Änderung ERWARTETE_GEMEINDEN_GESAMT bewusst aktualisieren."
            )
        _pruefe_geometrien_gueltig(gemeinden)

        print("VG250-Kreise")
        kreise = kreise_laden()

        quelldatum = dt.date.today().isoformat()
        laender_auswahl = [argumente.land] if argumente.land else sorted({ags[:2] for ags in gemeinden})

        gebaute_laender: dict[str, dict] = {}
        for land in laender_auswahl:
            buendel = land_buendel(land, gemeinden, kreise, quelldatum)
            _pruefe_serialisierte_geometrien(buendel)
            gebaute_laender[land] = buendel
            groesse = _gzip_schreiben(ZIEL / f"{land}.json.gz", buendel)
            if groesse > MAX_DATEIGROESSE_BYTES:
                raise bauen.Fehler(
                    f"Land {land}: {groesse / 1_048_576:.1f} MiB gzip, über dem "
                    f"{MAX_DATEIGROESSE_BYTES / 1_048_576:.0f}-MiB-Cloudflare-Limit - "
                    "Vereinfachung nötig (siehe Modul-Docstring)."
                )
            print(f"  Land {land}: {len(buendel['gemeinden'])} Gemeinden, {groesse / 1024:.0f} KiB gzip")

        router: dict | None = None
        if not argumente.land:
            router = router_bauen(gemeinden)
            if len(router["laender"]) != 16:
                raise bauen.Fehler(
                    f"Router: {len(router['laender'])} Länder statt der erwarteten 16 gebaut."
                )
            router_pfad = ZIEL / "router.json"
            router_pfad.write_text(
                json.dumps(router, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
            )
            print(f"  Router: {router_pfad.stat().st_size / 1024:.0f} KiB (ungepackt)")

        print("Stichproben")
        _stichproben_pruefen(gemeinden, gebaute_laender, router)
        print("Fertig.")
        return 0
    except bauen.Fehler as exc:
        print(f"\nAbbruch: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
