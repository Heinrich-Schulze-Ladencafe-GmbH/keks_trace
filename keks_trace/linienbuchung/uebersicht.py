"""Linie: Tagesübersicht der Aufträge je Linie (wie der Orderblock bei FOBIS)."""

import frappe
from frappe.utils import flt, formatdate, getdate, nowdate

from keks_trace.linienbuchung.basis import _menge_text, hinweise

STATUS_REIHENFOLGE = {"Läuft": 0, "Freigegeben": 1, "Geplant": 2, "Fertig": 3, "Abgebrochen": 4}


def tagesuebersicht(datum: str | None = None) -> dict:
	"""Produktionsaufträge eines Tages je Linie mit Status, Menge, gebucht und Hinweis. Für heute zusätzlich
	alles, was von früheren Tagen noch freigegeben ist oder läuft (sonst fällt es aus dem Blick)."""
	tag = getdate(datum or nowdate())
	heute = tag == getdate(nowdate())
	bedingung = "(datum = %(tag)s or (%(heute)s and datum < %(tag)s and status in ('Freigegeben', 'Läuft')))"
	zeilen = frappe.db.sql(
		f"""
		select name, linie, datum, reihenfolge, status, artikel, artikelname, menge_kg, gebucht_kg, kunde,
			kundenauftrag, bemerkung
		from `tabProduktionsauftrag` where {bedingung}
		order by linie, datum, reihenfolge, creation
		""",
		{"tag": tag, "heute": 1 if heute else 0},
		as_dict=True,
	)
	je_linie = {}
	for z in zeilen:
		l = je_linie.setdefault(
			z.linie or "-", {"linie": z.linie or "-", "auftraege": [], "offen": 0, "fertig": 0}
		)
		fertig = z.status in ("Fertig", "Abgebrochen")
		l["fertig" if fertig else "offen"] += 1
		l["auftraege"].append(
			{
				"auftrag": z.name,
				"status": z.status,
				"artikel": z.artikel,
				"name": z.artikelname,
				"kunde": frappe.db.get_value("Customer", z.kunde, "customer_name") if z.kunde else None,
				"menge_text": _menge_text(z.artikel, z.menge_kg),
				"gebucht_text": _menge_text(z.artikel, z.gebucht_kg),
				"anteil": min(flt(z.gebucht_kg) / flt(z.menge_kg), 1) if flt(z.menge_kg) else 0,
				"vortag": getdate(z.datum) < tag,
				"datum": formatdate(z.datum),
				"hinweis": " · ".join(h["text"] for h in hinweise(z)),
			}
		)
	for l in je_linie.values():
		l["auftraege"].sort(key=lambda a: (STATUS_REIHENFOLGE.get(a["status"], 9), not a["vortag"]))
	return {
		"datum": formatdate(tag),
		"datum_iso": str(tag),
		"heute": heute,
		"linien": sorted(je_linie.values(), key=lambda l: l["linie"]),
		"offen": sum(l["offen"] for l in je_linie.values()),
		"fertig": sum(l["fertig"] for l in je_linie.values()),
	}
