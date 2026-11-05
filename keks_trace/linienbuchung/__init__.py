"""Buchen an der Backstraße: Kübel einkippen, nachfüllen, Palette fertig.

Ablauf (siehe Konzept „Produktionsplanung und Datenmodell“):
- Jede Station an der Linie arbeitet für einen gewählten Produktionsauftrag (Terminal Station →
  aktueller Auftrag). Former und Verpackung können so 45 Minuten versetzt an verschiedenen
  Aufträgen sein.
- Zuführen (Former, Nachfüllstationen): Kübel, Gebinde, Charge oder Tank scannen → Umlagerung in den
  Lagerort der Linie, mit dem Produktionsauftrag als Vermerk. Der Kübel wird dabei geleert.
- Palette fertig (Paletten-Terminal): Anzahl Kartons → Fertigung. Verbraucht wird aus dem Lagerort
  der Linie, was laut Linienrezept auf diese Menge entfällt, nur Ware DIESES Auftrags, älteste
  zuerst. Ergebnis ist das Tages-Los auf der Palette.
- Auftrag beenden: Rest auf der Linie wird als „Linienrest“ ausgebucht.

Linienrezept: die Stückliste der Fertigware, durch die Stufen aufgelöst, die auf der Linie ohne
eigene Buchung entstehen (Backware, Ware lose). Was übrig bleibt, wird an der Linie zugeführt:
veredelter Teig aus Kübeln, Füllung, Glasur, Schokolade, Streusel, Packmittel.

Die Funktionen liegen nach Bereichen in den Untermodulen. Hier werden alle wieder
angeboten, damit die Aufrufe von außen gleich bleiben (API keks_trace.linienbuchung.<funktion>).
"""

from keks_trace.linienbuchung.auftrag import (
	auftraege,
	info,
	kuebel_vorschlag,
	waehlen,
)
from keks_trace.linienbuchung.basis import (
	AUF_DER_LINIE,
	EPS,
	LINIENREST,
	LinienFehler,
	_fehler,
	_hat,
	_laufender,
	_linie,
	_menge_text,
	_station,
	hinweise,
)
from keks_trace.linienbuchung.fertig import (
	beenden,
	packstation,
	palette_fertig,
)
from keks_trace.linienbuchung.lose import (
	LOSE_ZIELE,
	im_linienlager,
	lose_artikel,
	lose_einheit,
	lose_fertig,
)
from keks_trace.linienbuchung.retour import (
	RETOUR_STUFEN,
	_herkunft,
	retour_liste,
	rueckgabe,
)
from keks_trace.linienbuchung.rework import (
	_pruefe_rework_anteil,
	_rework_ziel,
	laufende_auftraege,
	rework_sorten,
	rework_von_linie,
)
from keks_trace.linienbuchung.rezept import (
	_verbrauch,
	bestand,
	linienrezept,
	rework_ersatz,
)
from keks_trace.linienbuchung.uebersicht import (
	STATUS_REIHENFOLGE,
	tagesuebersicht,
)
from keks_trace.linienbuchung.zufuhr import (
	zufuehren,
)
