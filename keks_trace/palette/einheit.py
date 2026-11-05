"""Paletten: Einheiten (Karton, Beutel, kg), Umrechnung und Füllung einer Palette."""

import frappe
from frappe import _
from frappe.utils import flt

from keks_trace.palette.basis import EPS, _fehler

# Einheiten, die nur zum Rechnen und Anzeigen dienen (nicht zum Zählen am Packtisch)
NUR_ANZEIGE = ("Palette", "Lage")


def einheiten(artikel: str, alle: bool = False) -> list[dict]:
	"""Zähleinheiten eines Artikels mit Umrechnung in die Lagereinheit, größte zuerst.

	Palette und Lage nur mit alle=True (Aufträge in Paletten, Anzeige); gezählt wird in Karton/Beutel.
	"""
	lager_einheit = frappe.get_cached_value("Item", artikel, "stock_uom")
	liste = [
		{"einheit": u.uom, "faktor": flt(u.conversion_factor)}
		for u in frappe.get_cached_doc("Item", artikel).uoms
		if u.uom != lager_einheit and flt(u.conversion_factor) > EPS and (alle or u.uom not in NUR_ANZEIGE)
	]
	liste.sort(key=lambda e: -e["faktor"])
	liste.append({"einheit": lager_einheit, "faktor": 1.0})
	return liste


def faktor(artikel: str, einheit: str | None) -> float:
	if not einheit:
		return 1.0
	for e in einheiten(artikel, alle=True):
		if e["einheit"] == einheit:
			return e["faktor"]
	_fehler(_("Einheit {0} ist für {1} nicht eingerichtet.").format(einheit, artikel))


def zerlegen(artikel: str, menge: float) -> str:
	"""Menge (Lagereinheit) als „3 Paletten + 5 Karton“; Reste in der kleinsten Zähleinheit."""
	menge = flt(menge, 6)
	stufen = [e for e in einheiten(artikel, alle=True) if e["einheit"] != "Lage"]
	if menge <= EPS:
		zaehl = [e["einheit"] for e in stufen if e["einheit"] not in NUR_ANZEIGE]
		return "0 " + ANZEIGE.get(zaehl[0], zaehl[0])
	teile = []
	# Stückware (Herzen, Rohlinge): Rest in Stück; Kiloware: Rest als Bruchteil der kleinsten Zähleinheit
	stueck = frappe.get_cached_value("Item", artikel, "stock_uom") in STUECK_EINHEITEN
	for i, e in enumerate(stufen):
		letzte = i == len(stufen) - 1 or (stufen[i + 1]["faktor"] == 1 and e["faktor"] != 1 and not stueck)
		if letzte:
			n = round(menge / e["faktor"], 2)
			if n >= 0.05:  # Rundungsreste (z. B. 0,0002 kg) nicht anzeigen
				teile.append(_n(n, e["einheit"]))
			break
		n = int(menge / e["faktor"] + 1e-6)
		if n:
			teile.append(_n(n, e["einheit"]))
			menge = flt(menge - n * e["faktor"], 6)
		if menge <= 1e-6:
			break
	if not teile:
		erste = next(e["einheit"] for e in stufen if e["einheit"] not in NUR_ANZEIGE)
		return "0 " + ANZEIGE.get(erste, erste)
	return " + ".join(teile)


ANZEIGE = {"Nos": "Stk", "Kg": "kg"}


STUECK_EINHEITEN = ("Nos", "Stk", "Stück")


def _n(n, einheit):
	mehrzahl = {"Palette": "Paletten", "Lage": "Lagen"}
	einheit = ANZEIGE.get(einheit, einheit)
	text = f"{flt(n, 3):,.3f}".rstrip("0").rstrip(".").replace(",", "_").replace(".", ",").replace("_", ".")
	return f"{text} {mehrzahl.get(einheit, einheit) if flt(n) != 1 else einheit}"
