"""Paletten mit NVE (SSCC): Kartons und Beutel aus Fertigware-Losen.

Die Palette ist ein logischer Träger im Fertiglager. Ihr Inhalt ergibt sich ausschließlich aus
den unveränderbaren Paletten-Bewegungen (Zugang/Abgang je Los und Einheit). Lagerbestand bleibt
in ERPNext je Charge geführt; diese Datei sorgt dafür, dass beides zusammenpasst:

- Auf Paletten kann nie mehr stehen, als vom Los am Lager ist.
- Ein Lieferschein nimmt Ware entweder von einer Palette (Feld „Palette“ an der Position)
  oder aus losen Kartons, die auf keiner Palette stehen.
- Eine Fertigung, deren Los schon auf einer Palette steht, kann nicht storniert werden.

Die Funktionen liegen nach Bereichen in den Untermodulen. Hier werden alle wieder
angeboten, damit die Aufrufe von außen gleich bleiben (API keks_trace.palette.<funktion>).
"""

from keks_trace.palette.basis import (
	AKTIV,
	EPS,
	TEST_BASISNUMMER,
	VERSANDKARTON,
	PalettenFehler,
	_fehler,
)
from keks_trace.palette.belege import (
	VERBRAUCH,
	_charge_aus_bundle,
	_gezaehlt,
	_position_charge,
	abgleich,
	lieferung_on_cancel,
	lieferung_on_submit,
	pruefe_lieferung,
	se_before_cancel,
	se_on_cancel,
	se_on_submit,
)
from keks_trace.palette.bestand import (
	_offen,
	_status_pruefen,
	_summe_text,
	_zusammen,
	auf_paletten,
	etikett_aktuell,
	etikett_gedruckt,
	fuellung,
	info,
	inhalt,
	kartons,
	lagerbestand,
	lose,
	stand,
)
from keks_trace.palette.bewegung import (
	_anzahl_text,
	_bewegung,
	_etikett_hinweis,
	_hinweis_fuellung,
	_position,
	anlegen,
	beladen,
	korrektur,
	oeffnen,
	schliessen,
	umpacken,
)
from keks_trace.palette.einheit import (
	ANZEIGE,
	NUR_ANZEIGE,
	STUECK_EINHEITEN,
	_n,
	einheiten,
	faktor,
	zerlegen,
)
from keks_trace.palette.nve import (
	finde,
	nve_aus_scan,
	nve_neu,
	pruefziffer,
	standard_kreis,
)
from keks_trace.palette.rueckverfolgung import (
	_yymmdd,
	etikett,
	paletten_fuer,
)
from keks_trace.palette.versandkarton import (
	_zuordnung,
	karton_abnehmen,
	karton_auf_palette,
)
