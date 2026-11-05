"""Linie: Produktionsaufträge, Zuführen, Packstation, Palette fertig, Rework an der Linie."""

import frappe
from frappe import _
from frappe.utils import cint

from keks_trace.anfrage import einmalig
from keks_trace.terminal.basis import _darf, _fehler, _station


def _linien_station(station):
	s = _station(station)
	if not (s.f_linie or s.f_packstation or s.f_palette_fertig):
		_fehler(_("Die Station {0} arbeitet nicht an einer Linie.").format(s.name))
	return s


@frappe.whitelist()
def linie_retour_liste(station: str) -> list[dict]:
	"""Retour: was vom laufenden Auftrag unbenutzt zurück ins Lager kann."""
	from keks_trace import linienbuchung

	return linienbuchung.retour_liste(_linien_station(station).name)


@frappe.whitelist()
@einmalig
def linie_rueckgabe(station: str, charge: str, menge: float) -> dict:
	from keks_trace import linienbuchung

	return linienbuchung.rueckgabe(_linien_station(station).name, charge, menge)


@frappe.whitelist()
def tagesuebersicht(station: str, datum: str | None = None) -> dict:
	"""Aufträge des Tages je Linie (nur lesen, jede Station)."""
	from keks_trace import linienbuchung

	_station(station)
	frappe.has_permission("Produktionsauftrag", "read", throw=True)
	return linienbuchung.tagesuebersicht(datum)


@frappe.whitelist()
def linie_auftraege(station: str) -> list[dict]:
	from keks_trace import linienbuchung

	return linienbuchung.auftraege(_linien_station(station).name)


@frappe.whitelist()
def linie_waehlen(station: str, auftrag: str) -> dict:
	from keks_trace import linienbuchung

	return linienbuchung.waehlen(_linien_station(station).name, auftrag)


@frappe.whitelist()
def linie_info(station: str) -> dict:
	from keks_trace import linienbuchung

	s = _linien_station(station)
	name = frappe.db.get_value("Terminal Station", s.name, "aktueller_auftrag")
	return linienbuchung.info(name) if name else {}


@frappe.whitelist()
@einmalig
def linie_zufuehren(
	station: str, code: str, menge: float | None = None, fefo_grund: str | None = None
) -> dict:
	from keks_trace import linienbuchung

	s = _station(station)
	_darf(s, "linie")
	return linienbuchung.zufuehren(s.name, code, menge, fefo_grund)


@frappe.whitelist()
@einmalig
def linie_palette(station: str, anzahl: float, einheit: str, palette: str | None = None) -> dict:
	from keks_trace import linienbuchung

	s = _station(station)
	_darf(s, "palette_fertig")
	return linienbuchung.palette_fertig(s.name, anzahl, einheit, palette)


@frappe.whitelist()
@einmalig
def linie_lose(
	station: str,
	anzahl: float,
	einheit: str | None = None,
	ziel: str = "lager",
	palette: str | None = None,
	kiste: str | None = None,
) -> dict:
	"""Lose Ware vom laufenden Auftrag: Kartons ins Lager (F5, optional auf Palette) oder ins Linienlager (F6)."""
	from keks_trace import linienbuchung

	s = _station(station)
	_darf(s, "palette_fertig")
	return linienbuchung.lose_fertig(s.name, anzahl, einheit, ziel, palette, kiste)


@frappe.whitelist()
def rework_linie_auftraege(station: str) -> list[dict]:
	"""Backstube: laufende Linienaufträge, je mit den passenden Rework-Sorten (Filter) und freien Behältern."""
	from keks_trace import linienbuchung

	s = _station(station)
	_darf(s, "rework")
	return [
		{**a, "sorten": linienbuchung.rework_sorten(a["auftrag"])} for a in linienbuchung.laufende_auftraege()
	]


@frappe.whitelist()
def freie_rework_behaelter(station: str) -> list[dict]:
	_station(station)
	return frappe.get_all(
		"Produkttraeger", {"typ": "Rework-Behälter", "status": "Frei"}, ["code"], order_by="code", limit=100
	)


@frappe.whitelist()
@einmalig
def rework_linie(station: str, auftrag: str, rework_artikel: str, kg: float, behaelter: str) -> dict:
	"""Backstube bucht einen gewogenen Rework-Behälter von der Linie (Flussschema F18)."""
	from keks_trace import linienbuchung

	s = _station(station)
	_darf(s, "rework")
	return linienbuchung.rework_von_linie(s.name, auftrag, rework_artikel, kg, behaelter)


@frappe.whitelist()
@einmalig
def linie_beenden(station: str, auftrag: str | None = None, abbrechen: int = 0) -> dict:
	from keks_trace import linienbuchung

	s = _station(station)
	_darf(s, "palette_fertig")
	return linienbuchung.beenden(s.name, auftrag, bool(cint(abbrechen)))


@frappe.whitelist()
def packstation(station: str) -> dict:
	from keks_trace import linienbuchung

	s = _station(station)
	if not s.f_palette_fertig:  # Verpackungs-PC zeigt den Verpackungsauftrag auch
		_darf(s, "packstation")
	return linienbuchung.packstation(s.name)
