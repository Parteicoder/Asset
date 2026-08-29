#!/usr/bin/env python3
"""Coverage-Selbsttest ohne Netz gegen kleine lokale Fixtures."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bauen  # noqa: E402
import gebiete_bauen  # noqa: E402


fehler = 0


def pruefe(bedingung, text):
    global fehler
    if bedingung:
        print(f"  ok    {text}")
    else:
        print(f"  FEHLT {text}")
        fehler += 1


print("EPSG:3035 und Zensus-Zell-ID")
easting, northing = bauen.epsg3035(12.632, 51.464)
kennung = bauen.zensus_zell_id(easting, northing)
pruefe(kennung == "100mN31536E45038", f"stabiler Eilenburg-Regressionswert ({kennung})")


print("OSM-Straßenfilter")
pruefe(not bauen.ist_relevante_strasse({"highway": "motorway"}), "motorway ausgeschlossen")
pruefe(
    not bauen.ist_relevante_strasse({"highway": "residential", "foot": "no"}),
    "residential mit foot=no ausgeschlossen",
)
pruefe(bauen.ist_relevante_strasse({"highway": "residential"}), "residential eingeschlossen")
pruefe(
    not bauen.ist_relevante_strasse({"highway": "residential", "access": "private"}),
    "access=private ausgeschlossen",
)


print("Zensus-Spaltenerkennung")
fixtures = Path(__file__).resolve().parent / "fixtures"
bevoelkerung = bauen.zensus_laden(fixtures / "zensus.csv")
pruefe(bevoelkerung["100mN31536E45038"] == 7, "Einwohner-Spalte gelesen")
try:
    bauen.zensus_laden(fixtures / "zensus-ohne-einwohner.csv")
    spaltenfehler = False
except bauen.Fehler:
    spaltenfehler = True
pruefe(spaltenfehler, "fehlende Einwohner-Spalte schlägt kontrolliert fehl")
pruefe(
    bauen._zensus_spalten(["Gitter_ID_100m", "x_mp_100m", "y_mp_100m", "EWZ"])[2] == "EWZ",
    "gebräuchliche EWZ-Spalte erkannt",
)


print("H3-Fallback für Gemeinden ohne Zellmittelpunkt")
try:
    import h3
    from shapely.geometry import Point as _Point

    # Ein winziges Polygon (deutlich kleiner als eine H3-Res-8-Zelle, ~460 m Kantenlänge) kann
    # ganz ohne Zellmittelpunkt bleiben - genau der Fall, der reale Gemeinden wie "Insel Lütje
    # Hörn" beim echten VG250-Bestand betrifft.
    winzig = _Point(12.632, 51.464).buffer(0.0001)
    zellen_winzig = bauen._h3_zellen(winzig)
    pruefe(len(zellen_winzig) == 1, f"Fallback liefert genau eine Zelle ({len(zellen_winzig)})")
except ImportError as exc:
    print(f"  FEHLT H3-Fallback-Test nicht ausführbar: {exc}")
    fehler += 1


print("populationDensity=null ohne Zensus-Treffer, kein STATISTIK_VERALTET")
try:
    import h3
    from shapely.geometry import LineString, Polygon

    # Zelle weit entfernt von der Fixture-Zensuszelle (Fixture liegt bei Eilenburg) - garantiert
    # keine Zensus-Zuordnung.
    unbewohnt = h3.latlng_to_cell(53.5, 9.9, bauen.H3_AUFLOESUNG)
    hexagon_unbewohnt = bauen._hexagon(unbewohnt)
    einwohner, zensuszellen = bauen._zensus_im_hexagon(hexagon_unbewohnt, bevoelkerung)
    pruefe(zensuszellen == 0, "keine Zensuszelle unter der Testzelle gefunden")
    dichte = (
        round(einwohner / h3.cell_area(unbewohnt, unit="km^2"), 1) if zensuszellen else None
    )
    pruefe(dichte is None, f"populationDensity wird null statt 0.0 ({dichte})")
except ImportError as exc:
    print(f"  FEHLT Null-Dichte-Test nicht ausführbar: {exc}")
    fehler += 1


print("Synthetisches Ende-zu-Ende-Bündel")
try:
    import h3
    from shapely.geometry import LineString, Polygon

    mitte = (51.464, 12.632)
    zelle = h3.latlng_to_cell(*mitte, bauen.H3_AUFLOESUNG)
    rand = h3.cell_to_boundary(zelle)
    gemeinde = Polygon([(lon, lat) for lat, lon in rand]).buffer(0.002)
    strassen = [
        LineString([(12.62, 51.464), (12.644, 51.464)]),
        LineString([(12.632, 51.455), (12.632, 51.473)]),
    ]
    # Das Raster wird aus dem projizierten Hexagon erzeugt; so liegt die Fixture garantiert in
    # einer tatsächlich geprüften Rasterzelle, unabhängig von H3-Randdetails.
    with tempfile.TemporaryDirectory(prefix="coverage-test-") as ordner:
        zellen, geschrieben = bauen.buendel_bauen(
            {"14730110": ("Eilenburg", gemeinde)},
            strassen,
            bevoelkerung,
            Path(ordner),
        )
        datei = Path(ordner) / "14730110.json"
        inhalt = json.loads(datei.read_text(encoding="utf-8"))
        unveraendert = not bauen.schreiben(datei, inhalt)
    pruefe(zellen >= 1 and geschrieben == 1, f"mindestens eine H3-Zelle erzeugt ({zellen})")
    pruefe(inhalt["gemeindeAgs"] == "14730110", "Gemeinde-AGS geschrieben")
    pruefe(inhalt["formulaVersion"] == bauen.FORMELVERSION, "Formelversion geschrieben")
    pruefe(
        set(inhalt["zellen"][0])
        == {"h3CellId", "boundary", "relevantRoadKm", "populationDensity", "dataQualityFlags"},
        "exakte Zellenfelder geschrieben",
    )
    rand = inhalt["zellen"][0]["boundary"]
    pruefe(len(rand) >= 6, f"Hexagon-Rand hat mindestens 6 Punkte ({len(rand)})")
    pruefe(rand[0] == rand[-1], "Hexagon-Rand ist geschlossen (erster Punkt = letzter Punkt)")
    pruefe(any(z["relevantRoadKm"] > 0 for z in inhalt["zellen"]), "Straßenlänge berechnet")
    pruefe(
        any((z["populationDensity"] or 0) > 0 for z in inhalt["zellen"]),
        "Bevölkerungsdichte berechnet",
    )
    pruefe(
        all("STATISTIK_VERALTET" not in z["dataQualityFlags"] for z in inhalt["zellen"]),
        "STATISTIK_VERALTET wird nicht mehr aus fehlender Zensuszuordnung abgeleitet",
    )
    pruefe(unveraendert, "identisches Bündel nicht neu geschrieben")
except ImportError as exc:
    print(f"  FEHLT Ende-zu-Ende-Test nicht ausführbar: {exc}")
    fehler += 1


print("Gebiete: E6-Kodierung")
pruefe(gebiete_bauen._e6(12.632) == 12_632_000, "positive Kommazahl korrekt skaliert")
pruefe(gebiete_bauen._e6(-8.6892) == -8_689_200, "negative Kommazahl korrekt skaliert")
pruefe(gebiete_bauen._e6(0.00000049) == 0, "unter der halben Einheit abgerundet")
pruefe(
    gebiete_bauen._runde_halbe_von_null_weg(2.5) == 3, "exakte .5 (positiv) rundet von null weg auf"
)
pruefe(
    gebiete_bauen._runde_halbe_von_null_weg(-2.5) == -3,
    "exakte .5 (negativ) rundet von null weg ab - NICHT Pythons round() (-2)",
)
pruefe(gebiete_bauen._runde_halbe_von_null_weg(0.5) == 1, "0.5 rundet auf 1")
pruefe(gebiete_bauen._runde_halbe_von_null_weg(-0.5) == -1, "-0.5 rundet auf -1")


print("Gebiete: Ring-Enthält-Prüfung mit Loch")


def _punkt_e6(lon: float, lat: float) -> tuple[int, int]:
    return gebiete_bauen._e6(lon), gebiete_bauen._e6(lat)


# Quadrat 0..10 Grad (E6), Loch 4..6 Grad mittig - Punkt im Loch zählt nicht als "drin".
AUSSEN = gebiete_bauen._ring_zu_e6([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])
LOCH = gebiete_bauen._ring_zu_e6([(4, 4), (6, 4), (6, 6), (4, 6), (4, 4)])
POLYGON_MIT_LOCH = {"outer": AUSSEN, "holes": [LOCH]}
pruefe(
    not gebiete_bauen.punkt_in_polygon(POLYGON_MIT_LOCH, *_punkt_e6(5, 5)),
    "Punkt im Loch liegt draußen",
)
pruefe(
    gebiete_bauen.punkt_in_polygon(POLYGON_MIT_LOCH, *_punkt_e6(1, 1)),
    "Punkt im Außenring, außerhalb des Lochs, liegt drin",
)
pruefe(
    not gebiete_bauen.punkt_in_polygon(POLYGON_MIT_LOCH, *_punkt_e6(20, 20)),
    "Punkt außerhalb des Außenrings liegt draußen",
)


print("Gebiete: Bbox-Vorfilter + AGS-Lookup")
GEMEINDEN_FIXTURE = [
    {
        "ags": "00000001",
        "bbox": [0, 0, 10_000_000, 10_000_000],
        "polygons": [POLYGON_MIT_LOCH],
    }
]
pruefe(
    gebiete_bauen.punkt_zu_ags(GEMEINDEN_FIXTURE, *_punkt_e6(1, 1)) == "00000001",
    "Punkt in der Gemeinde löst zum AGS auf",
)
pruefe(
    gebiete_bauen.punkt_zu_ags(GEMEINDEN_FIXTURE, *_punkt_e6(5, 5)) is None,
    "Punkt im Loch löst zu keinem AGS auf",
)
pruefe(
    gebiete_bauen.punkt_zu_ags(GEMEINDEN_FIXTURE, *_punkt_e6(50, 50)) is None,
    "Punkt außerhalb jeder Bbox löst zu keinem AGS auf",
)


print()
if fehler:
    print(f"{fehler} Prüfung(en) fehlgeschlagen")
    raise SystemExit(1)
print("Alle Prüfungen bestanden")
