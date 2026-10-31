"""Produktionsplan je Linie: Aufträge je Tag mit Dauer, Engpass, Auslastung. Knöpfe: planen, freigeben."""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, flt, formatdate, nowdate

from keks_trace.planung import _belegt


def execute(filters=None):
	f = frappe._dict(filters or {})
	if not f.linie:
		return _spalten(), [], _("Bitte eine Linie wählen.")
	von = f.von or nowdate()
	bis = f.bis or add_days(von, 30)
	auftraege = frappe.get_all(
		"Produktionsauftrag",
		filters={"linie": f.linie, "datum": ["between", [von, bis]], "status": ["!=", "Abgebrochen"]},
		fields=[
			"name", "datum", "reihenfolge", "status", "artikel", "artikelname", "menge", "einheit", "menge_kg",
			"dauer_stunden", "engpass", "verpackungsanlage", "kunde", "kundenauftrag", "liefertermin", "gebucht_kg",
		],
		order_by="datum, reihenfolge, creation",
	)  # fmt: skip
	laufzeit = flt(frappe.get_cached_value("Linie", f.linie, "laufzeit_stunden"))
	daten, tage = [], defaultdict(float)
	for a in auftraege:
		tage[a.datum] = 0
	for tag in tage:
		tage[tag] = _belegt(f.linie, tag)[0]
	for a in auftraege:
		daten.append({**a, "auslastung": flt(tage[a.datum] / laufzeit * 100, 0) if laufzeit else None})
	kg = sum(flt(a.menge_kg) for a in auftraege)
	return (
		_spalten(),
		daten,
		_("{0} Aufträge an {1} Tagen, {2} kg · Laufzeit {3} h pro Tag").format(
			len(auftraege), len(tage), f"{flt(kg, 0):,.0f}".replace(",", "."), f"{laufzeit:g}"
		)
		+ (_(" · erster Tag {0}").format(formatdate(min(tage))) if tage else ""),
	)


def _spalten():
	return [
		{"fieldname": "datum", "label": _("Produktionstag"), "fieldtype": "Date", "width": 110},
		{"fieldname": "reihenfolge", "label": _("Nr."), "fieldtype": "Int", "width": 50},
		{
			"fieldname": "name",
			"label": _("Auftrag"),
			"fieldtype": "Link",
			"options": "Produktionsauftrag",
			"width": 130,
		},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 95},
		{"fieldname": "artikelname", "label": _("Artikel"), "fieldtype": "Data", "width": 180},
		{"fieldname": "menge", "label": _("Menge"), "fieldtype": "Float", "width": 80},
		{"fieldname": "einheit", "label": _("Einheit"), "fieldtype": "Data", "width": 70},
		{"fieldname": "menge_kg", "label": _("kg"), "fieldtype": "Float", "width": 80},
		{
			"fieldname": "dauer_stunden",
			"label": _("Stunden"),
			"fieldtype": "Float",
			"precision": 2,
			"width": 80,
		},
		{"fieldname": "auslastung", "label": _("Tag ausgelastet %"), "fieldtype": "Percent", "width": 110},
		{"fieldname": "engpass", "label": _("Engpass"), "fieldtype": "Data", "width": 170},
		{"fieldname": "verpackungsanlage", "label": _("Verpackung"), "fieldtype": "Data", "width": 100},
		{"fieldname": "kunde", "label": _("Kunde"), "fieldtype": "Link", "options": "Customer", "width": 140},
		{"fieldname": "liefertermin", "label": _("Liefertermin"), "fieldtype": "Date", "width": 100},
		{"fieldname": "gebucht_kg", "label": _("Gebucht kg"), "fieldtype": "Float", "width": 90},
	]
