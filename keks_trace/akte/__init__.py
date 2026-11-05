"""Akte: der Lebenslauf einer Palette oder eines Behälters, lesbar für das Terminal.

Quelle sind nur vorhandene Protokolle, nichts wird neu berechnet oder gespeichert:
- Palette: Paletten Bewegung (wer, wann, wo, welches Los) und Etikettendruck
- Behälter/Gebinde: Traeger Belegung (welche Charge von wann bis wann) und Etikettendruck

Dazu „Wo ist dieses Los?“ (fundstellen): alle Paletten und Behälter, auf bzw. in denen ein Los gerade liegt, je mit
kurzem Lebenslauf. Damit findet man eine Palette ohne Etikett wieder: Inhalt, Ort, Zeit und Person grenzen ein.

Die Funktionen liegen nach Bereichen in den Untermodulen. Hier werden alle wieder
angeboten, damit die Aufrufe von außen gleich bleiben (API keks_trace.akte.<funktion>).
"""

from keks_trace.akte.basis import (
	EPS,
	MAX_EREIGNISSE,
	MAX_FUNDSTELLEN,
	ZUSAMMEN_MINUTEN,
	_bis,
	_datum,
	_druck_ereignisse,
	_los,
	_person,
	_sortiert,
	_uhr,
	_zeit,
)
from keks_trace.akte.baum import (
	MAX_HERKUNFT_TIEFE,
	MAX_KNOTEN,
	MAX_PRUEFUNGEN,
	ROHSTOFF_STUFEN,
	_buchung,
	_freigabe,
	_knoten,
	_pruefungen,
	_wareneingang,
	_zutaten,
	herkunft,
)
from keks_trace.akte.lebenslauf import (
	_bewegung_text,
	_bewegungen,
	_etikett_text,
	_karton_zeilen,
	_zuordnungen,
	_zusammenfassen,
	akte,
	behaelter,
	palette,
)
from keks_trace.akte.suche import (
	_kurz,
	fundstellen,
)
