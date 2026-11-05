"""Prüfen einer gescannten Zutat: Sperre, Verfall, Rework-Regel, FEFO."""

import frappe
from frappe import _
from frappe.utils import flt

from keks_trace import palette as paletten
from keks_trace.buchung.basis import EPS
from keks_trace.buchung.bestand import _quellen
from keks_trace.buchung.scan import aufloesen
from keks_trace.buchung.zutat import _fefo_aeltere, _fefo_modus, _zeile
from keks_trace.terminal.basis import _station
from keks_trace.terminal.einwaage import rezept


@frappe.whitelist()
def auswahl(station: str, artikel: str) -> list[dict]:
	"""Zum Selbst-Auswählen ohne Scanner: Behälter und Chargen eines Artikels mit Menge und MHD."""
	_station(station)
	return _quellen(artikel)


@frappe.whitelist()
def vorschlag(
	station: str, ziel: str, menge: float, bevorzugt: str | None = None, kundenauftrag: str | None = None
) -> dict:
	"""Zutaten für die Sollmenge vorschlagen statt scannen: Vorrat am Tisch, Behälter (Silo/Tank) und
	sonst die älteste Ware zuerst, über mehrere Chargen bzw. Kisten verteilt. Jede Zeile ist geprüft."""
	s = _station(station)
	r = rezept(ziel, menge, s.name)
	erlaubt = {z["artikel"] for z in r["zutaten"]}
	zeilen, hinweise = [], []
	vorne = None
	if bevorzugt:  # z. B. die Kiste, die der Packer aus der Liste gewählt hat
		b = aufloesen(bevorzugt)
		vorne = (b.get("artikel"), {"code": b["code"], "menge": flt(b.get("inhalt") or 0)})
	for z in r["zutaten"]:
		quellen = (
			[{"code": z["silo"], "menge": z["menge"]}] if z["silo"] else _quellen(z["artikel"], kundenauftrag)
		)
		if vorne and vorne[0] == z["artikel"]:
			quellen = [vorne[1]] + [q for q in quellen if q["code"] != vorne[1]["code"]]
		offen = z["menge"]
		for q in quellen:
			if offen <= EPS:
				break
			m = min(offen, q["menge"])
			try:
				zeilen.append(_zeile(q["code"], m, ziel, erlaubt))
				offen -= m
			except frappe.ValidationError as e:
				hinweise.append(f"{z['name']}: {frappe.utils.strip_html(str(e))}")
				if z["silo"]:
					break
		if offen > EPS:
			hinweise.append(
				_("{0}: es fehlen {1}.").format(z["name"], paletten._n(flt(offen, 3), z["einheit"]))
			)
	frappe.local.message_log = []
	return {"zeilen": zeilen, "hinweise": hinweise}


@frappe.whitelist()
def pruefe_zeile(station: str, ziel: str, code: str, menge: float) -> dict:
	"""Sofortprüfung einer gescannten Zutat für ein Rezept (grün/rot am Terminal)."""
	_station(station)
	erlaubt = {z["artikel"] for z in rezept(ziel)["zutaten"]}
	return _zeile(code, menge, ziel, erlaubt)


@frappe.whitelist()
def fefo_pruefen(station: str, code: str) -> dict:
	"""Vor dem Zuführen: liegt vom gescannten Rohstoff/Packmittel eine Charge mit früherem MHD im Lager?

	Nur lesen. Gibt die älteren Chargen und ob ein Grund Pflicht ist (Einstellung) zurück.
	"""
	_station(station)
	modus = _fefo_modus()
	r = aufloesen(code)
	if modus == "Aus" or r["typ"] in ("silo", "palette") or not r.get("charge"):
		return {"aeltere": [], "pflicht": False}
	return {
		"aeltere": _fefo_aeltere(r["artikel"], r["charge"]),
		"pflicht": modus == "Grund Pflicht",
		"charge": r["charge"],
		"name": frappe.get_cached_value("Item", r["artikel"], "item_name"),
	}
