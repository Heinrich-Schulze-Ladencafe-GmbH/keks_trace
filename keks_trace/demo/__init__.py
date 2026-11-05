"""Demo: drei Produktionstage nach dem echten Ablauf auf einer ERPNext-Instanz.

Aufruf auf dem Server (Firma muss über den Einrichtungsassistenten angelegt sein):

        bench --site <site> execute keks_trace.demo.run

Ablauf: Grundteig (Silo/Säcke) -> Veredelung (weitere Zutaten, Rework) -> Backen
-> Füllen/Glasieren/Schokolieren (gekaufte Schokolade, selbst gemachte Nougatfüllung)
-> lose Ware in Kisten im Lager -> Verpacken -> Lieferung.

Legt Demo-Stammdaten an (Artikel mit Präfix KT-), bucht drei Tage mit Rework und Behältern,
verpackt, liefert an einen Demo-Kunden und gibt die Rückverfolgung aus.
Jeder Lauf erzeugt neue Chargen und Behälter (eindeutiges Kürzel), Stammdaten werden wiederverwendet.

Weitere Demos und Testhilfen in diesem Paket (nichts davon läuft im Echtbetrieb, außer demo.tag.morgens,
das auf Nicht-Demosystemen nichts tut): linie (Backstraße mit Produktionsaufträgen), pilot (Honig Lebkuchen),
herzen (Herzenboden), einkauf (Kontrakt), erechnung (E-Rechnung, DATEV), tag (Demo-Tag mit Drehbuch /demo),
lasttest (Massendaten und Messung). Die Tests nutzen stammdaten() und die Helfer hier.

Die Funktionen liegen nach Bereichen in den Untermodulen. Hier werden alle wieder
angeboten, damit die Aufrufe von außen gleich bleiben (API keks_trace.demo.<funktion>).
"""

from keks_trace.demo.grunddaten import (
	_blatt,
	_pruefplaene,
	metalldetektor_ok,
	pruefungen_altern,
	silos_anlegen,
	stammdaten,
	standardlager,
)
from keks_trace.demo.helfer import (
	_lager,
	_ort,
	_stufe,
	_zeile,
	buchen,
	liefern,
	neue_charge,
	neuer_traeger,
)
from keks_trace.demo.kette import (
	_ausgabe,
	drei_tage_kette,
	lagerware,
	run,
)
from keks_trace.demo.konstanten import (
	ALLERGENGRUPPEN,
	ARTIKEL,
	AUF_PAPIER,
	BIO_LIEFERANT,
	FREIGABE_PFLICHT,
	KENNZEICHNUNG,
	PRUEFPLAENE,
	REWORK_REGELN,
	REZEPTE,
	ROHSTOFF_PREIS,
	SILOS,
	UMLAGER_LAGER,
	VERPACKUNG,
)
