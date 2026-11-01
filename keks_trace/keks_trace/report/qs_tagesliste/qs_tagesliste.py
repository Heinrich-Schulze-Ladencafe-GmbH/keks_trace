"""QS Tagesliste: FEFO- und Einwaage-Abweichungen, Prüfungen außerhalb der Grenze und Sperren eines Tages.

Oben steht, ob der Tag schon durchgesehen ist; bestätigt wird über den Knopf im Bericht (nur QS).
"""

import frappe
from frappe import _
from frappe.utils import format_datetime, getdate, nowdate

from keks_trace import qs_tagesliste


def execute(filters=None):
	filters = frappe._dict(filters or {})
	von = getdate(filters.von or nowdate())
	bis = getdate(filters.bis or von)
	arten = set(filters.arten or []) if filters.get("arten") else None
	zeilen = [z for z in qs_tagesliste.eintraege(von, bis) if not arten or z["art"] in arten]
	return _spalten(), zeilen, None, None, _zusammenfassung(von, bis, zeilen)


def _spalten():
	return [
		{"fieldname": "zeit", "label": _("Zeit"), "fieldtype": "Datetime", "width": 150},
		{"fieldname": "art", "label": _("Art"), "fieldtype": "Data", "width": 90},
		{"fieldname": "station", "label": _("Station"), "fieldtype": "Link", "options": "Terminal Station", "width": 120},
		{"fieldname": "artikel", "label": _("Artikel"), "fieldtype": "Link", "options": "Item", "width": 120},
		{"fieldname": "charge", "label": _("Charge"), "fieldtype": "Link", "options": "Batch", "width": 160},
		{"fieldname": "text", "label": _("Was, Grund"), "fieldtype": "Small Text", "width": 420},
		{"fieldname": "beleg_typ", "label": _("Belegart"), "fieldtype": "Data", "hidden": 1},
		{"fieldname": "beleg", "label": _("Beleg"), "fieldtype": "Dynamic Link", "options": "beleg_typ", "width": 150},
	]  # fmt: skip


def _zusammenfassung(von, bis, zeilen):
	je_art = {a: sum(1 for z in zeilen if z["art"] == a) for a in qs_tagesliste.ARTEN}
	werte = [
		{"value": je_art[a], "label": a, "datatype": "Int", "indicator": "Orange" if je_art[a] else "Green"}
		for a in qs_tagesliste.ARTEN
	]
	offen = qs_tagesliste.offene_freigaben()
	werte.append(
		{
			"value": offen,
			"label": _("Freigaben offen"),
			"datatype": "Int",
			"indicator": "Blue" if offen else "Green",
		}
	)
	if von == bis:
		d = qs_tagesliste.durchsicht(von)
		werte.append(
			{
				"value": _("durchgesehen: {0}, {1}").format(
					d.durchgesehen_von, format_datetime(d.zeitpunkt, "dd.MM.yyyy HH:mm")
				)
				if d
				else _("noch nicht durchgesehen"),
				"label": _("Durchsicht"),
				"datatype": "Data",
				"indicator": "Green" if d else "Red",
			}
		)
	return werte
