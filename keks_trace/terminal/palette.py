"""Paletten und Versandkartons am Terminal."""

import frappe
from frappe import _

from keks_trace import palette as paletten
from keks_trace.anfrage import einmalig
from keks_trace.buchung.basis import _fehler
from keks_trace.buchung.scan import aufloesen
from keks_trace.terminal.basis import _darf, _meldungen, _station


def _palette(code):
	nve = paletten.finde(code)
	if not nve:
		_fehler(_("{0} ist keine Palette.").format(code))
	return nve


@frappe.whitelist()
@einmalig
def palette_neu(station: str, typ: str = "Lagerpalette", kunde: str | None = None) -> dict:
	s = _station(station)
	if not (s.f_paletten or s.f_herstellen):
		_darf(s, "paletten")
	nve = paletten.anlegen(typ, s.name, kunde)
	return paletten.info(nve)


@frappe.whitelist()
@einmalig
def karton_auf_palette(station: str, karton: str, palette: str) -> dict:
	"""Versandkarton (eigene NVE) auf eine Palette mit NVE stellen."""
	s = _station(station)
	if not (s.f_paletten or s.f_lieferung or s.f_herstellen or s.f_palette_fertig):
		_darf(s, "paletten")
	return paletten.karton_auf_palette(_palette(karton), _palette(palette), s.name)


@frappe.whitelist()
@einmalig
def karton_abnehmen(station: str, karton: str) -> dict:
	"""Versandkarton von seiner Palette nehmen; er bleibt im Lager."""
	s = _station(station)
	nve = _palette(karton)
	palette = frappe.db.get_value("Palette", nve, "auf_palette")
	paletten.karton_abnehmen(nve, s.name)
	return paletten.info(palette) if palette else paletten.info(nve)


@frappe.whitelist()
def palette_info(code: str) -> dict:
	return paletten.info(_palette(code))


@frappe.whitelist()
@einmalig
def palette_beladen(station: str, palette: str, code: str, anzahl: float, einheit: str) -> dict:
	"""Lose Kartons eines Loses auf die Palette (Los-Etikett scannen)."""
	s = _station(station)
	_darf(s, "paletten")
	r = aufloesen(code)
	if r["typ"] != "charge":
		_fehler(_("Bitte das Los scannen."))
	return paletten.beladen(_palette(palette), r["charge"], anzahl, einheit, s.name)


@frappe.whitelist()
@einmalig
def palette_umpacken(station: str, von: str, nach: str, charge: str, anzahl: float, einheit: str) -> dict:
	s = _station(station)
	_darf(s, "paletten")
	erg = paletten.umpacken(_palette(von), _palette(nach), charge, anzahl, einheit, s.name)
	erg["hinweise"] = _meldungen()  # z. B. „Etikett der Quellpalette neu drucken“
	return erg


@frappe.whitelist()
def palette_schliessen(station: str, palette: str) -> dict:
	_darf(_station(station), "paletten")
	return paletten.schliessen(_palette(palette))


@frappe.whitelist()
def palette_oeffnen(station: str, palette: str) -> dict:
	_darf(_station(station), "paletten")
	return paletten.oeffnen(_palette(palette))


@frappe.whitelist()
def freie_kisten(station: str) -> list[dict]:
	_station(station)
	return frappe.get_all(
		"Produkttraeger", {"typ": "Kiste lose Ware", "status": "Frei"}, ["code"], order_by="code", limit=200
	)


@frappe.whitelist()
def offene_paletten(station: str) -> list[dict]:
	"""Paletten, die noch nicht eingewickelt sind (Status Offen, mit Inhalt): zum Abschließen am Paletten-Terminal."""
	_station(station)
	ergebnis = []
	for p in frappe.get_all(
		"Palette", {"status": "Offen"}, ["name", "typ", "kunde"], order_by="creation desc", limit=100
	):
		i = paletten.info(p.name)
		if i.get("positionen"):
			ergebnis.append({"nve": p.name, "typ": p.typ, "kunde": p.kunde, "inhalt": i.get("kartons") or "",
			                 "lose": ", ".join(sorted({x["charge"] for x in i["positionen"]}))})  # fmt: skip
	return ergebnis


@frappe.whitelist()
@einmalig
def palette_versandbereit(station: str, palette: str) -> dict:
	"""Palette eingewickelt: abschließen, NVE-Etikett drucken, versandbereit im Lager."""
	_station(station)
	nve = paletten.finde(palette)
	if not nve:
		_fehler(_("{0} ist keine Palette.").format(palette))
	paletten.schliessen(nve)
	return paletten.info(nve)
