"""Schnittstelle für die Terminals (Backstube, Verpackung, Lager, Versand).

Jedes Terminal ist als seine Station angemeldet. Gescannt wird mit dem Handscanner als
Tastatureingabe: ein Code ist ein Behälter, ein Silo/Tank oder eine Charge.

Die Prüfungen am Terminal (pruefe_zeile) geben sofort grün oder rot. Beim Buchen laufen
zusätzlich alle Regeln aus keks_trace.pruefungen (Rework-Anteil, FIFO, Vollständigkeit, ...).
Die Daten vom Terminal werden beim Buchen serverseitig neu aufgelöst, nie blind übernommen.

Die Funktionen liegen nach Bereichen in den Untermodulen. Hier werden alle wieder
angeboten, damit die Aufrufe von außen gleich bleiben (API keks_trace.terminal.<funktion>).
"""

from keks_trace.terminal.arbeitsliste import (
	_fertig_fuer,
	_hauptzutat,
	_vorrat_je_auftrag,
	aufgaben,
	auftraege,
	verpacken_ziele,
	zum_verpacken,
)
from keks_trace.terminal.basis import (
	EPS,
	FUNKTIONSNAMEN,
	VORRAT,
	TerminalFehler,
	_darf,
	_fehler,
	_liste,
	_meldungen,
	_mit_hinweis,
	_neue_charge,
	_se_zeile,
	_silo_filter,
	_silo_je_artikel,
	_station,
	_vorraete,
)
from keks_trace.terminal.behaelter import (
	behaelter_reinigung,
	silo_leer,
)
from keks_trace.terminal.bestand import (
	_lager_chargen,
	_lager_chargen_alle,
	_offene_auftraege,
	_pruefe_charge,
	_quellen,
	_reserviert,
	_verfuegbar,
	_verkaufslager,
	charge_lager,
)
from keks_trace.terminal.buchen import (
	_ziel_behaelter,
	_ziel_lager,
	anbrechen,
	herstellen,
	rework_erfassen,
	vorschau,
)
from keks_trace.terminal.eingang import (
	BESTELLUNG_OFFEN,
	GEBINDEARTEN,
	_bestellungen,
	_lieferanten,
	_neues_gebinde,
	_pruefe_bestellung,
	_pruefe_lieferantencharge,
	wareneingang,
	wareneingang_artikel,
	wareneingang_scan,
)
from keks_trace.terminal.einwaage import (
	REZEPT_STUFEN,
	_fuer_auftrag,
	_gebinde_einheiten,
	_kuebel_fuer,
	_lagerort,
	_pruefe_rezept,
	_rezept_modus,
	_toleranz,
	rezept,
	rezepte,
)
from keks_trace.terminal.linie import (
	_linien_station,
	freie_rework_behaelter,
	linie_auftraege,
	linie_beenden,
	linie_info,
	linie_lose,
	linie_palette,
	linie_retour_liste,
	linie_rueckgabe,
	linie_waehlen,
	linie_zufuehren,
	packstation,
	rework_linie,
	rework_linie_auftraege,
	tagesuebersicht,
)
from keks_trace.terminal.palette import (
	_palette,
	freie_kisten,
	karton_abnehmen,
	karton_auf_palette,
	offene_paletten,
	palette_beladen,
	palette_info,
	palette_neu,
	palette_oeffnen,
	palette_schliessen,
	palette_umpacken,
	palette_versandbereit,
)
from keks_trace.terminal.scan import (
	_artikel_zur_gtin,
	_charge_aus_los_oder_buchung,
	_charge_name,
	_charge_zum_eigenen_los,
	akte,
	aufloesen,
	herkunft,
	info,
)
from keks_trace.terminal.stammdaten import (
	einheiten,
	etikett_drucken,
	etikett_vormerken,
	fertigware_im_lager,
	kopfdaten,
	kunden,
	lager_chargen,
	pruefung_erfassen,
	pruefungen_faellig,
	registrierungen,
	rework_artikel,
	silos,
	start,
	stationen,
	vorraete,
)
from keks_trace.terminal.versand import (
	KARTON_TARA_KG,
	_kundenadresse,
	_lieferposition,
	_lieferpositionen,
	_lieferzeile,
	_lose_im_karton,
	_paket_lieferung_kartons,
	_versandkartons_im_lieferschein,
	lieferung,
	paket_karton,
	paket_lieferung,
	paket_vorschlag,
	pruefe_lieferzeile,
	sendungsnummer,
	umlager_ziele,
	umlagern,
)
from keks_trace.terminal.zutaten import (
	FEFO_STUFEN,
	_fefo_aeltere,
	_fefo_modus,
	_fefo_text,
	_pruefe_fefo,
	_pruefe_rework_fuer,
	_zeile,
	auswahl,
	fefo_pruefen,
	pruefe_zeile,
	vorschlag,
)
